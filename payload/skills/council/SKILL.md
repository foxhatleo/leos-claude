---
name: council
description: Multi-model multi-lineage adversarial review council. Use at two checkpoints — after finishing a plan (checkpoint=plan) and after finishing an implementation (checkpoint=impl) — on any non-trivial change. Also invoke when the Stop hook nudges about a missing council marker. Spec at ~/.claude/council/DESIGN.md.
---

# Council review

You (the Claude-family orchestrator) are the AUTHOR under review. Other-lineage models check your
work for blind spots you share with yourself. Follow this procedure mechanically — the places
where it constrains you (severity, rejection evidence) exist because you are the conflicted party.

Paths: `BIN=~/.claude/council/bin/council.py`, prompts in `~/.claude/council/prompts/`,
**seats config: `~/.claude/council/seats.json`** (machine-local; created at setup — see
`drivers/` in the leos-claude repo for per-CLI templates).
Kill switches: `.council-off` file in repo root, or project listed in
`~/.claude/council/config.json` `disabledProjects` — if either, stop here.

## Seats model

`seats.json` lists this machine's EXTERNAL reviewer seats, strongest-first (schema v2 —
full field docs in the leos-claude repo's `seats.template.json`):

```json
{ "seats": [
    {"name": "codex", "lineage": "openai", "driver": "exec", "transport": "stdin",
     "argv": ["codex", "exec", "--sandbox", "read-only", "--skip-git-repo-check",
              "-c", "model_reasoning_effort={EFFORT}", "-"],
     "efforts": {"default": "high", "max": "xhigh"}, "timeoutSeconds": 600}
  ] }
```

- **Build the command from `argv`, never from a hand-written shell string**: substitute
  `{EFFORT}` (`efforts.default` below critical, `efforts.max` at critical), then shell-quote
  every element individually when composing the Bash call (reviewer/prompt text must never be
  interpolated unquoted). `transport: stdin` → append `< $WORK/prompt-<checkpoint>.md`;
  `transport: arg` → replace the `{PROMPT_TEXT}` element with `"$(cat $WORK/prompt-<checkpoint>.md)"`.
- Respect each seat's `timeoutSeconds` (default 600) as the Bash call timeout.
- The **native seat (Sonnet)** always exists implicitly and is never listed: spawn a
  subagent via the Agent tool using whatever general-purpose agent type THIS harness offers
  (e.g. `claude` or `general-purpose` — check the session's available agent types) with
  `model: sonnet`, prompt = prompt-file content + "You may read files in <repo path> but must
  not modify anything. Your final message must be ONLY the JSON findings block."
- Missing/empty/unparseable seats.json → **native-only mode**: every tier is served by
  independent native Sonnet subagents (low=1, elevated=2, high=3, critical=3). State the
  reduced-diversity caveat in your report.

## Tier → seats mapping

| Tier | Seats |
|---|---|
| skip | — |
| low (1) | native Sonnet |
| elevated (2) | native + seats[0] |
| high (3) | native + seats[0] + seats[1] |
| critical | native + ALL seats, everyone at `max` effort, **+ human sign-off** |

Fewer external seats than the tier wants → use what exists (e.g. one external seat: high =
native + that seat; note the shortfall in the report). Never exceed 4 total seats.

## Checkpoint: impl (after implementation)

### 1. Tier
```
python3 $BIN risk --json
```
That is the **floor**. You may escalate **at most one tier** above it if you have a concrete
worry (log it: reason in the ledger, type `escalation`). You may NEVER go below the floor.
- `skip` → stop (no council).

### 2. Deterministic gates (reviewer zero)
Read `.council.json` in the repo root for `fastChecks` / `slowChecks` (arrays of shell commands).
- Run **fastChecks** (typecheck/lint) first, workspace-scoped if the config says so.
  - Fail on low/elevated → STOP; fix the failures first; record ledger entry
    `blocked-by-deterministic-failure`. This is not a passed review.
  - Fail on high/critical → continue to council, include failure output as reviewer context.
- Run **slowChecks** (test/build) if configured; their output is reviewer *context*, not a gate.
- No `.council.json` / no commands → escalate one tier (unknown deterministic floor) and tell
  reviewers the deterministic status is unknown. Zero tests collected counts as a fail, not a pass.

### 3. Dispatch — blind, parallel (Round 1)
Get the work dir first: `WORK=$(python3 $BIN state-dir)/tmp` — ALL prompt and output files go
there, NEVER into the repo (zero repo footprint; repo-root output files are also a symlink
hazard). Build the prompt from `prompts/review-impl.md`: substitute `{CHECKS}` (gate results),
`{TASK}` (2-4 sentence task summary — no hints about what you think is fine), `{DIFF}` (output
of `git diff -M <merge-base>`; if huge, include stat + the riskiest files in full). Write it to
`$WORK/prompt-impl.md`. Then launch ALL seats for the tier in one message, in parallel, in the
background, from the repo root:

- **Native seat**: Agent tool as described in the Seats model.
- **Each external seat**: build its command from `argv` + effort per the Seats model, run via Bash with
  run_in_background and a generous timeout, output to `$WORK/out-<seat>.md`.

Budget: give each Bash call a timeout (default 10 min; `.council.json` `budgetSeconds`
overrides). If a seat times out or errors, proceed without it and record `fallback-fired` in
the ledger; if ALL external seats fail, fall back to native-only and record it.

### 4. Adjudicate — mechanically
Parse every finding. Assign each an `id` and set `reviewer` to the seat that produced it (the
prompt schema deliberately omits these — you know which output file is which). For each, record
EXACTLY one disposition in the ledger — write the JSON (single entry or array) to a file under
`$WORK` and run `python3 $BIN ledger --entry-file <file>`. NEVER inline reviewer-derived text
into a shell command (quote-injection hazard). Entry type `finding`; include: id, reviewer,
severity, claim, disposition, evidence/patch ref:
- `accepted` / `fixed` → point to the patch.
- `rejected` → REQUIRES concrete evidence: exact command output, a cited requirement, or a
  passing regression test that encodes the CORRECT behavior and exercises the claimed failure.
  Fluent reasoning alone is NOT evidence.
- `deferred` → reason + surface it to the developer.
Severity is REVIEWER-ASSIGNED. You may not change it. Findings whose claim matches
auth/data-loss/money/security are auto-high regardless of the reviewer's tag.
**High-severity rejects fail closed:** without qualifying evidence, you cannot reject — fix it or
ask the developer.

### 5. Re-review (once) + audit
If you made fixes: send ONLY the patched region + the findings it addresses back to ONE seat
(seats[0] preferred; native if no externals) for a single re-review. Hard cap: 2 passes total.
No debate rounds.
If you rejected ≥1 finding: pick ONE rejected finding at random and ask a DIFFERENT seat
"was this correctly dismissed?" — record the answer (type `reject-audit`).

### 6. Close out
```
python3 $BIN mark --checkpoint impl --tier <tier>
```
Report to the developer: tier + reasons, seats consulted, findings table (severity, claim,
disposition), anything deferred/overridden. **critical tier: you MUST present the deduped digest
and get an explicit developer ack before treating the task as done.**

If you skip the council on an elevated+ diff (you judged it unwarranted), record
`python3 $BIN mark --checkpoint impl --override --reason "<why>"` — never skip silently.

## Checkpoint: plan (after writing a plan, before implementing)

1. Stakes from OBJECTIVE plan-text signals, not your judgment: plan mentions
   auth/payments/migrations/schema/breaking API/data deletion → high-stakes; else normal.
2. Reviewer: **seats[0] at default effort** (normal) or **seats[0] at max + seats[1] at max**
   (high-stakes). Native Sonnet if no external seats. Never a weak/flash-class seat for plans.
   Prompt from `prompts/review-plan.md` ({TASK}, {PLAN}) — written to `$WORK/prompt-plan.md`,
   outputs to `$WORK/out-plan-*.md` (same zero-repo-footprint rule as impl).
3. Adjudicate as in impl step 4 (same disposition rules, reviewer-assigned severity).
4. `python3 $BIN mark --checkpoint plan`. Plan approval is NOT a license to soften the impl
   checkpoint — the impl council still runs on its own tier.

## Never

- Never present the council as passed when a seat errored out — report what actually ran.
- Never lower a reviewer's severity, never reject high-severity without evidence or the developer.
- Never run reviewers with write access.
- Never loop beyond 2 passes; escalate remaining disagreement to the developer instead.
