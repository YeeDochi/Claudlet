"""Best-effort probe: is the Claude Code host window the active window?

Used to gate `celebrate` (fire only when the user is looking elsewhere). On
KDE Wayland the active window's class isn't exposed over plain DBus, so we try
`kdotool` first, then `xprop _NET_ACTIVE_WINDOW` (works for X/XWayland clients
like VS Code or Konsole-under-X). When detection is unavailable we report
"focused" conservatively, which suppresses celebrate rather than misfiring it.
"""
import functools
import shutil
import subprocess
import sys


def _run(cmd):
    return subprocess.check_output(cmd, text=True, timeout=2).strip()


@functools.lru_cache(maxsize=None)
def _has(cmd):
    # terminal_focused() runs every tick (30-60/s); shutil.which() walks the
    # whole PATH per call, which is a real per-frame cost on platforms (e.g.
    # Windows) where these tools never exist. Availability can't change
    # mid-session, so cache it instead of re-scanning PATH every frame.
    return shutil.which(cmd) is not None


def _active_via_kdotool():
    if not _has("kdotool"):
        return None
    try:
        wid = _run(["kdotool", "getactivewindow"])
        if not wid:
            return None
        return (_run(["kdotool", "getwindowclassname", wid]).lower() or None)
    except Exception:
        return None


def _active_via_xprop():
    if not _has("xprop"):
        return None
    try:
        out = _run(["xprop", "-root", "_NET_ACTIVE_WINDOW"])
        wid = out.split()[-1]
        if not wid.startswith("0x"):
            return None
        cls = _run(["xprop", "-id", wid, "WM_CLASS"])
        quoted = cls.split('"')[1::2]          # ['instance', 'Class']
        return (quoted[-1].lower() if quoted else None)
    except Exception:
        return None


def _active_via_applescript():
    """macOS: name of the frontmost app (e.g. 'terminal', 'iterm2', 'code').
    Best-effort — untested on macOS hardware."""
    if sys.platform != "darwin" or not _has("osascript"):
        return None
    try:
        return (_run(["osascript", "-e",
                      "tell application \"System Events\" to get name of "
                      "first process whose frontmost is true"]).lower() or None)
    except Exception:
        return None


def _active_window_class():
    """Active window's class/app-name lowercased, or None if undetectable."""
    return (_active_via_kdotool() or _active_via_xprop()
            or _active_via_applescript())


def focus_matches(classes, active_cls):
    """Pure decision: does the active window's class match any host class?

    `classes` are host-window class substrings; `active_cls` is the live active
    window's class (or None if undetectable). Empty `classes` (unknown host) or
    `active_cls is None` -> True (conservative: suppress celebrate). Pure, so
    it's tested with data — no probe monkeypatching."""
    if not classes:
        return True
    if active_cls is None:
        return True
    return any(c in active_cls for c in classes)


def terminal_focused(classes):
    """True if the active window matches any of `classes` (host window class
    substrings). Thin adapter: probe the live active-window class, then defer
    the decision to `focus_matches`."""
    return focus_matches(classes, _active_window_class())
