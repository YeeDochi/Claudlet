#!/usr/bin/env python3
"""Register (or remove) claudlet hooks in ~/.claude/settings.json.

Usage:
    claudlet-install-hooks           # install
    claudlet-install-hooks --remove  # remove

Backs up settings.json before writing. Idempotent.
"""
import json
import os
import shutil
import sys
import time

SETTINGS = os.path.expanduser("~/.claude/settings.json")


def _quote(path):
    # Always quote, even with no spaces: Claude Code runs hook commands
    # through bash even on Windows, and an unquoted "C:\Users\..." loses
    # every backslash there (bash treats "\U", "\g", etc. as escapes of the
    # next literal char). Double quotes keep bash from touching backslashes
    # (its escape rules inside "" only apply to \, $, `, ", newline) while
    # still being valid, unremarkable quoting for cmd.exe and POSIX sh.
    return f'"{path}"'


def _hook_command():
    """Command string settings.json invokes per hook event. Prefer the installed
    `claudlet-hook` console script (pipx/pip); else the source checkout's
    bin/claudlet-hook shim (which puts src/ on sys.path); else `python -m
    claudlet.cli.hook`. On Windows, extensionless scripts need the interpreter
    prefixed (cmd.exe ignores "#!"); a real console-script .exe from which()
    runs directly."""
    exe = shutil.which("claudlet-hook")
    if exe:
        return _quote(exe)
    repo_bin = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
        "bin", "claudlet-hook")
    if os.path.exists(repo_bin):
        if os.name == "nt":
            return f"{_quote(sys.executable)} {_quote(repo_bin)}"
        return _quote(repo_bin)
    return f"{_quote(sys.executable)} -m claudlet.cli.hook"


HOOK_CMD = _hook_command()

TOOL_EVENTS = ["PreToolUse", "PostToolUse"]
PLAIN_EVENTS = ["UserPromptSubmit", "Notification", "Stop", "StopFailure",
                "SubagentStop", "SessionStart", "SessionEnd"]
ALL_EVENTS = TOOL_EVENTS + PLAIN_EVENTS


def load():
    if not os.path.exists(SETTINGS):
        return {}
    with open(SETTINGS, encoding="utf-8") as f:
        return json.load(f)


def save(s):
    os.makedirs(os.path.dirname(SETTINGS), exist_ok=True)
    if os.path.exists(SETTINGS):
        os.rename(SETTINGS, f"{SETTINGS}.bak.{int(time.time())}")
    with open(SETTINGS, "w", encoding="utf-8") as f:
        json.dump(s, f, indent=2, ensure_ascii=False)


def is_ours(group):
    for h in group.get("hooks", []):
        cmd = h.get("command", "")
        # match the current markers and the pre-rename ones ("claude-pet-hook"/
        # "claude_pet.hook", plus the pre-cli-move "claudlet.hook") so a
        # migration run cleanly drops old entries instead of leaving them
        # alongside the new claudlet ones (double-firing hooks).
        if any(m in cmd for m in ("claudlet-hook", "claudlet.hook", "claudlet.cli.hook",
                                  "claude-pet-hook", "claude_pet.hook")):
            return True
    return False


def main(argv=None):
    remove = "--remove" in (sys.argv if argv is None else argv)
    s = load()
    hooks = s.get("hooks", {})

    for ev in ALL_EVENTS:
        # drop any existing claudlet groups first (idempotent)
        hooks[ev] = [g for g in hooks.get(ev, []) if not is_ours(g)]
        if not remove:
            cmd = {"type": "command", "command": f"{HOOK_CMD} {ev}"}
            group = {"hooks": [cmd]}
            if ev in TOOL_EVENTS:
                group["matcher"] = "*"
            hooks[ev].append(group)
        if not hooks[ev]:
            del hooks[ev]

    if hooks:
        s["hooks"] = hooks
    elif "hooks" in s:
        del s["hooks"]

    save(s)
    print(("removed" if remove else "installed"), "claudlet hooks:",
          ", ".join(ALL_EVENTS))
    print("(restart Claude Code sessions for changes to take effect)")


if __name__ == "__main__":
    main()
