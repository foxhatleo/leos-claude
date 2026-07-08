# Shell & environment knowledge (zsh-first; bash only as a fallback)

Hard-won facts about how Claude Code gets its environment on Leo's machines. The standard shell
is **zsh** — fall back to `bash` only on a machine where zsh is unavailable. The shell-specific
notes below are written for zsh; bash differences are called out.

## The inheritance model (all shells)

Claude Code's Bash tool does NOT re-source shell profiles per command. At startup it snapshots
the environment of the shell that **launched `claude`** (see `~/.claude/shell-snapshots/`), and
Bash-tool sessions run a POSIX shell (zsh, or bash where zsh is absent) initialized from that
snapshot. Consequences:

- The shell that launches `claude` supplies the harness's PATH/env — keep its login config
  correct (zsh: `~/.zprofile` / `~/.zshrc`; bash: `~/.bash_profile` / `~/.profile`) and it IS
  the harness config. Nothing extra needed.
- Env changes made AFTER launch (e.g. editing `~/.zprofile`) are invisible until Claude Code
  restarts. **Diagnosis rule: tool works in Leo's terminal but "MISSING" in the Bash tool →
  restart the Claude session.**
- The Bash tool and hook wrappers emit POSIX syntax and run under zsh/bash — parity with the
  login shell, not shell-swapping, is the goal.

## Hooks & absolute paths

Hook commands run via `sh` with the harness process env. Portable pattern (used by the
settings fragment): `sh -c 'python3 "$HOME"/.claude/hooks/<hook>.py; ...'` — `$HOME` expands at
execution. The statusLine command does not get this treatment reliably → always configure it
with a rendered absolute path (`command -v ccstatusline`).

## Package-manager global bins

- **zsh** (standard) — add the global-bin dir in `~/.zprofile`:
  ```sh
  export PNPM_HOME="$HOME/Library/pnpm"
  export PATH="$PNPM_HOME/bin:$PNPM_HOME:$PATH"
  ```
  (Adapt for yarn/npm global dirs per the machine's PM choice.)
- **bash** (fallback only) — the same `export` lines in `~/.bash_profile` (or `~/.profile`).
- **pnpm gotcha**: `pnpm setup` inside a project directory may execute a *project script named
  "setup"* instead of pnpm's builtin. Run it from `$HOME`.

## macOS quirks encountered

- `/var` is `/private/var`; temp dirs (`/var/folders`, `/private/tmp`) are legitimate workspaces
  (bash-guard exempts them).
- Homebrew on ARM lives at `/opt/homebrew/bin` — usually already on PATH via the launching
  shell; CLIs installed there (codex, opencode) are safe to reference absolutely in seat argv
  if PATH proves unreliable on a machine.
