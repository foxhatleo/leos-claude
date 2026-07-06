#!/usr/bin/env python3
"""leos-claude apply tool — deterministic PRIMITIVES for install/migrate.

This is NOT an autonomous installer. The target machine's Claude drives the setup
interview conversationally (docs/SETUP.md) and uses these subcommands for every
mechanical write, so merges are deterministic, backed up, ownership-tracked, and
idempotent across machines. It never asks questions: on any conflict it REFUSES
and reports — the driving Claude resolves with the user and retries.

Subcommands:
  plan    --repo DIR                    Dry-run: per-manifest-item state + settings-merge preview (JSON).
  backup  --repo DIR                    Copy would-be-touched dests to ~/.claude/backups/leos-claude-<ts>/.
  apply   --repo DIR [--force-dest D]*  Apply copy + merge-json items; refuse on unowned conflicts.
  verify  --repo DIR                    Check installed state matches manifest + ownership. Exit 1 on drift.
  record  --repo DIR --version N --tag T [--answers-file F]   Update ~/.claude/leos-claude.json profile.
  remove  --dest PATH                   Remove an owned file (migration removals). Refuses if not owned.

Ownership: every applied item's dest + content sha256 (and for merge-json, the exact
owned key/value snapshot) is recorded in ~/.claude/leos-claude.json. apply/remove only
ever overwrite/delete content that matches an owned hash (or is missing); anything
else is a conflict → refuse (override per-dest with --force-dest after human approval).

Stdlib only. Fails loudly (this is not a hook). Writes only to manifest dests,
~/.claude/leos-claude.json, and the backup dir.
"""

import argparse
import hashlib
import json
import os
import shutil
import sys
import time

HOME = os.path.expanduser("~")
PROFILE = os.path.join(HOME, ".claude", "leos-claude.json")


def sha(path):
    try:
        with open(path, "rb") as f:
            return hashlib.sha256(f.read()).hexdigest()
    except FileNotFoundError:
        return None


def expand(dest):
    """Expand a manifest dest and REFUSE anything that escapes HOME (realpath kills
    ../ traversal and symlink tricks — a forked/corrupted manifest must not be able
    to write outside the user's home tree)."""
    path = os.path.realpath(os.path.expanduser(dest))
    home = os.path.realpath(HOME)
    if not (path == home or path.startswith(home + os.sep)):
        raise SystemExit(f"refusing dest outside HOME: {dest}")
    return path


def load_json(path, default):
    try:
        with open(path) as f:
            return json.load(f)
    except FileNotFoundError:
        return default


def load_manifest(repo):
    with open(os.path.join(repo, "manifest.json")) as f:
        return json.load(f)


def load_profile():
    return load_json(PROFILE, {"version": 0, "owned": {}, "answers": {}})


def save_profile(profile):
    os.makedirs(os.path.dirname(PROFILE), exist_ok=True)
    with open(PROFILE, "w") as f:
        json.dump(profile, f, indent=2, sort_keys=True)


# --- settings merge -----------------------------------------------------------

def _copy(obj):
    return json.loads(json.dumps(obj))


def merge_preview(fragment, current, owned_values, retire_missing=True, retire_snapshot=None):
    """Compute merge actions for a settings fragment.
    Returns (actions, conflicts). Arrays: union-dedup (append missing).
    Scalars/objects: set if absent; equal → noop; differing → conflict UNLESS the
    current value matches our previously-owned snapshot (then it's ours to update)."""
    actions, conflicts = [], []

    def walk(frag, cur, own, path):
        for k, v in frag.items():
            p = f"{path}.{k}" if path else k
            if k not in cur:
                actions.append({"op": "set", "path": p, "value": v})
            elif isinstance(v, list) and isinstance(cur[k], list):
                own_list = own.get(k) if isinstance(own.get(k), list) else []
                if own_list and any(isinstance(x, dict) for x in v + own_list):
                    # Ownership-aware element replacement: superseded owned entries are
                    # swapped out, never left to accumulate (e.g. hook entries across
                    # versions). Owned entries the user edited/removed → conflict.
                    lingering = [o for o in own_list if o in cur[k] and o not in v]
                    if all(x in cur[k] for x in v) and not lingering:
                        continue  # destination already satisfies the fragment — current
                    edited = [o for o in own_list if o not in cur[k] and o not in v]
                    if edited:
                        conflicts.append({"path": p, "ours": v,
                                          "theirs": "owned element(s) modified/removed by user",
                                          "detail": edited})
                        continue
                    superseded = [o for o in own_list if o in cur[k] and o not in v]
                    new_elems = [x for x in v if x not in cur[k]]
                    if superseded or new_elems:
                        actions.append({"op": "replace-elements", "path": p,
                                        "remove": superseded, "add": new_elems})
                else:
                    missing = [x for x in v if x not in cur[k]]
                    if missing:
                        actions.append({"op": "append", "path": p, "value": missing})
            elif isinstance(v, dict) and isinstance(cur[k], dict):
                walk(v, cur[k], own.get(k, {}) if isinstance(own.get(k), dict) else {}, p)
            elif cur[k] == v:
                pass
            elif own.get(k) == cur[k]:
                actions.append({"op": "update-owned", "path": p, "value": v, "was": cur[k]})
            else:
                conflicts.append({"path": p, "ours": v, "theirs": cur[k]})

    def retire(frag, cur, own, path):
        """Owned keys absent from the new fragment get retired (the documented way to
        remove settings across versions). User-modified values → conflict, not deletion."""
        for k, ov in own.items():
            p = f"{path}.{k}" if path else k
            if k in frag:
                if isinstance(ov, dict) and isinstance(frag.get(k), dict) and isinstance(cur.get(k), dict):
                    retire(frag[k], cur[k], ov, p)
                continue
            if k not in cur:
                continue  # already gone
            if cur[k] == ov:
                actions.append({"op": "retire", "path": p})
            elif isinstance(ov, list) and isinstance(cur[k], list):
                present = [o for o in ov if o in cur[k]]
                if present:
                    actions.append({"op": "replace-elements", "path": p,
                                    "remove": present, "add": []})
            else:
                conflicts.append({"path": p, "ours": "<retired in new version>",
                                  "theirs": cur[k]})

    walk(fragment, current, owned_values, "")
    if retire_missing:  # manifest fragments are authoritative-complete; additive
        # Retirement compares ONLY against the manifest-owned snapshot — machine-added
        # values (merge-settings extraValues) must never be retired by a manifest apply.
        retire(fragment, current,
               retire_snapshot if retire_snapshot is not None else owned_values, "")
    return actions, conflicts


def apply_actions(current, actions):
    for a in actions:
        keys = a["path"].split(".")
        node = current
        for k in keys[:-1]:
            node = node.setdefault(k, {})
        leaf = keys[-1]
        if a["op"] == "retire":
            node.pop(leaf, None)
            continue
        if a["op"] == "append":
            node.setdefault(leaf, [])
            node[leaf] = node[leaf] + [x for x in a["value"] if x not in node[leaf]]
        elif a["op"] == "replace-elements":
            node.setdefault(leaf, [])
            node[leaf] = [x for x in node[leaf] if x not in a["remove"]] \
                + [x for x in a["add"] if x not in node[leaf]]
        else:
            node[leaf] = a["value"]
    return current


# --- item handling -------------------------------------------------------------

def item_state(item, repo, profile):
    src = os.path.join(repo, item["src"])
    dest = expand(item["dest"])
    if item["strategy"] == "copy":
        s_src, s_dest = sha(src), sha(dest)
        owned = profile["owned"].get(item["dest"], {}).get("sha")
        if s_dest is None:
            return "missing"
        if s_dest == s_src:
            return "current"
        if s_dest == owned:
            return "owned-outdated"
        return "conflict"
    if item["strategy"] == "merge-json":
        fragment = load_json(src, {})
        current = load_json(dest, {})
        entry = profile["owned"].get(item["dest"], {})
        walk_own = _deep_union(_copy(entry.get("values", {})), entry.get("extraValues", {}))
        actions, conflicts = merge_preview(fragment, current, walk_own,
                                           retire_snapshot=entry.get("values", {}))
        if conflicts:
            return "conflict"
        return "current" if not actions else ("missing" if not os.path.exists(dest) else "owned-outdated")
    return "generate"  # documented machine-local items; apply.py never touches them


def cmd_plan(args):
    repo = os.path.abspath(args.repo)
    manifest, profile = load_manifest(repo), load_profile()
    try:
        repo_version = open(os.path.join(repo, "VERSION")).read().strip()
    except FileNotFoundError:
        print(json.dumps({"error": "missing VERSION file — is this a complete leos-claude clone?"}))
        return 1
    report = {"repoVersion": repo_version,
              "installedVersion": profile.get("version", 0), "items": []}
    for item in manifest["items"]:
        entry = {"dest": item["dest"], "strategy": item["strategy"],
                 "state": item_state(item, repo, profile)}
        if item["strategy"] == "merge-json":
            fragment = load_json(os.path.join(repo, item["src"]), {})
            current = load_json(expand(item["dest"]), {})
            oe = profile["owned"].get(item["dest"], {})
            walk_own = _deep_union(_copy(oe.get("values", {})), oe.get("extraValues", {}))
            entry["actions"], entry["conflicts"] = merge_preview(
                fragment, current, walk_own, retire_snapshot=oe.get("values", {}))
        report["items"].append(entry)
    report["removals"] = [r for r in manifest.get("removed", [])
                          if os.path.exists(expand(r["dest"]))]
    print(json.dumps(report, indent=2))
    return 0


def cmd_backup(args):
    repo = os.path.abspath(args.repo)
    manifest = load_manifest(repo)
    ts = time.strftime("%Y%m%d-%H%M%S")
    bdir = os.path.join(HOME, ".claude", "backups", f"leos-claude-{ts}")
    copied = []
    targets = [i["dest"] for i in manifest["items"]] + [r["dest"] for r in manifest.get("removed", [])]
    for tdest in targets:
        dest = expand(tdest)
        if os.path.exists(dest):
            rel = tdest.replace("~/", "").replace("/", "__")
            os.makedirs(bdir, exist_ok=True)
            shutil.copy2(dest, os.path.join(bdir, rel))
            copied.append(tdest)
    print(json.dumps({"backupDir": bdir if copied else None, "copied": copied}, indent=2))
    return 0


def cmd_apply(args):
    repo = os.path.abspath(args.repo)
    manifest, profile = load_manifest(repo), load_profile()
    force = set(args.force_dest or [])
    applied, refused = [], []

    for item in manifest["items"]:
        state = item_state(item, repo, profile)
        src, dest = os.path.join(repo, item["src"]), expand(item["dest"])
        if item["strategy"] == "copy":
            if state == "current":
                if item["dest"] not in profile["owned"]:  # backfill: identical file pre-existed
                    profile["owned"][item["dest"]] = {"sha": sha(dest), "src": item["src"]}
                    applied.append(f"owned-backfill:{item['dest']}")
                continue
            if state == "conflict" and item["dest"] not in force:
                refused.append({"dest": item["dest"], "reason": "exists with unowned content"})
                continue
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            shutil.copy2(src, dest)
            profile["owned"][item["dest"]] = {"sha": sha(dest), "src": item["src"]}
            applied.append(item["dest"])
        elif item["strategy"] == "merge-json":
            fragment = load_json(src, {})
            current = load_json(dest, {})
            oe = profile["owned"].get(item["dest"], {})
            extra = oe.get("extraValues", {})
            walk_own = _deep_union(_copy(oe.get("values", {})), extra)
            actions, conflicts = merge_preview(fragment, current, walk_own,
                                               retire_snapshot=oe.get("values", {}))
            if conflicts and item["dest"] not in force:
                refused.append({"dest": item["dest"], "reason": "merge conflicts", "conflicts": conflicts})
                continue
            if not actions and not conflicts:
                cur_owned = profile["owned"].get(item["dest"])
                if cur_owned is None:  # backfill merge-json ownership
                    profile["owned"][item["dest"]] = {"values": fragment, "src": item["src"]}
                    applied.append(f"owned-backfill:{item['dest']}")
                elif cur_owned.get("values") != fragment:  # refresh stale snapshot
                    profile["owned"][item["dest"]] = {"values": fragment,
                                                      "extraValues": cur_owned.get("extraValues", {}),
                                                      "src": item["src"]}
                    applied.append(f"owned-refresh:{item['dest']}")
                continue
            merged = apply_actions(current, actions)
            if conflicts:  # forced: fragment wins
                merged = apply_actions(merged, [{"op": "set", "path": c["path"], "value": c["ours"]}
                                                for c in conflicts])
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            with open(dest, "w") as f:
                json.dump(merged, f, indent=2)
            profile["owned"][item["dest"]] = {"values": fragment, "extraValues": extra,
                                              "src": item["src"]}
            applied.append(item["dest"])

    for r in load_manifest(repo).get("removed", []):
        dest = expand(r["dest"])
        entry = profile["owned"].get(r["dest"], {})
        if "values" in entry:
            refused.append({"dest": r["dest"],
                            "reason": "merge-json dest — shrink the fragment, never file-remove"})
            continue
        owned = entry.get("sha")
        if os.path.exists(dest):
            if sha(dest) == owned or r["dest"] in force:
                os.remove(dest)
                profile["owned"].pop(r["dest"], None)
                applied.append(f"removed:{r['dest']}")
            else:
                refused.append({"dest": r["dest"], "reason": "removal target has unowned content"})

    save_profile(profile)
    print(json.dumps({"applied": applied, "refused": refused}, indent=2))
    return 1 if refused else 0


def cmd_verify(args):
    repo = os.path.abspath(args.repo)
    manifest, profile = load_manifest(repo), load_profile()
    problems = []
    for item in manifest["items"]:
        state = item_state(item, repo, profile)
        if item["strategy"] in ("copy", "merge-json") and state not in ("current",):
            problems.append({"dest": item["dest"], "state": state})
    print(json.dumps({"ok": not problems, "problems": problems}, indent=2))
    return 1 if problems else 0


def cmd_record(args):
    profile = load_profile()
    profile["version"] = args.version
    profile["tag"] = args.tag
    profile["repo"] = os.path.abspath(args.repo)
    profile["updatedAt"] = int(time.time())
    if args.answers_file:
        answers = load_json(args.answers_file, {})
        profile.setdefault("answers", {}).update(answers)
    save_profile(profile)
    print(json.dumps({"version": profile["version"], "tag": profile["tag"]}, indent=2))
    return 0


def _deep_union(base, extra):
    """Deep-union extra into base (dicts recurse, lists union, scalars overwrite)."""
    for k, v in extra.items():
        if isinstance(v, dict) and isinstance(base.get(k), dict):
            _deep_union(base[k], v)
        elif isinstance(v, list) and isinstance(base.get(k), list):
            base[k] = base[k] + [x for x in v if x not in base[k]]
        else:
            base[k] = v
    return base


def cmd_merge_settings(args):
    """Merge an arbitrary machine-generated fragment into ~/.claude/settings.json with the
    same conflict rules + ownership tracking as manifest merge-json items."""
    profile = load_profile()
    fragment = load_json(args.fragment, None)
    if not isinstance(fragment, dict):
        print(f"cannot read fragment: {args.fragment}", file=sys.stderr)
        return 1
    dest_key = "~/.claude/settings.json"
    dest = expand(dest_key)
    current = load_json(dest, {})
    oe = profile["owned"].get(dest_key, {})
    walk_own = _deep_union(_copy(oe.get("values", {})), oe.get("extraValues", {}))
    actions, conflicts = merge_preview(fragment, current, walk_own, retire_missing=False)
    if conflicts and not args.force:
        print(json.dumps({"applied": False, "conflicts": conflicts}, indent=2))
        return 1
    merged = apply_actions(current, actions)
    if conflicts:  # forced
        merged = apply_actions(merged, [{"op": "set", "path": c["path"], "value": c["ours"]}
                                        for c in conflicts])
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    with open(dest, "w") as f:
        json.dump(merged, f, indent=2)
    profile["owned"][dest_key] = {
        "values": oe.get("values", {}),
        "extraValues": _deep_union(_copy(oe.get("extraValues", {})), fragment),
        "src": oe.get("src", "merge-settings"),
    }
    save_profile(profile)
    print(json.dumps({"applied": True, "actions": actions}, indent=2))
    return 0


def cmd_remove(args):
    profile = load_profile()
    dest = expand(args.dest)
    # Resolve the ownership key whether the caller passed the ~-form or an
    # already-shell-expanded absolute path (shells expand unquoted ~).
    key = next((k for k in profile["owned"] if expand(k) == dest), args.dest)
    entry = profile["owned"].get(key, {})
    if "values" in entry:
        print(json.dumps({"removed": False, "reason":
              "merge-json dest — never file-removed; shrink the settings fragment instead"}))
        return 1
    owned = entry.get("sha")
    if not os.path.exists(dest):
        print(json.dumps({"removed": False, "reason": "not present"}))
        return 0
    if sha(dest) != owned:
        print(json.dumps({"removed": False, "reason": "unowned content — refusing"}))
        return 1
    os.remove(dest)
    profile["owned"].pop(key, None)
    save_profile(profile)
    print(json.dumps({"removed": True}))
    return 0


def main():
    ap = argparse.ArgumentParser(prog="apply.py")
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name, fn, extra in [
        ("plan", cmd_plan, []), ("backup", cmd_backup, []),
        ("apply", cmd_apply, ["force"]), ("verify", cmd_verify, []),
        ("record", cmd_record, ["record"]), ("remove", cmd_remove, ["remove"]),
        ("merge-settings", cmd_merge_settings, ["merge-settings"]),
    ]:
        p = sub.add_parser(name)
        if name not in ("remove", "merge-settings"):
            p.add_argument("--repo", required=True)
        if "force" in extra:
            p.add_argument("--force-dest", action="append")
        if "record" in extra:
            p.add_argument("--version", type=int, required=True)
            p.add_argument("--tag", required=True)
            p.add_argument("--answers-file")
        if "remove" in extra:
            p.add_argument("--dest", required=True)
        if "merge-settings" in extra:
            p.add_argument("--fragment", required=True)
            p.add_argument("--force", action="store_true")
        p.set_defaults(fn=fn)
    args = ap.parse_args()
    sys.exit(args.fn(args))


if __name__ == "__main__":
    main()
