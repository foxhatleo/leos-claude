# Shell & environment knowledge (fish-first, but shell-agnostic where noted)

Hard-won facts about how Claude Code gets its environment on Leo's machines. Apply the fish
sections only when the machine's login shell is fish.

## The inheritance model (all shells)

Claude Code's Bash tool does NOT re-source shell profiles per command. At startup it snapshots
the environment of the shell that **launched `claude`** (see `~/.claude/shell-snapshots/`), and
Bash-tool sessions run a POSIX shell (zsh/bash) initialized from that snapshot. Consequences:

- If Leo launches `claude` from fish, the harness inherits fish's full PATH/env — fish config
  IS the harness config. Nothing extra needed.
- Env changes made AFTER launch (e.g. `fish_add_path`) are invisible until Claude Code restarts.
  **Diagnosis rule: tool works in Leo's terminal but "MISSING" in the Bash tool → restart the
  Claude session.**
- **Never switch the Bash tool or hook wrappers to fish** — they emit POSIX syntax; fish is
  intentionally not POSIX. Environment parity, not shell-swapping, is the goal.

## Hooks & absolute paths

Hook commands run via `sh` with the harness process env. Portable pattern (used by the
settings fragment): `sh -c 'python3 "$HOME"/.claude/hooks/<hook>.py; ...'` — `$HOME` expands at
execution. The statusLine command does not get this treatment reliably → always configure it
with a rendered absolute path (`command -v ccstatusline`).

## Package-manager global bins

- **fish**: `fish_add_path -U <bin-dir>` (universal variable, persists, fish-only). E.g. pnpm:
  `fish_add_path -U ~/Library/pnpm/bin`.
- **zsh parity** (harmless belt-and-braces; also covers zsh-launched contexts) — `~/.zprofile`:
  ```sh
  export PNPM_HOME="$HOME/Library/pnpm"
  export PATH="$PNPM_HOME/bin:$PNPM_HOME:$PATH"
  ```
  (Adapt for yarn/npm global dirs per the machine's PM choice.)
- **pnpm gotcha**: `pnpm setup` inside a project directory may execute a *project script named
  "setup"* instead of pnpm's builtin. Run it from `$HOME`.

## macOS quirks encountered

- `/var` is `/private/var`; temp dirs (`/var/folders`, `/private/tmp`) are legitimate workspaces
  (bash-guard exempts them).
- Homebrew on ARM lives at `/opt/homebrew/bin` — usually already on PATH via the launching
  shell; CLIs installed there (codex, opencode) are safe to reference absolutely in seat argv
  if PATH proves unreliable on a machine.
