# Changelog

Newest first. Each version = git tag `v<N>`. Target Claudes: execute the **Migration actions**
of every version newer than the machine's installed version, in ascending order — you should
never need to read git diffs.

## v2 — 2026-07-08 (tag `v2`)

Shell policy switched to zsh-first. Leo's interactive shell moved off fish; the portable layer
now standardizes on **zsh, with bash only as a fallback** where zsh is unavailable. The default
clone location also moved to **`~/.leos-claude`** (dot-prefixed).

### Changed
- `payload/shell/fish-env.md` → renamed to `payload/shell/shell-env.md` and rewritten
  zsh-first: dropped the fish sections (`fish_add_path -U`, "launched from fish", the
  fish-is-not-POSIX warning); PATH-parity guidance is now `~/.zprofile` (zsh) with a
  `~/.bash_profile` fallback note. The env-inheritance facts and macOS quirks are unchanged.
- `docs/SETUP.md` step 2 references the renamed doc and the zsh → bash PATH-parity order.
- Default clone location is now **`~/.leos-claude`** (dot-prefixed); `docs/SETUP.md` step 0
  clones there explicitly. The profile filename `~/.claude/leos-claude.json` is unchanged.

### Migration actions
- No deployed files change: the shell doc is reference knowledge (not a manifest item), so there
  is nothing to copy or `apply.py remove`. Just re-record:
  `python3 tools/apply.py record --repo <clone> --version 2 --tag v2`.
- Machine-local, ASK Leo before editing: if this machine's `~/.claude/CLAUDE.md` has a
  fish-specific "Shell" section (or other fish-syntax instructions), update it to the zsh-first
  policy. These are Leo's personal files, not repo-managed.
- Existing clone: move it to the dot-prefixed path (`mv ~/leos-claude ~/.leos-claude`), run
  `git worktree repair` inside it if you use worktrees, then re-point the profile:
  `python3 tools/apply.py record --repo ~/.leos-claude --version 2 --tag v2`.

## v1 — 2026-07-06 (tag `v1`)

Initial release: Leo's full portable layer.

### Added
- Council review system (engine `council.py`, seats-abstraction SKILL, prompts, DESIGN spec,
  5 seat drivers: codex-cli, opencode, gemini-cli, cursor-cli, native-only). Review prompts
  carry a work-alone clause: seats must not convene review layers of their own (some seat CLIs
  are provisioned as orchestrators with council-like settings).
- Codex fast-mode setup option (plan-gated `service_tier = "fast"`; trial run at setup, falls
  back to normal mode if the plan disallows it).
- bash-guard PreToolUse tripwire (guard-config.json machine extras; 90+ test cases).
- format-on-edit PostToolUse hook (9-toolchain auto-detection + lint feedback).
- Settings fragment: 20 secrets deny rules + hook registrations ($HOME-portable commands).
- Allowlist templates (pnpm/yarn/npm + universal git/gh), suggested taste defaults.
- tools/apply.py primitives, docs (SETUP/MIGRATE/RECONCILE), test batteries.

### Migration actions
- None — v1 has no predecessor. Fresh machines: docs/SETUP.md.
