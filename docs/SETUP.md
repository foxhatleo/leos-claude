# SETUP — fresh install on a target machine

You (the target machine's Claude) drive this as a conversation with Leo, in order. Use
AskUserQuestion for every ASK step. Use `tools/apply.py` for every mechanical write. Record
answers as you go (they end up in the profile via `record --answers-file`).

## 0. Preflight

- **Clone** (public repo — anonymous HTTPS clone works): `git clone https://github.com/foxhatleo/leos-claude`.
  `gh` auth is NOT required to install, but note whether `gh auth status` passes — the
  permission allowlist includes gh commands and some workflows benefit from it; offer
  `gh auth login` as an optional step.
- Detect: OS, login shell (`echo $SHELL`), existing `~/.claude` contents, existing
  `~/.claude/leos-claude.json` (if present and version ≥ repo VERSION → run
  `python3 tools/apply.py verify --repo .` first: green → nothing to do; red → repair the
  drift (re-apply / ask Leo) before stopping. If present and lower → this is a MIGRATE,
  switch to docs/MIGRATE.md).
- `python3 tools/apply.py plan --repo .` — read the dry-run report. Any `conflict` items mean
  this machine has pre-existing Claude config → docs/RECONCILE.md governs; resolve each with
  Leo BEFORE applying.
- `python3 tools/apply.py backup --repo .` — always, before any write.

## 1. Reconcile existing settings

If `~/.claude/settings.json` exists with non-leos-claude content: the merge-json strategy
only adds our fragment's keys and union-merges arrays. The plan report lists exact conflicts
(same key, different value) — present each to Leo with both values and apply his choice
(`--force-dest` only after his explicit approval).

## 2. Package manager

ASK: pnpm / yarn / npm (Leo's usual answer: pnpm, but per machine). Then:
- Merge `universal` + chosen PM's list from `payload/settings/allowlist-templates.json` into
  `permissions.allow`: write a temp fragment `{"permissions": {"allow": [...]}}` and run
  `python3 tools/apply.py merge-settings --fragment <tempfile>` — the supported primitive for
  machine-generated settings (same conflict rules + ownership tracking as manifest merges).
- Global-bin PATH parity: see `payload/shell/fish-env.md`. fish → `fish_add_path`; zsh →
  `.zprofile` snippet. pnpm may additionally need `pnpm setup` — run it OUTSIDE any project dir
  (inside a project it may execute a project script named "setup").

## 3. Attribution

ASK: blank Claude attribution on commits/PRs on this machine? **Default: no** (leave harness
defaults). If yes: add `"attribution": {"commit": "", "pr": ""}` to settings.

## 4. Plugins

- Core, install without asking: `superpowers`, `code-review`, `feature-dev`,
  `security-guidance`, `github` (all `@claude-plugins-official`).
- ASK per machine: `vercel`, `playwright`, `typescript-lsp`, `frontend-design`.
- `codex@openai-codex` (+ marketplace `openai/codex-plugin-cc`): install iff the Codex council
  seat is chosen in step 6.
- Command: `claude plugin install <name>@<marketplace>`.

## 5. Connectors / MCP

ASK (multi-select): Slack, GitHub, Cloudflare, Google Drive, Google Calendar, Vercel, Figma,
Sentry, Atlassian (Jira/Confluence), Notion, Linear — plus free-form "anything else?". Wire the
chosen ones via the connectors directory / `claude mcp add` as available on that machine.

**Auth is part of this step, not an afterthought.** For each chosen connector: initiate the
OAuth/token flow, hand off to Leo for the interactive part, then **verify** the connection
actually works (list the server's tools / make a harmless read call) before marking it done.
Report per-connector status (connected / auth-pending / failed) in the final summary. Never
store tokens anywhere in this repo or its clone.

## 6. Council

ASK which setup (combinable): none / Codex CLI / Gemini CLI / GLM+Gemini(+more) via opencode
(OpenRouter or another provider) / via Cursor CLI.
- For each chosen seat, follow `payload/council/drivers/<driver>.md` in THIS order:
  1. **Install** the CLI (check `command -v` first — may already exist).
  2. **Auth** — check current state (`codex login status`, `opencode auth list`, the CLI's
     equivalent), and if unauthenticated, walk Leo through the interactive login/API-key flow
     NOW. Do not defer auth: an unauthenticated seat will silently fail at first council run.
  3. **Smoke test** (from the driver doc) — must return COUNCIL-OK.
- Only seats that pass BOTH auth verification and the smoke test get written to seats.json.
- Write `~/.claude/council/seats.json` (schema: `payload/council/seats.template.json`),
  strongest-first. None → `{"seats": []}` (native-only mode — see drivers/native-only.md).
- Write `~/.claude/council/config.json` → `{"disabledProjects": []}`.
- The council engine/skill/prompts/hook registration are part of the manifest apply (step 9).

## 7. Taste defaults

Offer everything in `payload/settings/suggested-defaults.json` (grouped ask is fine; honor the
`askExplicitly` notes — attribution default-skip; statusLine only if ccstatusline installed,
with the REAL absolute path from `command -v ccstatusline`). Optional tools: ASK about
installing `ccusage` and `ccstatusline` (global via the chosen PM).

## 8. Guard config

ASK: "What directory/directories under HOME hold your projects on this machine?" Write
`~/.claude/hooks/guard-config.json` → `{"homeToplevel": ["<answers>"]}` so bash-guard treats
recursive deletion of those roots as critical.

## 9. Apply + verify + record

```
python3 tools/apply.py apply --repo .        # copies + merges (refuses on conflicts)
python3 tools/apply.py verify --repo .       # must print ok:true
python3 tests/guard-tests.py                 # ALL PASS required
python3 tests/fmt-tests.py                   # ALL PASS required
python3 tests/council-tests.py               # ALL PASS required
python3 tools/apply.py record --repo <clone-path> --version $(cat VERSION) --tag v$(cat VERSION) --answers-file <answers.json>
```

Then report to Leo: what was installed, interview answers recorded, seats configured (with
smoke-test results), anything deferred/refused, and remind him hooks activate on the next
Claude Code session.
