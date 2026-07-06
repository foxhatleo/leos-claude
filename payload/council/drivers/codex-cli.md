# Seat driver: Codex CLI (OpenAI lineage)

- Install: `brew install codex` (or per OpenAI docs). Auth: `codex login` (interactive — user does this).
- Seat entry (schema v2 — see seats.template.json):
  ```json
  {"name": "codex", "lineage": "openai", "driver": "exec", "transport": "stdin",
   "argv": ["codex", "exec", "--sandbox", "read-only", "--skip-git-repo-check",
            "-c", "model_reasoning_effort={EFFORT}", "-"],
   "efforts": {"default": "high", "max": "xhigh"}, "timeoutSeconds": 600}
  ```
- Fast mode (ASK at setup, only after the normal smoke test passes): Codex "fast mode" is
  priority processing — top-level `service_tier = "fast"` in `~/.codex/config.toml` — and is
  **plan-gated**. If Leo wants it, trial-run FIRST:
  `echo "Reply with exactly: COUNCIL-OK" | codex exec --sandbox read-only --skip-git-repo-check -c service_tier="fast" -c model_reasoning_effort="low" -`
  - COUNCIL-OK → set `service_tier = "fast"` in `~/.codex/config.toml`. That file is Leo's
    pre-existing Codex config and sits OUTSIDE apply.py's backup/ownership coverage, so:
    back it up first (`cp ~/.codex/config.toml ~/.codex/config.toml.bak-leos-claude` if it
    exists), make the smallest possible edit (add/update that one top-level key, touch no other
    keys; create the file only if absent), then re-run the NORMAL smoke test to prove codex
    still parses its config — any failure → restore the backup and tell Leo. Every codex run on
    the machine — council seats included — inherits the key; seats.json needs no change.
  - Error mentioning plan/tier/eligibility (while the normal-mode smoke test passes) → the
    current plan doesn't include fast mode: leave `service_tier` unset (normal mode), tell Leo,
    and record that outcome with the interview answers.
  - Like all flags this can drift — if `service_tier` is rejected as unknown config, check
    current Codex docs for the fast-mode setting before concluding the plan disallows it.
- Gotchas:
  - `--skip-git-repo-check` is required outside codex-trusted dirs; harmless inside.
  - Leo provisions Codex on some machines with orchestrator settings of its own (a global
    AGENTS.md with a council-like review gate). The council review prompts carry a work-alone
    clause so a codex seat won't convene its own council mid-review; if a seat ever stalls
    spawning reviewers anyway, check `~/.codex/AGENTS.md` for the conflicting instruction.
  - `--sandbox read-only` is the enforcement layer — never drop it.
  - Do NOT use any `--wait`-style flags from plugin wrappers; plain `codex exec` backgrounded
    via the Bash tool is the reliable pattern.
  - Output includes a preamble + `codex` marker lines; the findings JSON block is at the end.
  - Flags can drift between versions — check `codex exec --help` if the invocation misbehaves.
- Smoke test (run at setup; expect COUNCIL-OK in output):
  `echo "Reply with exactly: COUNCIL-OK" | codex exec --sandbox read-only --skip-git-repo-check -c model_reasoning_effort="low" -`
- Also enable the `codex@openai-codex` plugin (marketplace `openai/codex-plugin-cc`) when this
  seat is chosen — it provides /codex commands the user may invoke directly.
