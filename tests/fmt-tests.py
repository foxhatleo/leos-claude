#!/usr/bin/env python3
"""format-on-edit routing battery — portable, uses fake tool shims (no real toolchains needed).
Run after install (hook at ~/.claude/hooks/format-on-edit.py)."""
import json
import os
import shutil
import stat
import subprocess

HOME = os.path.expanduser("~")
HOOK = os.path.join(HOME, ".claude", "hooks", "format-on-edit.py")
WRAP = f'python3 "{HOOK}"; ec=$?; [ "$ec" = 44 ] && exit 2; exit 0'
BASE = os.path.join(HOME, ".cache", "leos-claude-fmt-tests")  # must be under HOME (walk_up guard)


def shim(path, exit_code, output=""):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    log = path + ".log"
    with open(path, "w") as f:
        f.write(f'#!/bin/sh\necho "$@" >> "{log}"\n')
        if output:
            f.write(f'echo "{output}"\n')
        f.write(f"exit {exit_code}\n")
    os.chmod(path, os.stat(path).st_mode | stat.S_IEXEC)
    return log


def hook(file_path, env=None):
    payload = json.dumps({"tool_name": "Edit", "tool_input": {"file_path": file_path}})
    r = subprocess.run(["sh", "-c", WRAP], input=payload, capture_output=True, text=True, env=env)
    return r.returncode, r.stderr


def case(name, got, want, extra_ok=True):
    ok = got == want and extra_ok
    print(f"{'PASS' if ok else 'FAIL'} [{name}] exit={got} want={want}")
    return ok


fails = 0
shutil.rmtree(BASE, ignore_errors=True)  # fixed constant path under HOME, no shell

p = f"{BASE}/eslint-proj"; os.makedirs(p, exist_ok=True)
open(f"{p}/eslint.config.js", "w").write("export default []")
shim(f"{p}/node_modules/.bin/eslint", 1, "src/a.ts:1:1 error no-unused-vars")
open(f"{p}/a.ts", "w").write("let x = 1")
code, err = hook(f"{p}/a.ts")
fails += not case("eslint-feedback", code, 2, "no-unused-vars" in err)

p = f"{BASE}/biome-proj"; os.makedirs(p, exist_ok=True)
open(f"{p}/biome.json", "w").write("{}")
log = shim(f"{p}/node_modules/.bin/biome", 0)
open(f"{p}/b.ts", "w").write("let x = 1")
code, err = hook(f"{p}/b.ts")
fails += not case("biome-clean-silent", code, 0, os.path.exists(log))

p = f"{BASE}/prio-proj"; os.makedirs(p, exist_ok=True)
open(f"{p}/.oxfmtrc.json", "w").write("{}")
open(f"{p}/eslint.config.js", "w").write("export default []")
oxlog = shim(f"{p}/node_modules/.bin/oxfmt", 0)
eslog = shim(f"{p}/node_modules/.bin/eslint", 1, "should-not-run")
open(f"{p}/c.ts", "w").write("let x = 1")
code, err = hook(f"{p}/c.ts")
fails += not case("oxfmt-priority-same-dir", code, 0, os.path.exists(oxlog) and not os.path.exists(eslog))

# nearest config wins ACROSS families: child eslint beats parent oxfmt (Codex round-2 fix)
p = f"{BASE}/mono"; child = f"{p}/packages/app"; os.makedirs(child, exist_ok=True)
open(f"{p}/.oxfmtrc.json", "w").write("{}")
open(f"{child}/eslint.config.js", "w").write("export default []")
oxlog = shim(f"{p}/node_modules/.bin/oxfmt", 0)
eslog = shim(f"{p}/node_modules/.bin/eslint", 0)
open(f"{child}/d.ts", "w").write("let x = 1")
code, err = hook(f"{child}/d.ts")
fails += not case("nearest-config-cross-family", code, 0,
                  os.path.exists(eslog) and not os.path.exists(oxlog))

p = f"{BASE}/ruff-proj"; os.makedirs(p, exist_ok=True)
open(f"{p}/ruff.toml", "w").write("")
shim(f"{p}/.venv/bin/ruff", 1, "e.py:1:1 F401 unused import")
open(f"{p}/e.py", "w").write("import os")
code, err = hook(f"{p}/e.py")
fails += not case("ruff-feedback", code, 2, "F401" in err)

p = f"{BASE}/pylint-proj"; os.makedirs(p, exist_ok=True)
open(f"{p}/pyproject.toml", "w").write("[tool.pylint.main]\n")
shim(f"{p}/.venv/bin/pylint", 2, "f.py:1:0: E0602 undefined variable")
open(f"{p}/f.py", "w").write("print(y)")
code, err = hook(f"{p}/f.py")
fails += not case("pylint-feedback", code, 2, "E0602" in err)

p = f"{BASE}/nobin-proj"; os.makedirs(p, exist_ok=True)
open(f"{p}/biome.json", "w").write("{}")
open(f"{p}/g.ts", "w").write("let x = 1")
env = dict(os.environ, PATH="/usr/bin:/bin")
payload = json.dumps({"tool_name": "Edit", "tool_input": {"file_path": f"{p}/g.ts"}})
r = subprocess.run(["sh", "-c", WRAP], input=payload, capture_output=True, text=True, env=env)
fails += not case("missing-binary-silent", r.returncode, 0)

p = f"{BASE}/plain-proj"; os.makedirs(p, exist_ok=True)
open(f"{p}/h.ts", "w").write("let x = 1")
code, err = hook(f"{p}/h.ts")
fails += not case("no-config-silent", code, 0)

code, err = hook("/etc/hosts")
fails += not case("non-code-ext", code, 0)
r = subprocess.run(["sh", "-c", WRAP], input="garbage", capture_output=True, text=True)
fails += not case("garbage-stdin", r.returncode, 0)

shutil.rmtree(BASE, ignore_errors=True)
print(f"\n{'ALL PASS' if fails == 0 else f'{fails} FAILURES'}")
raise SystemExit(1 if fails else 0)
