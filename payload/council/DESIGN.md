# Council Review — Design Spec (v5.1)

A multi-model, multi-lineage adversarial review harness for Claude Code. The orchestrator
(the session's Claude-family model — Anthropic lineage; the specific model varies by session)
runs a "council" of other-lineage LLMs at two checkpoints — after **planning** and after
**implementation** — reads their findings, adjudicates mechanically, fixes, and re-reviews once.
Goal: catch training-lineage-correlated blind spots the Claude-family orchestrator shares with
itself.

Status: **v5 design approved; v5.1 resolves §8 implementation details. Implemented.** Shaped through two blind, independent
four-lineage review rounds (raw CLI reviewer output in `rounds/`; the two Sonnet reviews ran as
native subagents, captured in the session transcript). Round-1 verdict: unanimous
"don't ship as-is." Round-2 verdict: 3× "ship with changes," 1× "re-architect." This spec is the
synthesis.

---

## 1. Design principles (why, not just what)

1. **The author must not decide how hard it gets checked.** The primary gate is objective
   (diff-derived), not self-assessed confidence. Confidence may only *escalate*, never lower.
2. **Capability first on the common path; diversity where stakes are high.** A weak reviewer's
   "lineage diversity" is worthless if it can't find the bug. The strong native model (Sonnet)
   is the everyday baseline; foreign lineages are added as stakes rise, where their different
   failure distributions earn their cost.
3. **Cost tracks risk.** Most changes get one reviewer; the full panel is rare.
4. **Never block mid-flow.** The council runs inside the orchestrator's finish-the-task flow and
   surfaces findings in its report + a boundary digest. No hard git-hook gate. (The #1 predicted
   churn cause was a mid-flow hard-block.)
5. **Adjudication is externally verifiable, not self-refereed.** Severity comes from the reviewer,
   not the author; high-severity rejections fail *closed* without evidence; a different reviewer
   spot-checks a sample of rejections.
6. **Prove and tune with data.** Every finding + disposition is logged to a per-project ledger so
   the ladder can be tuned and the council's value measured, not assumed.

---

## 2. Fixed model registry (pinned — never looked up at runtime)

| Seat | Lineage | Driver | Invocation (effort filled per tier) |
|---|---|---|---|
| **Sonnet 5** | Anthropic | native Agent tool | `subagent_type: claude`, `model: sonnet` |
| **Codex** (GPT‑5.5) | OpenAI | `codex exec` | `codex exec --sandbox read-only --skip-git-repo-check -c model_reasoning_effort="<high\|xhigh>" -` |
| **GLM‑5.2** | Zhipu | `opencode run` | `opencode run --agent plan -m openrouter/z-ai/glm-5.2 --variant <high\|max>` |
| **Gemini 3.5 flash** | Google | `opencode run` | `opencode run --agent plan -m openrouter/google/gemini-3.5-flash --variant <xhigh\|max>` |

- **Portability note (leos-claude):** this table documents the reference setup the council was
  designed around. On installed machines the actual seat roster is parameterized by
  machine-local `~/.claude/council/seats.json` (see the skill's Seats model + seats.template.json);
  the ladder logic and everything below is seat-roster-agnostic.
- Orchestrator/author = the session's **Claude-family model** (Anthropic lineage). The ladder
  logic depends on lineage, not the specific model.
- **Variant fallback:** if a provider rejects a `--variant`, fall back to `high` deterministically.
  No runtime model discovery, ever.
- **Sonnet effort caveat (v1):** the native Agent tool inherits session effort and does not expose
  a per-call override; "Sonnet xhigh" at `critical` is aspirational until the harness exposes it.
- **Reviewers run read-only:** Codex via `--sandbox read-only`; opencode reviewers via a read-only
  agent/permission profile (deny edits + write-bash). Reviewers *may* read/grep the repo to verify
  claims — that is the intended mode for implementation review — but cannot modify it.
- **Reviewers work alone:** both review prompts instruct every seat to produce the review itself,
  in that run — no subagents, no consulting other models, no second review layer. Some seat CLIs
  (e.g. Codex) are provisioned on Leo's machines with orchestrator-side settings that convene a
  review council of their own; a seat obeying those mid-review would nest councils and stall. The
  clause is conditional and self-contained, so a seat with no such configuration reads it as a
  no-op instead of getting confused.

---

## 3. The gate (hybrid, capped + logged)

**Final tier = max(risk_floor, min(confidence_tier, risk_floor + 1)).**

- `risk_floor` is computed by a deterministic script from the diff. This is the primary gate.
- The orchestrator's self-assessed `confidence_tier` may **escalate at most one tier** above the
  floor, never below it. Every escalation is logged (finding: `escalation`, floor→final, reason).
- Confidence can therefore never *suppress* review (the round-1 conflict of interest) and cannot
  run away into over-review (the round-2 concern).

### 3.1 Risk-floor signals

Path/shape signals (cheap, first-pass):
- Risk-path globs → `high`/`critical`: `**/auth/**`, `**/migrations/**`, crypto/security dirs,
  `**/.github/**` + CI/CD, schema/`*.sql`/ORM model files, public/shared package entrypoints,
  payments/billing.
- Diff size / blast radius (files touched, lines, number of workspaces).
- Deletions, new dependencies, new env vars.

Semantic signals (round-2 addition — catch small-diff-high-risk):
- Exported/public API surface changed (signature/type/enum changes in package entrypoints).
- Tests deleted **or assertions removed/weakened** (not just "tests changed").
- Security-sensitive symbol names touched (token, secret, password, permission, authorize, csrf…).
- Config/env surface changes outside obvious globs (CORS, CSP, rate-limit, logging redaction).

**Known residual risk (documented, not claimed closed):** the floor is a *proxy*. A fluent
orchestrator (or accidental diff shape) can dodge globs (route auth through `utils`, split a
migration into a "prep" commit). Semantic signals reduce but do not eliminate this. The ledger +
sampled audit (§6) are the compensating controls. **Do not describe the gate as tamper-proof.**

### 3.2 Diff base robustness

Diff is computed vs the merge-base with the default branch, but must be robust to `--amend`,
squash, rebase, and dirty working trees (the orchestrator does these routinely). Use a stable
base resolution + working-tree overlay; when the base is ambiguous, escalate one tier rather than
under-report.

---

## 4. The ladder (who is called when)

| Tier | Council (seats added cumulatively) | Effort (per seat) | Fires when |
|---|---|---|---|
| **skip** | — | — | docs/comments/formatting/lockfile-only, or no code change |
| **low** (1) | Sonnet 5 | Sonnet `high` | small, isolated, no risk signals |
| **elevated** (2) | Sonnet + Codex | Sonnet `high` · Codex `high` | moderate blast radius / new deps / deletions / feature w/o tests |
| **high** (3) | Sonnet + Codex + GLM‑5.2 | Sonnet `high` · Codex `xhigh` · GLM `max` | risk globs or large blast radius or semantic risk |
| **critical** (4) | Sonnet + Codex + GLM + Gemini 3.5 flash — full four lineages **+ human sign-off** | Sonnet `xhigh` · Codex `xhigh` · GLM `max` · Gemini `max` | auth/migrations/payments/public-API + high blast radius, or data-loss risk |

- **Sonnet is the everyday baseline** (strong + cheap-to-orchestrate; same-lineage is acceptable at
  low stakes). Foreign lineages escalate on top. **Gemini flash is never a sole reviewer** — it is
  the least-load-bearing seat, added only at `critical`.
- **Critical requires human sign-off:** the orchestrator does not self-clear a critical change. It
  synthesizes the four reviews into **one deduped digest** (not four raw outputs) and asks the
  developer to ack before considering the change done.

---

## 5. Execution & convergence

1. **Deterministic gates first (fixed per round 2):**
   - *Fast* gates (typecheck, lint) run as a prerequisite. Workspace-scoped in monorepos (only the
     changed package(s) — a diff in one package must not trigger sibling packages' builds).
   - *Slow* gates (test, build) run as **context fed to reviewers**, not a hard prerequisite.
   - **Gate-absent** (no command declared) → escalate one tier + tell reviewers the deterministic
     floor is unknown. **Gate-vacuous** (0 tests collected) → treat as failure, not pass.
   - On `high`/`critical`, the council runs **even if gates fail**, with the failure output as
     context (design/architecture feedback is still valuable on a red build). On `low`/`elevated`,
     a failing gate short-circuits and is recorded as `blocked-by-deterministic-failure` — never
     "review passed."
2. **Round 1 — blind & parallel.** Reviewers run concurrently, none seeing the others' output.
   Each emits structured findings (§5.1) and **tags its own severity**.
3. **Mechanical adjudication.** For each finding the orchestrator records exactly one disposition:
   `accepted` (→ patch ref), `fixed` (→ patch ref), `rejected` (→ evidence), `deferred` (→ reason).
   - A `rejected` finding must cite concrete evidence: exact command output, a cited requirement,
     or a **passing regression test that encodes the *correct* expected behavior** and exercises
     the claimed failure mode. (Not a "failing test" — you cannot disprove a bug with one; and a
     test that merely asserts the current buggy behavior does not count.)
   - **High-severity rejections fail closed:** without qualifying evidence *or* developer sign-off,
     a high-severity finding cannot be rejected — it must be fixed or surfaced to the developer.
   - **Severity is reviewer-assigned**, plus keyword auto-high (auth/data-loss/money/security)
     regardless of orchestrator opinion. The orchestrator never sets or lowers severity.
4. **One bounded re-review.** After fixes, re-review **only the patched region**, once. Hard cap:
   **2 passes total.** No debate rounds.
5. **Sampled reject-audit.** A random sample of `rejected` findings is spot-checked by a *different*
   reviewer ("was this correctly dismissed?"), catching orchestrator rationalization cheaply.
6. **Budget & fallback.** Per-checkpoint **wall-clock** ceiling (v1: per-reviewer timeouts; token
   budgets are not portably measurable across three external CLIs). On exceed, fall back to a
   single strong reviewer (Sonnet or Codex) — and record that the fallback fired (so a slow test
   suite silently collapsing every review to one reviewer is visible, not hidden).

### 5.1 Structured finding schema
`{ id, reviewer, severity (reviewer-set), file, line, claim, suggested_fix, reviewer_confidence }`
→ disposition appended: `{ disposition, evidence_ref, patch_ref, audited_by? }`.

---

## 6. Triggering, surfacing & ledger

- **Skill `/council <plan|impl>`** — the orchestrator invokes it at both checkpoints as part of its
  normal flow.
- **Planning checkpoint (kept, fixed):** uses a **strong** reviewer (Codex/GLM at high), not flash.
  Plan-stakes derived from **objective plan-text keywords** (auth/payments/migrations/breaking-API/
  schema), not self-assessed. Scoped to non-trivial work. The prompt demands *concrete failure
  modes and cheaper alternatives* + requires the plan to state expected files, invariants, test
  strategy, rollback, and non-goals. Guard against plan-approval being treated as license to skip
  the implementation checkpoint (no cross-checkpoint anchoring).
- **Implementation checkpoint:** ladder per §4, backstopped by a **soft** `Stop`-hook nudge — if the
  orchestrator ends an implementation turn on an `elevated`+ diff with no fresh council marker, the
  hook reminds it. **Never a hard block.** Override allowed with a logged, developer-surfaced reason.
- **Surfacing:** findings appear in the orchestrator's normal report and, at a natural boundary
  (pre-push/PR), as a **deduped digest**. Not a firehose of raw reviewer text.
- **Ledger & markers (central, zero repo footprint):** state lives under
  `~/.claude/council/state/<project-slug>/` — `ledger.jsonl` plus `markers/<diff-hash>.json`.
  Nothing is written into the user's repos (no gitignore dance, consistent with the no-traces
  preference). Every finding, severity, disposition, evidence, reviewer, and later-reverted flag
  is logged — this is what makes the ladder tunable and the council's value measurable.
- **Soft-hook override mechanics (precise):** on turn-end with an `elevated`+ diff, the Stop hook
  looks up `markers/<diff-hash>.json`. A `reviewed` or `overridden` marker → pass. No marker →
  nudge (exit 2) with exact instructions: run `/council impl`, or record an override
  (`council.py mark --override --reason "…"` — logged to the ledger and surfaced in the digest).
  Loop-guard: after 2 nudges for the same diff hash, pass. Any error (no git, no python, malformed
  input) → **fail open** (exit 0). The hook never hard-blocks.

---

## 7. Scope & configuration

- **Global but risk-gated.** Installed in global Claude settings; the risk floor keeps it dormant on
  trivial/throwaway work (nothing trips the floor → `skip`).
- **Per-project off-switch:** a `.council-off` marker fully disables it.
- **Per-project config** `.council.json`: fast/slow check commands (+ workspace-aware selection),
  default branch, size thresholds, budget. Missing/invalid config for N runs is surfaced as a
  setup problem, not silently ignored.

---

## 8. Implementation decisions (v5.1 — resolved)

1. **opencode read-only profile:** reviewers run with `--agent plan` (opencode's built-in
   read-only agent: edits denied, reads allowed).
2. **Semantic triggers = regex/diff heuristics** (v1), not AST: changed `export …` lines,
   removed `assert|expect|should` lines, security symbols in changed lines, config-surface keys.
   AST precision deferred until the ledger shows the heuristics under- or over-firing.
3. **Diff-base resolution:** upstream branch if set → `origin/<default>` merge-base → `HEAD`
   (uncommitted-only) as final fallback; `git diff -M <base>` (rename-aware) covers committed +
   working-tree changes in one pass. Ambiguous base → escalate one tier.
4. **Thresholds (initial, conservative — tune from ledger):** lines ≤60 & files ≤3 = small;
   lines >400 or files >10 or workspaces >2 = large; deletion-heavy = deletions >2× additions
   and >100 lines.
5. **Stop-hook marker:** `~/.claude/council/state/<project-slug>/markers/<diff-hash>.json`,
   diff-hash = sha256 of the diff text (first 16 hex chars). Written by `council.py mark`.
6. **Critical sign-off language:** one deduped digest (finding → severity → reviewers → proposed
   disposition), ending with an explicit ack request; the orchestrator does not proceed past
   critical without a user response.

---

## 9. Explicitly rejected alternatives

- **Self-assessed confidence as the primary gate** (v1) — unanimous conflict-of-interest.
- **Gemini-flash as the everyday baseline** (v4) — unanimous "under-catches / theater."
- **Orchestrator-assigned severity** — defangs the disposition teeth (severity-downgrade escape).
- **Mid-flow hard-block Stop hook** — predicted #1 churn cause.
- **"Failing test to reject a finding"** — logically backward.
- **Async single-model advisory re-architecture** (Gemini's dissent) — discards the founding goal
  (lineage diversity), which the review rounds themselves demonstrated has real value.
