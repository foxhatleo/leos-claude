#!/usr/bin/env python3
"""bash-guard battery — portable. Run after install (hook at ~/.claude/hooks/bash-guard.py).
Covers: catastrophic classes, both Codex-review bypass rounds, false-positive fixes,
guard-config machine extras, fail-open guarantees."""
import json
import os
import subprocess
import tempfile

HOME = os.path.expanduser("~")
GUARD = os.path.join(HOME, ".claude", "hooks", "bash-guard.py")
WRAP = f'python3 "{GUARD}"; ec=$?; [ "$ec" = 43 ] && exit 2; exit 0'
PROJ = tempfile.mkdtemp(prefix="guard-proj-")  # a plausible cwd for relative targets

# guard-config fixture: "projects" as a machine-extra toplevel dir
CFG = tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False)
json.dump({"homeToplevel": ["projects"]}, CFG)
CFG.close()

BLOCK = [
    ("incident-class", "rm -rf tests/ patches/ ~/"),
    ("root", "rm -rf /"), ("home-tilde", "rm -rf ~"), ("fr-home-var", "rm -fr $HOME"),
    ("home-glob", "rm -rf ~/*"), ("braces-home", "rm -rf ${HOME}/"),
    ("home-toplevel", f"rm -rf {HOME}/Documents"),
    ("toplevel-contents", "rm -rf ~/Documents/*"),
    ("long-options", "rm --recursive --force /"),
    ("bin-rm", "/bin/rm -rf /"), ("command-rm", "command rm -rf ~"),
    ("env-rm", "env rm -rf $HOME"), ("sudo-n-rm", "sudo -n rm -rf /"),
    ("sudo-u-operand", f"sudo -u root rm -rf {HOME}"),
    ("doas-u", "doas -u root rm -rf /"), ("env-u-home", "env -u HOME rm -rf /"),
    ("nice-n19", "nice -n 19 rm -rf /"),
    ("var-assign", "FOO=bar rm -rf /"), ("multi-assign", f"A=1 B=2 rm -rf {HOME}"),
    ("quoted-home", 'rm -rf "$HOME"/Documents'),
    ("users-dir", "rm -rf /Users"), ("users-glob", "rm -rf /Users/*"),
    ("linux-home", "rm -rf /home"), ("root-home", "rm -rf /root"), ("dev-dir", "rm -rf /dev"),
    ("system-sub", "sudo rm -rf /usr/lib"),
    ("private-var", "rm -rf /private/var"), ("private-var-db", "rm -rf /private/var/db"),
    ("tilde-user", "rm -rf ~root"),
    ("bare-cd-dot", "cd && rm -rf ."), ("bare-cd-glob", "cd; rm -rf *"),
    ("cd-dashdash", f"cd -- {HOME} && rm -rf ."), ("cd-P", f"cd -P {HOME} && rm -rf ."),
    ("cd-home-glob", "cd ~ && rm -rf ./*"), ("cd-root-usr", "cd / && rm -rf usr"),
    ("xargs-home", 'printf "$HOME\\n" | xargs rm -rf'),
    ("xargs-0", "printf '%s\\0' ~ | xargs -0 rm -rf"),
    ("xargs-I", "printf %s ~ | xargs -I{} rm -rf {}"),
    ("xargs-longopt", "printf %s ~ | xargs --no-run-if-empty rm -rf"),
    ("dd-device", "dd if=/dev/zero of=/dev/disk0"),
    ("assign-dd", "FOO=bar dd of=/dev/disk1 if=/dev/zero"),
    ("mkfs-cmd", "mkfs.ext4 /dev/sda1"), ("assign-mkfs", "FOO=bar mkfs /dev/disk1"),
    ("no-preserve-root", "rm -rf --no-preserve-root /x"),
]
ALLOW = [
    ("node_modules", "rm -rf node_modules"),
    ("project-dirs", "rm -rf ./dist build/"),
    ("deep-relative", "rm -rf packages/app/.next"),
    ("tmp-abs", f"rm -rf {tempfile.gettempdir()}/some-scratch"),
    ("single-file", "rm file.txt"), ("git-rm", "git rm -r old/"),
    ("echo-mention", "echo rm and -rf are flags"),
    ("rg-mkfs", "rg mkfs docs"), ("git-grep-mkfs", "git grep mkfs"),
    ("sed-mkfs-doc", "sed -n 1,20p docs/mkfs.md"), ("echo-dd", "echo dd of=/dev/disk2"),
    ("xargs-find-clean", "find . -name node_modules -type d | xargs rm -rf"),
    ("xargs-scoped-ref", 'echo "$HOME"; find . -name build | xargs rm -rf'),
    ("dot-in-project", "rm -rf ."),
    ("cd-tmp-clean", f"cd {PROJ} && rm -rf .next"),
    ("env-assign-build", "NODE_ENV=production pnpm build"),
    ("sudo-install", "sudo apt-get install jq"),
    ("home-deep-subdir", f"rm -rf {HOME}/projects/someproj/node_modules"),
]


def run(cmd, cwd=PROJ, env=None):
    payload = json.dumps({"tool_name": "Bash", "tool_input": {"command": cmd}, "cwd": cwd})
    return subprocess.run(["sh", "-c", WRAP], input=payload, capture_output=True,
                          text=True, env=env).returncode


fails = 0
base_env = dict(os.environ, CLAUDE_GUARD_CONFIG="/nonexistent-guard-config")
for want, cases in ((2, BLOCK), (0, ALLOW)):
    for name, cmd in cases:
        got = run(cmd, env=base_env)
        ok = got == want
        fails += (not ok)
        print(f"{'PASS' if ok else 'FAIL'} [{name}] exit={got} want={want}")

# guard-config: machine extra dir becomes critical only WITH the config
cfg_env = dict(os.environ, CLAUDE_GUARD_CONFIG=CFG.name)
got = run("rm -rf ~/projects", env=base_env)
fails += not (got == 0)
print(f"{'PASS' if got == 0 else 'FAIL'} [config-absent-allows] exit={got} want=0")
got = run("rm -rf ~/projects", env=cfg_env)
fails += not (got == 2)
print(f"{'PASS' if got == 2 else 'FAIL'} [config-present-blocks] exit={got} want=2")

# fail-open + unknown-cwd conservatism
r = subprocess.run(["sh", "-c", WRAP], input="garbage", capture_output=True, text=True)
fails += not (r.returncode == 0)
print(f"{'PASS' if r.returncode == 0 else 'FAIL'} [garbage-stdin] exit={r.returncode} want=0")
payload = json.dumps({"tool_name": "Bash", "tool_input": {"command": "rm -rf ."}})
r = subprocess.run(["sh", "-c", WRAP], input=payload, capture_output=True, text=True)
fails += not (r.returncode == 2)
print(f"{'PASS' if r.returncode == 2 else 'FAIL'} [dot-no-cwd-blocks] exit={r.returncode} want=2")
r = subprocess.run(["sh", "-c", 'python3 /nonexistent.py; ec=$?; [ "$ec" = 43 ] && exit 2; exit 0'],
                   input="{}", capture_output=True, text=True)
fails += not (r.returncode == 0)
print(f"{'PASS' if r.returncode == 0 else 'FAIL'} [missing-script-failopen] exit={r.returncode} want=0")

os.unlink(CFG.name)
print(f"\n{'ALL PASS' if fails == 0 else f'{fails} FAILURES'}")
raise SystemExit(1 if fails else 0)
