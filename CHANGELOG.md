# Changelog

Newest first. Each version = git tag `v<N>`. Target Claudes: execute the **Migration actions**
of every version newer than the machine's installed version, in ascending order — you should
never need to read git diffs.

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
