"""Shared helpers: detect the Claude Code host app, and per-session socket paths.

Pure and dependency-free so both `bin/claude-pet-hook` (runs inside the Claude
Code session, sees its env) and `src/pet.py` can import it and agree.
"""
import os
import tempfile

LOOPBACK = "127.0.0.1"

# host -> window-class / app-name substrings used to match/focus that host's
# window. On Linux these match KWin resourceClass; on macOS the frontmost app
# name (from AppleScript) is matched against the same substrings.
HOST_CLASSES = {
    "vscode": ["code"],
    "jetbrains": ["jetbrains"],
    "konsole": ["konsole"],
    "apple_terminal": ["terminal"],
    "iterm": ["iterm"],
    "unknown": [],
}

# host -> macOS application name, for `osascript ... to activate` (click-to-focus).
# None where we can't name it reliably (varies per JetBrains IDE).
MAC_APP = {
    "vscode": "Visual Studio Code",
    "apple_terminal": "Terminal",
    "iterm": "iTerm",
}


def detect_host(env=None):
    """Best-effort identify the terminal/IDE hosting Claude Code, from env vars."""
    env = os.environ if env is None else env
    if env.get("TERM_PROGRAM") == "vscode" or env.get("VSCODE_PID"):
        return "vscode"
    if "jetbrains" in (env.get("TERMINAL_EMULATOR", "").lower()):
        return "jetbrains"
    if env.get("KONSOLE_VERSION"):
        return "konsole"
    tp = env.get("TERM_PROGRAM", "")
    if tp == "Apple_Terminal":
        return "apple_terminal"
    if tp == "iTerm.app":
        return "iterm"
    return "unknown"


def host_classes(host):
    """Window-class / app-name substrings for a host (empty list if unknown)."""
    return HOST_CLASSES.get(host, [])


def mac_app(host):
    """macOS application name to activate for a host, or None if unknown."""
    return MAC_APP.get(host)


def runtime_dir():
    """Base dir for per-session port files: $XDG_RUNTIME_DIR, else the OS temp dir.

    AF_UNIX sockets aren't available on stock Windows Python builds, so pets
    listen on a loopback TCP port instead and drop the assigned port in a
    small file here for hook/motion scripts to read.
    """
    return os.environ.get("XDG_RUNTIME_DIR") or tempfile.gettempdir()


def session_port_file(session_id):
    """Path to the file holding the loopback TCP port for a session's pet."""
    sid = session_id or "default"
    return os.path.join(runtime_dir(), "claude-pet-{}.port".format(sid))


def read_session_port(session_id):
    """Port of the pet attached to this session, or None if unknown/stale."""
    try:
        with open(session_port_file(session_id)) as f:
            return int(f.read().strip())
    except (OSError, ValueError):
        return None


def write_session_port(session_id, port):
    with open(session_port_file(session_id), "w") as f:
        f.write(str(port))
