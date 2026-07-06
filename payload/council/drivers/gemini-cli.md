# Seat driver: Gemini CLI (Google lineage)

CLI surfaces drift between versions — check `gemini --help` on this machine, adjust the
invocation if needed, and confirm the smoke test before writing the seat.

- Install: per Google's Gemini CLI docs (`brew install gemini-cli` or npm). Auth: `gemini`
  first-run OAuth or `GEMINI_API_KEY` (user provides; never store keys in the repo).
- Invocation shape:
  - Headless prompt: `gemini -p "<prompt>"` or stdin piping.
  - Read-only: prefer a plan/read-only or approval-mode flag if available
    (e.g. `--approval-mode plan`). If no read-only mode exists, the seat still works for
    review (it only needs to READ) but note the weaker guarantee in the setup report.
- Seat entry (adjust to the flags this machine's version accepts):
  ```json
  {"name": "gemini", "lineage": "google", "driver": "exec", "transport": "arg",
   "argv": ["gemini", "-p", "{PROMPT_TEXT}"],
   "efforts": {"default": "default", "max": "default"}, "timeoutSeconds": 600}
  ```
  (If the CLI exposes no effort knob, both efforts map to the same value and the `{EFFORT}`
  token is simply unused.)
- Smoke test (must print COUNCIL-OK): `gemini -p "Reply with exactly: COUNCIL-OK"`
- Write this seat into seats.json only after the smoke test passes.
