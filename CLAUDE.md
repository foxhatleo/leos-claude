# leos-claude — Leo's portable Claude Code setup

You are a Claude Code instance on one of Leo's machines, asked to **install** or **upgrade**
this setup. This repo is written for you. Read this file fully before acting.

## Prime directives

1. **When unsure, ASK.** Reconciliation conflicts, ambiguous machine context, anything that
   might be machine- or project-specific — ask Leo with concrete options. Never guess, never
   silently overwrite.
2. **Never clobber.** Back up before writing (`tools/apply.py backup`). Existing settings you
   don't own are Leo's other configuration — merge around them, ask on conflict.
3. **No secrets ever enter this repo.** Auth (codex login, opencode providers, gh) is done by
   Leo interactively on each machine. If you find something secret-looking while working here,
   stop and tell Leo.
4. **Use the primitives.** All mechanical writes go through `tools/apply.py`
   (plan / backup / apply / verify / record / remove) so every machine converges identically.
   You drive the conversation; the script does the writes.

## What this is

Leo's reviewed-and-tested global Claude Code layer: the **council** multi-lineage adversarial
review system (spec: `payload/council/DESIGN.md`), **security hooks** (bash-guard tripwire,
auto-format-and-lint-feedback), **permission hardening** (secrets deny-list, PM-specific
allowlists), plus suggested tools and taste defaults. Everything machine-specific
(council seats, guard config, interview answers) lives OUTSIDE the repo in machine-local
files that YOU generate during setup.

## Procedures

- Fresh/first install on this machine → `docs/SETUP.md` (interview + install, in order).
- "Leo's Claude has been upgraded, please upgrade" → `docs/MIGRATE.md`.
- Conflict handling rules for both → `docs/RECONCILE.md`.

## Versioning

`VERSION` (integer) + `CHANGELOG.md` (newest-first; each entry has **Migration actions** —
imperative steps including removals, so you never have to read diffs). Git tags `v1..vN`
mark each version. The machine's installed version lives in `~/.claude/leos-claude.json`
(managed via `apply.py record`) together with ownership hashes and Leo's interview answers —
re-use recorded answers instead of re-asking on migration.

## Map

- `manifest.json` — payload → destination + strategy (copy / merge-json). Machine-local
  generated files are documented under `machineLocal` (never auto-applied).
- `payload/` — the actual files (hooks, council engine + skill + prompts + drivers, settings
  fragments, shell knowledge).
- `payload/council/drivers/` — per-CLI seat templates. For every chosen seat: check the CLI's
  current flags, run the driver's smoke test, and only write seats that pass.
- `tests/` — run after every install/migration; all batteries must pass before you report done.
