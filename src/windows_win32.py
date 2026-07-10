"""Read other windows' geometry on Windows (ctypes/Win32), so the pet can
perch on and be contained by them — the Windows equivalent of the KWin/D-Bus
geometry feed in `pet.py`.

Win32 has nothing like KWin scripting's push-on-change signals, so this is
polled on a timer instead of pushed. EnumWindows already returns windows in
current, correct Z-order every call, so (unlike the KWin feed) no
just-activated-window workaround is needed here.

Produces the same wire format the KWin feed uses (`windows.parse_kwin_dump`),
so it plugs into the existing, already-tested perch/contain pipeline
unchanged: `id;class;x,y,w,h;pid|id;class;x,y,w,h;pid|...`, bottom-to-top.
"""
import ctypes
from ctypes import wintypes

user32 = ctypes.windll.user32 if hasattr(ctypes, "windll") else None
dwmapi = ctypes.windll.dwmapi if hasattr(ctypes, "windll") else None

GWL_EXSTYLE = -20
WS_EX_TOOLWINDOW = 0x00000080
DWMWA_EXTENDED_FRAME_BOUNDS = 9
DWMWA_CLOAKED = 14
_WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)


def _is_cloaked(hwnd):
    """True if DWM is hiding this window despite IsWindowVisible() saying True.
    Modern Windows leaves UWP/shell surfaces (Settings, input UI, etc.) around
    in this cloaked state on other virtual desktops/suspended — visible-looking
    rects that aren't actually drawn, which the pet would otherwise perch on or
    hide behind as if they were real."""
    if dwmapi is None:
        return False
    cloaked = ctypes.c_int(0)
    hr = dwmapi.DwmGetWindowAttribute(
        hwnd, DWMWA_CLOAKED, ctypes.byref(cloaked), ctypes.sizeof(cloaked))
    return hr == 0 and cloaked.value != 0


def _visible_rect(hwnd):
    """GetWindowRect on Win10/11 includes an invisible resize-border margin for
    many apps (observed ~7-8px on Chrome/Electron and Windows Terminal) — the
    reported box is bigger than what's actually drawn on screen. That's fine
    for "contain" (just a loose bounding box) but throws off "perch", which
    needs the pet's feet to land exactly on the visible top edge. DWM's
    extended-frame-bounds attribute gives the true visible rect; fall back to
    GetWindowRect if DWM has nothing (composition off, exotic window types)."""
    rect = wintypes.RECT()
    if dwmapi is not None:
        hr = dwmapi.DwmGetWindowAttribute(
            hwnd, DWMWA_EXTENDED_FRAME_BOUNDS, ctypes.byref(rect), ctypes.sizeof(rect))
        if hr == 0:
            return rect
    if user32.GetWindowRect(hwnd, ctypes.byref(rect)):
        return rect
    return None


def _enum_windows(exclude_hwnd=None):
    """Visible, non-minimized top-level windows, topmost-first (raw Win32 order)."""
    out = []

    def _cb(hwnd, _lparam):
        if exclude_hwnd is not None and hwnd == exclude_hwnd:
            return True
        # Cheap, local user32 checks first — DwmGetWindowAttribute is a call
        # into dwm.exe, and every top-level window on the system (including
        # dozens of invisible/helper ones) reaches this callback each poll,
        # so paying for DWM only after the free filters narrows it down a lot.
        if not user32.IsWindowVisible(hwnd) or user32.IsIconic(hwnd):
            return True
        if user32.GetWindowTextLengthW(hwnd) == 0:
            return True                  # no title -> background/helper window
        ex_style = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
        if ex_style & WS_EX_TOOLWINDOW:
            return True
        if _is_cloaked(hwnd):
            return True
        rect = _visible_rect(hwnd)
        if rect is None:
            return True
        w, h = rect.right - rect.left, rect.bottom - rect.top
        if w <= 0 or h <= 0:
            return True
        buf = ctypes.create_unicode_buffer(256)
        user32.GetClassNameW(hwnd, buf, 256)
        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        out.append((hwnd, buf.value.lower(), rect.left, rect.top, w, h, pid.value))
        return True

    user32.EnumWindows(_WNDENUMPROC(_cb), 0)
    return out


def dump(exclude_hwnd=None):
    """Current windows as a KWin-feed-format string (bottom-to-top stacking)."""
    if user32 is None:
        return ""
    rows = _enum_windows(exclude_hwnd)
    rows.reverse()   # EnumWindows is topmost-first; the feed format wants bottom->top
    return "|".join(
        "{};{};{},{},{},{};{}".format(hwnd, cls, x, y, w, h, pid)
        for hwnd, cls, x, y, w, h, pid in rows
    )
