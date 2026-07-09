"""Best-effort probe: is the Claude terminal (Konsole) the active window?

KDE Wayland does not expose the active window's class over plain DBus, and X
tools cannot see native Wayland clients. We try `kdotool` (a KWin-scripting
CLI) first; if it is absent or fails, we report "unknown" and the caller treats
that conservatively (assume focused -> no celebrate). Enabling reliable
detection is the spike: if kdotool is not acceptable, replace
`_active_window_class` with a persistent KWin script that emits the active
window's resourceClass over DBus.
"""
import shutil
import subprocess

TERMINAL_CLASSES = ("konsole",)   # extend if other terminals are used


def _active_window_class():
    """Return the active window's class lowercased, or None if undetectable."""
    kdotool = shutil.which("kdotool")
    if not kdotool:
        return None
    try:
        wid = subprocess.check_output([kdotool, "getactivewindow"],
                                      text=True, timeout=2).strip()
        if not wid:
            return None
        cls = subprocess.check_output(
            [kdotool, "getwindowclassname", wid],
            text=True, timeout=2).strip().lower()
        return cls or None
    except Exception:
        return None


def terminal_focused():
    cls = _active_window_class()
    if cls is None:
        return True   # conservative: unknown -> assume focused, suppress celebrate
    return any(t in cls for t in TERMINAL_CLASSES)
