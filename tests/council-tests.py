#!/usr/bin/env python3
"""Council engine battery — portable. Tests risk tiers + the Stop-hook flow against a scratch
git repo. Run after install (engine at ~/.claude/council/bin/council.py). Cleans up its own
council state dir afterwards."""
import json
import os
import shutil
import subprocess

HOME = os.path.expanduser("~")
BIN = os.path.join(HOME, ".claude", "council", "bin", "council.py")
WRAP = f'python3 "{BIN}" hook; ec=$?; [ "$ec" = 42 ] && exit 2; exit 0'
T = os.path.join(HOME, ".cache", "leos-claude-council-test")


def sh(cmd, cwd=T):
    # shell=True is safe here: every call site passes a hardcoded literal (git fixture
    # setup chains) — no user, file, or model-derived input ever reaches this helper.
    return subprocess.run(cmd, shell=True, cwd=cwd, capture_output=True, text=True)


def risk():
    r = sh(f'python3 "{BIN}" risk --json')
    return json.loads(r.stdout)


def hook():
    payload = json.dumps({"cwd": T})
    r = subprocess.run(["sh", "-c", WRAP], input=payload, capture_output=True, text=True)
    return r.returncode


def case(name, got, want):
    ok = got == want
    print(f"{'PASS' if ok else 'FAIL'} [{name}] got={got} want={want}")
    return ok


fails = 0
shutil.rmtree(T, ignore_errors=True)
os.makedirs(f"{T}/src/auth", exist_ok=True)
os.makedirs(f"{T}/src/utils", exist_ok=True)
os.makedirs(f"{T}/tests", exist_ok=True)
os.makedirs(f"{T}/docs", exist_ok=True)
sh("git init -q && git config user.email t@t && git config user.name t")
open(f"{T}/src/utils/math.js", "w").write("export function add(a, b) { return a + b }\n")
open(f"{T}/src/auth/login.js", "w").write("export function login(u, p) { return check(u, p) }\n")
open(f"{T}/tests/math.test.js", "w").write(
    'test("add", () => {\n  expect(add(1,2)).toBe(3)\n  expect(add(2,2)).toBe(4)\n  expect(add(0,0)).toBe(0)\n})\n')
open(f"{T}/docs/readme.md", "w").write("# readme\n")
sh("git add -A && git commit -qm init")

# tiers
open(f"{T}/docs/readme.md", "a").write("more docs\n")
fails += not case("docs-only-skip", risk()["tier"], "skip")
sh("git checkout -q .")
open(f"{T}/src/utils/math.js", "a").write("export function sub(a, b) { return a - b }\n")
fails += not case("small-util-low", risk()["tier"], "low")
sh("git checkout -q .")
open(f"{T}/src/auth/login.js", "a").write("export function logout() { session.token = null }\n")
fails += not case("small-auth-high", risk()["tier"], "high")
sh("git checkout -q .")
open(f"{T}/tests/math.test.js", "w").write('test("add", () => {\n  expect(add(1,2)).toBe(3)\n})\n')
fails += not case("assert-removal-elevated", risk()["tier"], "elevated")
sh("git checkout -q .")
with open(f"{T}/src/auth/login.js", "a") as f:
    for i in range(450):
        f.write(f"const p{i} = {i}\n")
fails += not case("auth-large-critical", risk()["tier"], "critical")
sh("git checkout -q .")

# hook flow
state_dir = subprocess.run(["python3", BIN, "state-dir"], cwd=T, capture_output=True,
                           text=True).stdout.strip()
shutil.rmtree(state_dir, ignore_errors=True)
open(f"{T}/src/auth/login.js", "a").write("export function f() { return token }\n")
fails += not case("nudge1", hook(), 2)
fails += not case("nudge2", hook(), 2)
fails += not case("loop-guard", hook(), 0)
shutil.rmtree(state_dir, ignore_errors=True)
sh(f'python3 "{BIN}" mark --checkpoint plan')
fails += not case("plan-marker-rejected", hook(), 2)
sh(f'python3 "{BIN}" mark --checkpoint impl')
fails += not case("impl-marker-honored", hook(), 0)
sh("git checkout -q .")

# kill switch + fail-open
open(f"{T}/.council-off", "w").write("")
open(f"{T}/src/auth/login.js", "a").write("export function g() { return token }\n")
fails += not case("council-off", hook(), 0)
os.remove(f"{T}/.council-off")
sh("git checkout -q .")
r = subprocess.run(["sh", "-c", WRAP], input="garbage", capture_output=True, text=True)
fails += not case("garbage-failopen", r.returncode, 0)

# cleanup
shutil.rmtree(state_dir, ignore_errors=True)
shutil.rmtree(T, ignore_errors=True)
print(f"\n{'ALL PASS' if fails == 0 else f'{fails} FAILURES'}")
raise SystemExit(1 if fails else 0)
