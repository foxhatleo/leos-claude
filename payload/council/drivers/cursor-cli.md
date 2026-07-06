# Seat driver: Cursor CLI (multi-model: GPT, Gemini, GLM…)

Cursor's CLI surface changes quickly — check `cursor-agent --help` (or the current binary
name) on this machine, adjust the invocation if needed, and confirm each smoke test before
writing seats.

- Install: per Cursor docs (`curl https://cursor.com/install -fsS | bash` historically).
  Auth: `cursor-agent login` (user does this interactively).
- Invocation shape:
  - Headless: `cursor-agent -p "<prompt>" --model <model>` (print mode).
  - Model slugs: check `cursor-agent models`; pick per-lineage models (a GPT-class model for
    OpenAI lineage, Gemini-class for Google, GLM if offered).
  - Read-only: use a plan/readonly flag if available; if none, note the weaker guarantee.
- Seat entry per model (adjust to the flags this machine's version accepts):
  ```json
  {"name": "cursor-gpt", "lineage": "openai", "driver": "exec", "transport": "arg",
   "argv": ["cursor-agent", "-p", "{PROMPT_TEXT}", "--model", "<model-slug>"],
   "efforts": {"default": "default", "max": "default"}, "timeoutSeconds": 600}
  ```
  One seat per model/lineage — e.g. cursor-gpt (openai), cursor-gemini (google),
  cursor-glm (zhipu) — list strongest-first.
- Smoke test per seat (must print COUNCIL-OK):
  `cursor-agent -p "Reply with exactly: COUNCIL-OK" --model <slug>`
- Write each seat into seats.json only after its smoke test passes.
