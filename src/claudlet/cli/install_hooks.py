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
    return f'"{path}"'


def _command(*parts):
    """Build a command string out of PATHS, for the fallbacks below.

    No Windows path form satisfies every shell a hook string can land in, which
    is why `hook_command` avoids paths entirely when it can:

        quoted backslash    bash OK   PowerShell NO   cmd OK
        unquoted /          bash OK   PowerShell OK   cmd NO
        unquoted backslash  bash NO   PowerShell OK   cmd OK

    Bash needs the quotes, because an unquoted Windows path loses every
    backslash to its escape rules. PowerShell breaks ON the quotes: a statement
    starting with a quoted string is a string literal, not a command, so the
    hook silently never runs. cmd reads a leading `/` as a switch and never
    finds the program. (Wrapping in `cmd.exe /d /s /c` is not a way out either:
    MSYS rewrites those switches as paths, so cmd gets no /c, comes up
    INTERACTIVE, and reads the hook's JSON payload off stdin as a command.)

    Forward slashes are the best of the three -- they cover the hosts claudlet
    is known to run under -- so that is what a path gets here.
    """
    if os.name == "nt":
        return " ".join(p.replace("\\", "/") for p in parts)
    return " ".join(_quote(p) for p in parts)


def hook_command():
    """Command string a settings file invokes per hook event. Prefer the
    installed `claudlet-hook` console script (pipx/pip); else the source
    checkout's bin/claudlet-hook shim (which puts src/ on sys.path); else
    `python -m claudlet.cli.hook`. On Windows, extensionless scripts need the
    interpreter prefixed (cmd.exe ignores "#!"); a real console-script .exe
    from which() runs directly."""
    exe = shutil.which("claudlet-hook")
    if exe:
        if os.name == "nt":
            # No quotes, no slashes, no backslashes -- the one form bash,
            # PowerShell AND cmd all accept (see _command for why no path form
            # does). It costs nothing in precision: which() just resolved this
            # name off PATH, so that is exactly what the shell will find. A
            # space in the user's home stops mattering too.
            return "claudlet-hook"
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
