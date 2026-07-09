"""Shared helpers: detect the Claude Code host app, and per-session socket paths.

Pure and dependency-free so both `bin/claude-pet-hook` (runs inside the Claude
Code session, sees its env) and `src/pet.py` can import it and agree.
"""
import os

# host -> window-class substrings used to match/activate/focus that host's window
HOST_CLASSES = {
    "vscode": ["code"],
    "jetbrains": ["jetbrains"],
    "konsole": ["konsole"],
    "unknown": [],
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
    return "unknown"


def host_classes(host):
    """Window-class substrings for a host (empty list if unknown)."""
    return HOST_CLASSES.get(host, [])


def session_sock(session_id):
    """Unix socket path for a given Claude Code session id."""
    base = os.environ.get("XDG_RUNTIME_DIR", "/tmp")
    sid = session_id or "default"
    return os.path.join(base, "claude-pet-{}.sock".format(sid))
