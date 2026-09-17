#!/usr/bin/env python3
"""Register (or remove) claudlet hooks in each detected agent's settings file.

Usage:
    claudlet-install-hooks                   # install: every detected agent
    claudlet-install-hooks --remove          # remove: every detected agent
    claudlet-install-hooks --agent codex     # install: just codex
    claudlet-install-hooks --remove --agent claude,codex

Keeps a single rolling backup (<file>.bak) and writes atomically. Idempotent.
"""
import json
import os
import shutil
import sys
import tempfile

from claudlet.core import agents


def _quote(path):
    # Always quote, even with no spaces: an unquoted Windows path loses its
    # backslashes when a Unix-like shell interprets it.
    return f'"{path}"'


def _command(*parts):
    quoted = " ".join(_quote(part) for part in parts)
    if os.name == "nt":
        # Desktop agents execute hook strings through PowerShell, where a
        # quoted executable path is only a string unless prefixed with `&`.
        # Routing through cmd.exe also works when the host uses cmd or bash,
        # and keeps paths containing spaces executable in every Windows host.
        return f"cmd.exe /d /s /c call {quoted}"
    return quoted


def hook_command():
    """Command string a settings file invokes per hook event. Prefer the
    installed `claudlet-hook` console script (pipx/pip); else the source
    checkout's bin/claudlet-hook shim (which puts src/ on sys.path); else
    `python -m claudlet.cli.hook`. On Windows, extensionless scripts need the
    interpreter prefixed (cmd.exe ignores "#!"); a real console-script .exe
    from which() runs directly."""
    exe = shutil.which("claudlet-hook")
    if exe:
        return _command(exe)
    repo_bin = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(
            os.path.dirname(os.path.abspath(__file__))))),
        "bin", "claudlet-hook")
    if os.path.exists(repo_bin):
        if os.name == "nt":
            return _command(sys.executable, repo_bin)
        return _command(repo_bin)
    return f"{_command(sys.executable)} -m claudlet.cli.hook"


HOOK_CMD = hook_command()


def load(path):
    if not os.path.exists(path):
        return {}
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        # Corrupt/unreadable settings file. Returning {} would drop every OTHER
        # setting the user has when we write our hooks back, so bail loudly and
        # leave their file untouched instead.
        raise SystemExit(
            f"claudlet: cannot read {path} ({e}).\n"
            "Fix or move it aside, then re-run the installer.")


def save(path, s):
    """Write the settings file atomically, keeping a single rolling backup.

    The old approach renamed the live file to a timestamped .bak and *then*
    wrote the new one: a crash in between left no settings file at all, and the
    timestamped backups piled up forever. Instead: copy the current file to a
    stable <file>.bak, write the new content to a temp file in the same
    directory, fsync it, and os.replace() it into place (atomic on the same
    filesystem). The live file is never absent, and only one backup is kept.
    """
    d = os.path.dirname(path)
    os.makedirs(d, exist_ok=True)
    if os.path.exists(path):
        shutil.copy2(path, f"{path}.bak")   # single rolling backup
    fd, tmp = tempfile.mkstemp(dir=d, prefix=".settings.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(s, f, indent=2, ensure_ascii=False)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    except Exception:
        try:
            os.unlink(tmp)          # don't leave a half-written temp behind
        except OSError:
            pass
        raise


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


def targets(argv, home=None):
    """Which agents this run touches. Pure.

    No --agent -> every agent that looks installed. With --agent, exactly what
    was named (even if its marker dir is missing: naming it IS the intent),
    minus names we don't know."""
    want = None
    for i, a in enumerate(argv):
        if a == "--agent" and i + 1 < len(argv):
            want = argv[i + 1]
        elif a.startswith("--agent="):
            want = a.split("=", 1)[1]
    if want is None:
        return agents.detected(home)
    named = [n.strip() for n in want.split(",") if n.strip()]
    return [n for n in named if n in agents.AGENTS]


def install_for(agent, path, remove=False):
    """Register (or drop) our hook groups in one agent's config file."""
    spec = agents.get(agent)
    if remove and not os.path.exists(path):
        return          # nothing installed for this agent -- don't create the file
    s = load(path)
    hooks = s.get("hooks", {})
    # On remove, sweep every event the FILE lists too, not just what the
    # current registry declares: if an agent's event list is ever narrowed,
    # a claudlet group under a dropped event would otherwise survive
    # `--remove` and keep firing.
    events = (set(spec["events"]) | set(hooks)) if remove else spec["events"]
    for ev in events:
        # drop any existing claudlet groups first (idempotent)
        hooks[ev] = [g for g in hooks.get(ev, []) if not is_ours(g)]
        if not remove:
            cmd = {"type": "command",
                   "command": f"{HOOK_CMD} {ev} --agent {agent}"}
            group = {"hooks": [cmd]}
            if ev in spec["tool_events"]:
                group["matcher"] = "*"
            hooks[ev].append(group)
        if not hooks[ev]:
            del hooks[ev]

    if hooks:
        s["hooks"] = hooks
    elif "hooks" in s:
        del s["hooks"]

    save(path, s)


def main(argv=None, home=None):
    argv = sys.argv if argv is None else argv
    remove = "--remove" in argv
    picked = targets(argv, home)
    if not picked:
        print("claudlet: no agent found (looked for "
              + ", ".join("~/" + agents.get(n)["marker"] for n in agents.names())
              + "); nothing to do.")
        return
    for name in picked:
        path = agents.settings_path(name, home)
        install_for(name, path, remove)
        print(("removed" if remove else "installed"),
              f"claudlet hooks for {agents.get(name)['label']}:",
              ", ".join(agents.get(name)["events"]))
    print("(restart your agent sessions for changes to take effect)")


if __name__ == "__main__":
    main()
