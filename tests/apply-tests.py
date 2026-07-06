#!/usr/bin/env python3
"""apply.py primitives battery — runs everything against a TEMP HOME so the real machine is
never touched. Covers: fresh apply, idempotency, conflict refusal, forced override, backup,
merge semantics, ownership round-trip, owned removal, unowned-removal refusal, verify."""
import json
import os
import shutil
import subprocess
import tempfile

REPO_TOOLS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "tools", "apply.py")
TMP = tempfile.mkdtemp(prefix="leos-apply-test-")
FAKE_HOME = os.path.join(TMP, "home")
FIX_REPO = os.path.join(TMP, "repo")
ENV = dict(os.environ, HOME=FAKE_HOME)


def apply_py(*args):
    r = subprocess.run(["python3", REPO_TOOLS, *args], capture_output=True, text=True, env=ENV)
    try:
        return r.returncode, json.loads(r.stdout)
    except json.JSONDecodeError:
        return r.returncode, {"raw": r.stdout, "err": r.stderr}


def case(name, ok):
    print(f"{'PASS' if ok else 'FAIL'} [{name}]")
    return ok


# fixture repo: one copy item, one merge-json item
os.makedirs(f"{FIX_REPO}/payload", exist_ok=True)
os.makedirs(FAKE_HOME, exist_ok=True)
open(f"{FIX_REPO}/VERSION", "w").write("1\n")
open(f"{FIX_REPO}/payload/tool.py", "w").write("print('v1')\n")
json.dump({"permissions": {"deny": ["Read(**/.env)"]}, "newKey": "ours"},
          open(f"{FIX_REPO}/payload/frag.json", "w"))
json.dump({"items": [
    {"src": "payload/tool.py", "dest": "~/.claude/hooks/tool.py", "strategy": "copy", "since": 1},
    {"src": "payload/frag.json", "dest": "~/.claude/settings.json", "strategy": "merge-json", "since": 1},
], "removed": []}, open(f"{FIX_REPO}/manifest.json", "w"))

# pre-existing user settings with their own content + one array entry
os.makedirs(f"{FAKE_HOME}/.claude", exist_ok=True)
json.dump({"permissions": {"deny": ["Read(their-secret)"]}, "theirKey": True},
          open(f"{FAKE_HOME}/.claude/settings.json", "w"))

fails = 0
code, plan = apply_py("plan", "--repo", FIX_REPO)
fails += not case("plan-runs", code == 0 and plan["installedVersion"] == 0)

code, bk = apply_py("backup", "--repo", FIX_REPO)
fails += not case("backup-copies-existing", code == 0 and bk["copied"] == ["~/.claude/settings.json"])

code, res = apply_py("apply", "--repo", FIX_REPO)
merged = json.load(open(f"{FAKE_HOME}/.claude/settings.json"))
fails += not case("apply-fresh", code == 0 and len(res["applied"]) == 2)
fails += not case("merge-unions-arrays",
                  set(merged["permissions"]["deny"]) == {"Read(their-secret)", "Read(**/.env)"})
fails += not case("merge-preserves-theirs", merged["theirKey"] is True and merged["newKey"] == "ours")

code, res = apply_py("apply", "--repo", FIX_REPO)
fails += not case("idempotent-reapply", code == 0 and res["applied"] == [] and res["refused"] == [])

code, v = apply_py("verify", "--repo", FIX_REPO)
fails += not case("verify-green", code == 0 and v["ok"])

# conflict: user edits our copy-owned file offline... simulate unowned by changing content + profile mismatch
open(f"{FAKE_HOME}/.claude/hooks/tool.py", "w").write("print('user hacked')\n")
profile = json.load(open(f"{FAKE_HOME}/.claude/leos-claude.json"))
profile["owned"]["~/.claude/hooks/tool.py"]["sha"] = "not-a-real-hash"
json.dump(profile, open(f"{FAKE_HOME}/.claude/leos-claude.json", "w"))
code, res = apply_py("apply", "--repo", FIX_REPO)
fails += not case("conflict-refused", code == 1 and res["refused"])
code, res = apply_py("apply", "--repo", FIX_REPO, "--force-dest", "~/.claude/hooks/tool.py")
fails += not case("forced-override", code == 0 and "~/.claude/hooks/tool.py" in res["applied"])

# scalar conflict in settings: user sets newKey to their own value
merged = json.load(open(f"{FAKE_HOME}/.claude/settings.json"))
merged["newKey"] = "theirs-now"
json.dump(merged, open(f"{FAKE_HOME}/.claude/settings.json", "w"))
code, res = apply_py("apply", "--repo", FIX_REPO)
fails += not case("settings-scalar-conflict-refused", code == 1 and res["refused"])

# owned removal + unowned refusal
code, res = apply_py("remove", "--dest", "~/.claude/hooks/tool.py")
fails += not case("owned-removal", code == 0 and res["removed"])
open(f"{FAKE_HOME}/.claude/hooks/tool.py", "w").write("print('recreated by user')\n")
code, res = apply_py("remove", "--dest", "~/.claude/hooks/tool.py")
fails += not case("unowned-removal-refused", code == 1 and not res["removed"])

# expanded-absolute-path removal must resolve the ~-form ownership key (shells expand ~)
json.dump({"items": [{"src": "payload/tool.py", "dest": "~/.claude/hooks/tool2.py",
                      "strategy": "copy", "since": 1}], "removed": []},
          open(f"{FIX_REPO}/manifest.json", "w"))
apply_py("apply", "--repo", FIX_REPO)
code, res = apply_py("remove", "--dest", f"{FAKE_HOME}/.claude/hooks/tool2.py")
fails += not case("remove-expanded-path", code == 0 and res["removed"])

code, res = apply_py("record", "--repo", FIX_REPO, "--version", "1", "--tag", "v1")
profile = json.load(open(f"{FAKE_HOME}/.claude/leos-claude.json"))
fails += not case("record-version", code == 0 and profile["version"] == 1 and profile["tag"] == "v1")
fails += not case("record-abspath", os.path.isabs(profile["repo"]))

# --- fresh slate for the dict-array phase (isolate from conflict-test leftovers) ---
json.dump({}, open(f"{FAKE_HOME}/.claude/settings.json", "w"))
profile = json.load(open(f"{FAKE_HOME}/.claude/leos-claude.json"))
profile["owned"].pop("~/.claude/settings.json", None)
json.dump(profile, open(f"{FAKE_HOME}/.claude/leos-claude.json", "w"))

# dict-array upgrade: a changed owned hook entry must REPLACE, not duplicate
hook_v1 = {"matcher": "Bash", "hooks": [{"type": "command", "command": "guard", "timeout": 10}]}
hook_v2 = {"matcher": "Bash", "hooks": [{"type": "command", "command": "guard", "timeout": 15}]}
json.dump({"hooks": {"PreToolUse": [hook_v1]}}, open(f"{FIX_REPO}/payload/frag.json", "w"))
json.dump({"items": [{"src": "payload/frag.json", "dest": "~/.claude/settings.json",
                      "strategy": "merge-json", "since": 1}], "removed": []},
          open(f"{FIX_REPO}/manifest.json", "w"))
apply_py("apply", "--repo", FIX_REPO)
json.dump({"hooks": {"PreToolUse": [hook_v2]}}, open(f"{FIX_REPO}/payload/frag.json", "w"))
code, res = apply_py("apply", "--repo", FIX_REPO)
merged = json.load(open(f"{FAKE_HOME}/.claude/settings.json"))
entries = merged["hooks"]["PreToolUse"]
fails += not case("dict-array-replaces-not-duplicates",
                  code == 0 and entries == [hook_v2])

# user-edited owned dict element -> conflict, not silent overwrite
merged["hooks"]["PreToolUse"] = [{"matcher": "Bash", "hooks": [{"type": "command", "command": "user-custom", "timeout": 99}]}]
json.dump(merged, open(f"{FAKE_HOME}/.claude/settings.json", "w"))
json.dump({"hooks": {"PreToolUse": [hook_v1]}}, open(f"{FIX_REPO}/payload/frag.json", "w"))
code, res = apply_py("apply", "--repo", FIX_REPO)
fails += not case("user-edited-owned-element-conflict", code == 1 and res["refused"])

# manifest dest escaping HOME must be refused hard
json.dump({"items": [{"src": "payload/tool.py", "dest": "~/../../etc/evil", "strategy": "copy",
                      "since": 1}], "removed": []}, open(f"{FIX_REPO}/manifest.json", "w"))
open(f"{FIX_REPO}/payload/tool.py", "w").write("x")
code, res = apply_py("plan", "--repo", FIX_REPO)
fails += not case("traversal-dest-refused", code != 0)

# ownership backfill: identical pre-existing file gets adopted on apply
json.dump({"items": [{"src": "payload/tool.py", "dest": "~/.claude/hooks/tool3.py",
                      "strategy": "copy", "since": 1}], "removed": []},
          open(f"{FIX_REPO}/manifest.json", "w"))
open(f"{FIX_REPO}/payload/tool.py", "w").write("same content\n")
os.makedirs(f"{FAKE_HOME}/.claude/hooks", exist_ok=True)
open(f"{FAKE_HOME}/.claude/hooks/tool3.py", "w").write("same content\n")
code, res = apply_py("apply", "--repo", FIX_REPO)
profile = json.load(open(f"{FAKE_HOME}/.claude/leos-claude.json"))
fails += not case("ownership-backfill", code == 0 and "~/.claude/hooks/tool3.py" in profile["owned"])

# backup covers removal targets
json.dump({"items": [], "removed": [{"dest": "~/.claude/hooks/tool3.py"}]},
          open(f"{FIX_REPO}/manifest.json", "w"))
code, bk = apply_py("backup", "--repo", FIX_REPO)
fails += not case("backup-covers-removals", code == 0 and "~/.claude/hooks/tool3.py" in bk["copied"])

# merge-settings primitive: adds keys, unions arrays, records ownership union
frag2 = f"{TMP}/allow-frag.json"
json.dump({"permissions": {"allow": ["Bash(pnpm test:*)"]}}, open(frag2, "w"))
code, res = apply_py("merge-settings", "--fragment", frag2)
merged = json.load(open(f"{FAKE_HOME}/.claude/settings.json"))
profile = json.load(open(f"{FAKE_HOME}/.claude/leos-claude.json"))
owned_extra = profile["owned"]["~/.claude/settings.json"].get("extraValues", {})
fails += not case("merge-settings-applies",
                  code == 0 and "Bash(pnpm test:*)" in merged["permissions"]["allow"])
fails += not case("merge-settings-ownership-union",
                  "Bash(pnpm test:*)" in owned_extra.get("permissions", {}).get("allow", []))

# merge-json dest must never be file-removed
code, res = apply_py("remove", "--dest", "~/.claude/settings.json")
fails += not case("merge-json-remove-refused", code == 1 and not res["removed"]
                  and "fragment" in res["reason"])

# missing VERSION -> clean structured error, not a traceback
os.remove(f"{FIX_REPO}/VERSION")
code, res = apply_py("plan", "--repo", FIX_REPO)
fails += not case("missing-version-clean-error", code == 1 and "error" in res)

# --- fresh slate for the retire phase ---
json.dump({}, open(f"{FAKE_HOME}/.claude/settings.json", "w"))
profile = json.load(open(f"{FAKE_HOME}/.claude/leos-claude.json"))
profile["owned"].pop("~/.claude/settings.json", None)
json.dump(profile, open(f"{FAKE_HOME}/.claude/leos-claude.json", "w"))

# R1: fragment shrink retires owned key
os.makedirs(f"{FIX_REPO}/payload", exist_ok=True)
open(f"{FIX_REPO}/VERSION", "w").write("1\n")
json.dump({"a": 1, "b": {"x": True}}, open(f"{FIX_REPO}/payload/frag.json", "w"))
json.dump({"items": [{"src": "payload/frag.json", "dest": "~/.claude/settings.json",
                      "strategy": "merge-json", "since": 1}], "removed": []},
          open(f"{FIX_REPO}/manifest.json", "w"))
apply_py("apply", "--repo", FIX_REPO)
json.dump({"a": 1}, open(f"{FIX_REPO}/payload/frag.json", "w"))  # v2 drops b
code, res = apply_py("apply", "--repo", FIX_REPO)
merged = json.load(open(f"{FAKE_HOME}/.claude/settings.json"))
fails += not case("fragment-shrink-retires-key", code == 0 and "b" not in merged and merged.get("a") == 1)

# R1b: user-modified retired key -> conflict not deletion
json.dump({"a": 1, "c": "ours"}, open(f"{FIX_REPO}/payload/frag.json", "w"))
apply_py("apply", "--repo", FIX_REPO)
merged = json.load(open(f"{FAKE_HOME}/.claude/settings.json")); merged["c"] = "user-changed"
json.dump(merged, open(f"{FAKE_HOME}/.claude/settings.json", "w"))
json.dump({"a": 1}, open(f"{FIX_REPO}/payload/frag.json", "w"))
code, res = apply_py("apply", "--repo", FIX_REPO)
fails += not case("retire-user-modified-conflicts", code == 1 and res["refused"])
merged["c"] = "ours"; json.dump(merged, open(f"{FAKE_HOME}/.claude/settings.json", "w"))
apply_py("apply", "--repo", FIX_REPO)  # clean retire to reset state

# R2: user pre-applied exactly the new hook value -> no conflict, ownership refreshed
hook_v1 = {"matcher": "Bash", "hooks": [{"type": "command", "command": "g", "timeout": 10}]}
hook_v2 = {"matcher": "Bash", "hooks": [{"type": "command", "command": "g", "timeout": 15}]}
json.dump({"hooks": {"PreToolUse": [hook_v1]}}, open(f"{FIX_REPO}/payload/frag.json", "w"))
apply_py("apply", "--repo", FIX_REPO)
merged = json.load(open(f"{FAKE_HOME}/.claude/settings.json"))
merged["hooks"]["PreToolUse"] = [hook_v2]  # user pre-applies v2 manually
json.dump(merged, open(f"{FAKE_HOME}/.claude/settings.json", "w"))
json.dump({"hooks": {"PreToolUse": [hook_v2]}}, open(f"{FIX_REPO}/payload/frag.json", "w"))
code, res = apply_py("apply", "--repo", FIX_REPO)
merged = json.load(open(f"{FAKE_HOME}/.claude/settings.json"))
profile = json.load(open(f"{FAKE_HOME}/.claude/leos-claude.json"))
fails += not case("pre-applied-value-no-conflict",
                  code == 0 and merged["hooks"]["PreToolUse"] == [hook_v2])
fails += not case("pre-applied-ownership-refreshed",
                  profile["owned"]["~/.claude/settings.json"]["values"]["hooks"]["PreToolUse"] == [hook_v2])

# namespace isolation: manifest re-apply must never retire machine-added (merge-settings) values
json.dump({}, open(f"{FAKE_HOME}/.claude/settings.json", "w"))
profile = json.load(open(f"{FAKE_HOME}/.claude/leos-claude.json"))
profile["owned"].pop("~/.claude/settings.json", None)
json.dump(profile, open(f"{FAKE_HOME}/.claude/leos-claude.json", "w"))
json.dump({"permissions": {"deny": ["Read(**/.env)"]}, "hooks": {"Stop": [{"h": 1}]}},
          open(f"{FIX_REPO}/payload/frag.json", "w"))
json.dump({"items": [{"src": "payload/frag.json", "dest": "~/.claude/settings.json",
                      "strategy": "merge-json", "since": 1}], "removed": []},
          open(f"{FIX_REPO}/manifest.json", "w"))
apply_py("apply", "--repo", FIX_REPO)                       # manifest v1
mfrag = f"{TMP}/machine-frag.json"
json.dump({"permissions": {"allow": ["Bash(pnpm test:*)"]}}, open(mfrag, "w"))
apply_py("merge-settings", "--fragment", mfrag)             # machine addition
code, res = apply_py("apply", "--repo", FIX_REPO)           # manifest re-apply (idempotent)
merged = json.load(open(f"{FAKE_HOME}/.claude/settings.json"))
fails += not case("manifest-reapply-preserves-machine-values",
                  code == 0 and merged["permissions"].get("allow") == ["Bash(pnpm test:*)"])
# v2 drops hooks.Stop from manifest fragment: manifest key retires, machine values survive
json.dump({"permissions": {"deny": ["Read(**/.env)"]}}, open(f"{FIX_REPO}/payload/frag.json", "w"))
code, res = apply_py("apply", "--repo", FIX_REPO)
merged = json.load(open(f"{FAKE_HOME}/.claude/settings.json"))
fails += not case("v2-retires-manifest-key-keeps-machine",
                  code == 0 and "Stop" not in merged.get("hooks", {})
                  and merged["permissions"].get("allow") == ["Bash(pnpm test:*)"])

shutil.rmtree(TMP, ignore_errors=True)
print(f"\n{'ALL PASS' if fails == 0 else f'{fails} FAILURES'}")
raise SystemExit(1 if fails else 0)
