# leos-claude

Leo's portable Claude Code configuration, packaged for **Claude-driven installation** — the
repo is consumed by the Claude Code instance on the target machine, not by a shell script.

## Usage

**To set up a new machine**, open Claude Code and paste:

> Set up my Claude from https://github.com/foxhatleo/leos-claude — clone it, read its
> CLAUDE.md, and follow docs/SETUP.md. Ask me whenever a choice is machine-specific.

**To upgrade an already-set-up machine** after this repo changes:

> Leo's Claude has been upgraded. Here is the repo:
> https://github.com/foxhatleo/leos-claude — please upgrade per docs/MIGRATE.md.

The installing Claude interviews for machine-specific choices (package manager, council
reviewer CLIs, plugins, connectors), backs up and merges with existing settings (never
clobbers, asks on conflict), verifies external CLI + MCP auth, and runs the shipped test
batteries before declaring success.

## What's inside

| Piece | What it does |
|---|---|
| **Council** | Multi-lineage adversarial code review: a deterministic diff-risk gate + Stop-hook nudge convenes external reviewer models (Codex / Gemini / GLM via configurable CLI "seats") at plan- and implementation-checkpoints, with evidence-based finding adjudication and a per-project ledger. Degrades gracefully to native-only review. |
| **bash-guard** | PreToolUse tripwire blocking catastrophic deletions (`rm -rf ~`-class, dd-to-device, mkfs) — shell-tokenized, cwd-aware, 90+ test cases. Fail-open by design. |
| **format-on-edit** | PostToolUse hook: auto-detects the project's toolchain (oxfmt/biome/eslint/ruff/pylint/gofmt/golangci-lint/rustfmt/clippy), formats silently, feeds remaining lint errors back to Claude. |
| **Permission hardening** | Secrets deny-list + package-manager-specific command allowlists on top of auto mode. |
| **Suggested defaults** | Leo's taste settings (model/effort/ultracode/etc.), offered per machine, never forced. |

## Layout

`CLAUDE.md` = the entry point for the installing Claude · `docs/` = setup/migration/reconciliation
procedures · `payload/` = the files that get installed · `tools/apply.py` = deterministic
install primitives (dry-run, backup, ownership-tracked merge, verify) · `tests/` = post-install
verification batteries · `VERSION` + `CHANGELOG.md` + git tags = versioning.

Machine-local state (council seats, guard config, interview answers) is generated at setup
into `~/.claude/` and never committed here. No secrets live in this repo.

## Provenance

Every component was adversarially reviewed by a multi-model council (GPT-5.5, GLM-5.2, Gemini,
Claude Sonnet) — the same review system this repo ships. See `payload/council/DESIGN.md` for
the design history.

## License

GNU GPLv3 — see [LICENSE](LICENSE). No secrets, API keys, or machine-specific state live in
this repo; all auth happens interactively on each machine, and machine-local config is
generated at setup outside the repo.
