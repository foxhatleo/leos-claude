# Seat driver: Codex CLI (OpenAI lineage)

- Install: `brew install codex` (or per OpenAI docs). Auth: `codex login` (interactive — user does this).
- Seat entry (schema v2 — see seats.template.json):
  ```json
  {"name": "codex", "lineage": "openai", "driver": "exec", "transport": "stdin",
   "argv": ["codex", "exec", "--sandbox", "read-only", "--skip-git-repo-check",
            "-c", "model_reasoning_effort={EFFORT}", "-"],
   "efforts": {"default": "high", "max": "xhigh"}, "timeoutSeconds": 600}
  ```
- Gotchas:
  - `--skip-git-repo-check` is required outside codex-trusted dirs; harmless inside.
  - `--sandbox read-only` is the enforcement layer — never drop it.
  - Do NOT use any `--wait`-style flags from plugin wrappers; plain `codex exec` backgrounded
    via the Bash tool is the reliable pattern.
  - Output includes a preamble + `codex` marker lines; the findings JSON block is at the end.
  - Flags can drift between versions — check `codex exec --help` if the invocation misbehaves.
- Smoke test (run at setup; expect COUNCIL-OK in output):
  `echo "Reply with exactly: COUNCIL-OK" | codex exec --sandbox read-only --skip-git-repo-check -c model_reasoning_effort="low" -`
- Also enable the `codex@openai-codex` plugin (marketplace `openai/codex-plugin-cc`) when this
  seat is chosen — it provides /codex commands the user may invoke directly.
