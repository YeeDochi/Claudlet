"""Open a terminal window running a command.

The agent is an interactive TUI, so it cannot be launched detached the way the
pet is -- it needs a terminal attached to it. That is the whole reason this
module exists, and the reason it is platform code: every OS opens a terminal
differently, and none of it can be verified without a desktop.

Kept as a thin wrapper over `core/session_launch.py`, which decides WHAT to run.
Here we only decide HOW to open it, per the house rule that platform code stays
a thin layer over tested pure logic.
"""
import os
import shutil
import subprocess
import sys

TIMEOUT = 10.0

# Terminals we know how to drive, most-preferred first. A user who has iTerm
# open probably wants the new session there rather than in Apple Terminal.
_MAC_TERMINALS = (
    ("iTerm", "/Applications/iTerm.app"),
    ("Terminal", "/System/Applications/Utilities/Terminal.app"),
    ("Terminal", "/Applications/Utilities/Terminal.app"),
)

_APPLESCRIPT = {
    # `do script` in Terminal opens a new window and runs the line in it.
    "Terminal": 'tell application "Terminal"\n'
                '  activate\n'
                '  do script {cmd}\n'
                'end tell',
    "iTerm": 'tell application "iTerm"\n'
             '  activate\n'
             '  set w to (create window with default profile)\n'
             '  tell current session of w to write text {cmd}\n'
             'end tell',
}


def _as_literal(text):
    """An AppleScript string literal. Only backslash and quote need escaping."""
    return '"' + str(text).replace("\\", "\\\\").replace('"', '\\"') + '"'


def mac_script(command, app="Terminal"):
    """The AppleScript that runs `command` in a new window. Pure and testable."""
    template = _APPLESCRIPT.get(app) or _APPLESCRIPT["Terminal"]
    return template.format(cmd=_as_literal(command))


def pick_mac_terminal(exists=os.path.isdir):
    """Which terminal app to use, or None when we recognise none."""
    for name, path in _MAC_TERMINALS:
        if exists(path):
            return name
    return None


def available():
    """True when this platform can open a terminal window for us."""
    if sys.platform == "darwin":
        return pick_mac_terminal() is not None and bool(shutil.which("osascript"))
    if sys.platform.startswith("win"):
        return bool(shutil.which("cmd"))
    return bool(_linux_terminal())


def _linux_terminal():
    for exe in ("x-terminal-emulator", "gnome-terminal", "konsole",
                "xfce4-terminal", "alacritty", "kitty", "xterm"):
        if shutil.which(exe):
            return exe
    return None


def launch(command, run=None):
    """Open a terminal window running `command`. True on success.

    `run` is injected so the dispatch can be tested without opening windows.
    Never raises: a failure here means the user gets a pet with no session,
    which the caller reports -- it must not take the pet down with it.
    """
    runner = run or _run
    try:
        if sys.platform == "darwin":
            app = pick_mac_terminal()
            if app is None:
                return False
            return runner(["osascript", "-e", mac_script(command, app)])
        if sys.platform.startswith("win"):
            return runner(["cmd", "/c", "start", "", "cmd", "/k", command])
        exe = _linux_terminal()
        if exe is None:
            return False
        return runner([exe, "-e", "bash", "-lc", command])
    except Exception:
        return False


def _run(argv):
    proc = subprocess.run(argv, capture_output=True, timeout=TIMEOUT)
    return proc.returncode == 0
