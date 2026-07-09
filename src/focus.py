"""Best-effort probe: is the Claude Code host window the active window?

Used to gate `celebrate` (fire only when the user is looking elsewhere). On
KDE Wayland the active window's class isn't exposed over plain DBus, so we try
`kdotool` first, then `xprop _NET_ACTIVE_WINDOW` (works for X/XWayland clients
like VS Code or Konsole-under-X). When detection is unavailable we report
"focused" conservatively, which suppresses celebrate rather than misfiring it.
"""
import shutil
import subprocess


def _run(cmd):
    return subprocess.check_output(cmd, text=True, timeout=2).strip()


def _active_via_kdotool():
    if not shutil.which("kdotool"):
        return None
    try:
        wid = _run(["kdotool", "getactivewindow"])
        if not wid:
            return None
        return (_run(["kdotool", "getwindowclassname", wid]).lower() or None)
    except Exception:
        return None


def _active_via_xprop():
    if not shutil.which("xprop"):
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


def _active_window_class():
    """Active window's class lowercased, or None if undetectable."""
    return _active_via_kdotool() or _active_via_xprop()


def terminal_focused(classes):
    """True if the active window matches any of `classes` (host window class
    substrings). Empty `classes` (unknown host) or undetectable active window
    -> True (conservative: suppress celebrate)."""
    if not classes:
        return True
    cls = _active_window_class()
    if cls is None:
        return True
    return any(c in cls for c in classes)
