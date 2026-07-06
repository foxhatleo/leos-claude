#!/usr/bin/env python3
"""PreToolUse guard for Bash: blocks the catastrophic-deletion command class.

Narrow tripwire for irreversible, home/system-scale damage — NOT a general command
policy (the permission classifier handles that). False positives are cheap (Claude
sees the reason and rephrases or asks); false negatives are not.

Exit 0 = allow. Exit 43 = block — the settings.json wrapper maps 43 -> 2 (deny) and
everything else -> 0, so interpreter/script failures (python exits 1/2 on its own
errors) can never masquerade as a block. Fail-OPEN on internal errors.

Accepted out-of-scope (other layers' job): obfuscation via scripts/eval/base64,
non-rm destruction (find -delete), network exfiltration.
"""

import json
import os
import re
import shlex
import sys

HOME = os.path.realpath(os.path.expanduser("~"))

WRAPPERS = {"sudo", "command", "env", "nice", "nohup", "time", "doas"}
RECURSIVE_SHORT = re.compile(r"^-[a-zA-Z]*[rR]")
FORCEABLE = re.compile(r"^-[a-zA-Z]*f")

CRITICAL_DIRS = {
    "/", "/Users", "/home", "/root", "/dev", "/bin", "/boot", "/etc", "/lib",
    "/lib64", "/sbin", "/usr", "/var", "/opt", "/System", "/Library",
    "/Applications", "/private/etc", HOME,
}
def _home_toplevel():
    """OS-standard home dirs + machine extras from optional guard-config.json
    ({"homeToplevel": ["projects", ...]}). Config errors are ignored (fail-open)."""
    dirs = {"Desktop", "Documents", "Downloads", "Library", "Pictures", "Movies", "Music"}
    cfg_path = os.environ.get(
        "CLAUDE_GUARD_CONFIG",
        os.path.join(HOME, ".claude", "hooks", "guard-config.json"))
    try:
        with open(cfg_path) as f:
            extra = json.load(f).get("homeToplevel", [])
        dirs |= {d for d in extra if isinstance(d, str) and d and "/" not in d}
    except Exception:
        pass
    return {os.path.join(HOME, d) for d in dirs}


HOME_TOPLEVEL = _home_toplevel()
HOME_REF = re.compile(r"(~([A-Za-z_][\w-]*)?(/|[\s*]|$)|\$\{?HOME\}?)")
WATCHED = {"rm", "dd", "chmod", "xargs", "cd"}
ASSIGN_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")
UNKNOWN_DIR = "<unknown>"

# Whole subtrees that are never rm -rf'd unattended. /var excepted for temp dirs;
# /Users only to one level deep (user home roots) so project paths stay allowed.
PREFIX_CRITICAL = ("/bin", "/boot", "/etc", "/lib", "/lib64", "/sbin", "/usr",
                   "/System", "/Library", "/Applications", "/dev", "/root", "/home")
PREFIX_EXEMPT = ("/var/folders", "/var/tmp", "/private/var/folders", "/private/tmp")


def tokenize(segment):
    try:
        return shlex.split(segment, posix=True)
    except ValueError:
        return segment.split()


def split_statements(command):
    """Split on ; && || & into statements; a statement may contain a pipeline."""
    return [s for s in re.split(r"(?:\|\||&&|[;&])", command) if s.strip()]


def split_pipeline(statement):
    return [s for s in statement.split("|") if s.strip()]


def strip_wrappers(tokens):
    """Strip leading VAR=val assignments; if a wrapper (sudo/env/...) leads, scan
    forward to the first WATCHED command so wrapper flags AND their operands
    (e.g. `sudo -u root rm`) can't shield the real command."""
    i = 0
    while i < len(tokens) and ASSIGN_RE.match(tokens[i]):
        i += 1
    tokens = tokens[i:]
    if not tokens:
        return []
    if os.path.basename(tokens[0]) in WRAPPERS:
        for j in range(1, len(tokens)):
            if os.path.basename(tokens[j]) in WATCHED or tokens[j].startswith("mkfs"):
                return tokens[j:]
        return []
    return tokens


def expand(target, cwd, cd_context):
    """Expand ~/, ~user, $HOME; resolve relative paths against cd-context or tool cwd."""
    t = target.replace("${HOME}", HOME).replace("$HOME", HOME)
    if t == "~" or t.startswith("~/"):
        t = HOME + t[1:]
    else:
        m = re.match(r"^~([A-Za-z_][\w-]*)(/.*)?$", t)
        if m:  # ~user expansion: macOS + Linux home containers
            t = "/Users/" + m.group(1) + (m.group(2) or "")
    base = cd_context or cwd
    if base == UNKNOWN_DIR:
        base = None
    if t and not t.startswith("/") and base:
        t = os.path.join(base, t)
    return t


def is_critical(path):
    """Is path a critical dir, inside a critical subtree, or a glob over one's contents?"""
    if not path:
        return False
    starred = path.endswith(("/*", "/.*")) or path in ("/*", "*")
    norm = os.path.normpath(re.sub(r"/\.?\*$", "", path)) if starred else os.path.normpath(path)
    if norm in CRITICAL_DIRS or norm in HOME_TOPLEVEL:
        return True
    if norm.startswith("/") and not any(
            norm == e or norm.startswith(e + "/") for e in PREFIX_EXEMPT):
        for p in PREFIX_CRITICAL:
            if norm == p or norm.startswith(p + "/"):
                return True
        # /var and its macOS alias /private/var (temp dirs exempted above)
        if norm == "/var" or norm.startswith("/var/") \
                or norm == "/private/var" or norm.startswith("/private/var/"):
            return True
        # any user's home root, one level under /Users or /home
        m = re.match(r"^/(Users|home)/[^/]+/?$", norm)
        if m:
            return True
    return False


def check_rm(tokens, cwd, cd_context):
    """tokens = wrapper-stripped command tokens with tokens[0] ~ rm."""
    recursive = False
    targets = []
    for t in tokens[1:]:
        if t == "--no-preserve-root":
            return "rm --no-preserve-root"
        if t in ("--recursive", "-R"):
            recursive = True
        elif t.startswith("--"):
            continue
        elif t.startswith("-"):
            if RECURSIVE_SHORT.match(t):
                recursive = True
        else:
            targets.append(t)
    if not recursive:
        return None
    for raw in targets:
        # Unknown working directory: relative sweeps are unverifiable — block conservatively.
        if raw in (".", "..", "./", "../", "./*", "../*", "*") and not (cwd or cd_context):
            return f"recursive rm of '{raw}' with unknown working directory"
        if is_critical(expand(raw, cwd, cd_context)):
            return f"recursive rm targeting '{raw}'"
    return None


def handle_cd(tokens, cwd, cd_context):
    """Model cd: bare cd -> HOME; `cd -` -> unknown; skip flags/--."""
    args = [t for t in tokens[1:] if not (t.startswith("-") and t != "-")]
    if not args:
        return HOME
    if args[0] == "-":
        return UNKNOWN_DIR
    return expand(args[0], cwd, cd_context)


def check_statement(statement, cwd, cd_context):
    """Check one statement (possibly a pipeline). Returns (reason|None, new_cd_context)."""
    stmt_home_ref = bool(HOME_REF.search(statement))

    for stage in split_pipeline(statement):
        tokens = strip_wrappers(tokenize(stage))
        if not tokens:
            continue
        cmd = os.path.basename(tokens[0])

        if cmd == "cd":
            cd_context = handle_cd(tokens, cwd, cd_context)
            continue
        if cmd == "rm":
            reason = check_rm(tokens, cwd, cd_context)
            if reason:
                return reason, cd_context
        if cmd == "xargs":
            # Scan past xargs flags/operands (-0, -n 1, -I{}, --no-run-if-empty...) to find rm.
            rest = tokens[1:]
            for j, t in enumerate(rest):
                if os.path.basename(t) == "rm":
                    rec = any(RECURSIVE_SHORT.match(x) or x == "--recursive" for x in rest[j + 1:])
                    if rec and stmt_home_ref:
                        return "piped xargs rm -r with a home/root reference in the pipeline", cd_context
                    break
        if cmd == "mkfs" or cmd.startswith("mkfs."):
            return "mkfs (filesystem format)", cd_context
        if cmd == "dd":
            for t in tokens[1:]:
                if t.startswith("of=/dev/"):
                    return "dd writing to a raw device", cd_context
        if cmd == "chmod":
            rec = any(RECURSIVE_SHORT.match(t) for t in tokens[1:] if t.startswith("-"))
            if rec and tokens[-1] in ("/", HOME):
                return "recursive chmod on / or home", cd_context
    return None, cd_context


def check(command, cwd):
    cd_context = None
    for statement in split_statements(command):
        reason, cd_context = check_statement(statement, cwd, cd_context)
        if reason:
            return reason
    return None


def main():
    try:
        payload = json.load(sys.stdin)
    except Exception:
        return 0
    try:
        if payload.get("tool_name") != "Bash":
            return 0
        command = (payload.get("tool_input") or {}).get("command", "")
        if not isinstance(command, str) or not command:
            return 0
        cwd = payload.get("cwd") if isinstance(payload.get("cwd"), str) else None
        reason = check(command, cwd)
        if reason:
            sys.stderr.write(
                f"[bash-guard] BLOCKED — {reason}. This command class is irreversible at "
                f"home/system scale and is never run unattended. If the deletion is genuinely "
                f"intended: use a narrower explicit path (never '~', '/', '.', or a home-level "
                f"directory), prefer moving to trash, or ask the user to run it themselves.\n"
            )
            return 43
        return 0
    except Exception:
        return 0


if __name__ == "__main__":
    sys.exit(main())
