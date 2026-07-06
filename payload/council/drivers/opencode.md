# Seat driver: opencode (multi-model — GLM / Gemini / others via provider)

- Install: `brew install opencode` (or per opencode docs).
- Auth: `opencode auth login` → pick a provider (OpenRouter is the usual choice; any provider
  that serves the wanted models works — reflect the provider in the model slugs).
- **Read-only enforcement:** always `--agent plan` (opencode's built-in plan agent denies edits).
- Model slugs (OpenRouter form; check `opencode models | grep -i <name>` at setup — slugs drift):
  - GLM: `openrouter/z-ai/glm-5.2`
  - Gemini: `openrouter/google/gemini-3.5-flash`
  - (OpenAI-lineage models via a provider are possible, but prefer the native codex CLI seat.)
- Seat entry (GLM example, schema v2 — see seats.template.json):
  ```json
  {"name": "glm", "lineage": "zhipu", "driver": "exec", "transport": "arg",
   "argv": ["opencode", "run", "--agent", "plan", "-m", "openrouter/z-ai/glm-5.2",
            "--variant", "{EFFORT}", "{PROMPT_TEXT}"],
   "efforts": {"default": "high", "max": "max"}, "timeoutSeconds": 600}
  ```
- Effort via `--variant` (provider-specific: high/max/xhigh — if a variant is rejected, fall
  back to `high`).
- Smoke test: `opencode run --agent plan -m <slug> "Reply with exactly: COUNCIL-OK"`
- Gotcha: opencode agents CAN read the repo (intended) — treat their runs as repo-read-granting.
