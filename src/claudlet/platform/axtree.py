"""Read the on-screen text of a window through the macOS Accessibility API.

OPTIONAL BY DESIGN. The AX functions live in `pyobjc-framework-ApplicationServices`,
which claudlet does NOT depend on -- the pet itself never needed it, and making
every user install it for a feature most won't use is the wrong trade. Verified
2026-09-22 on this machine: pyobjc-core/Cocoa/Quartz/WebKit are present and
none of them export AXUIElementCreateApplication, so importing it unconditionally
would break the pet at startup for everyone.

So: `available()` says whether the backend is usable, `trusted()` says whether
the user has actually granted the permission, and `read_window()` returns None
rather than raising when either is false. The caller (core/inspect.py) degrades
to window metadata.

Everything below is a thin wrapper over the C API; the shaping and redaction of
what comes back is pure logic in core/inspect.py, per the house rule that
platform code stays a thin layer over tested pure code.
"""
import sys

# Attributes worth reading off an element. AXValue is the content of a text
# field, AXTitle/AXDescription the label of a control -- together they cover
# "what does this window say" without walking into pixel data.
_TEXT_ATTRS = ("AXValue", "AXTitle", "AXDescription", "AXLabel", "AXHelp")

# Depth cap: an Electron window nests very deep and the tail is almost always
# layout containers, not text. Breadth cap keeps a pathological tree bounded.
MAX_DEPTH = 12
MAX_NODES = 4000

_AX = None
_TRIED = False


def _api():
    """Import the AX module once, or None. Never raises."""
    global _AX, _TRIED
    if _TRIED:
        return _AX
    _TRIED = True
    if sys.platform != "darwin":
        return None
    for name in ("ApplicationServices", "HIServices"):
        try:
            mod = __import__(name)
        except ImportError:
            continue
        if hasattr(mod, "AXUIElementCreateApplication"):
            _AX = mod
            return _AX
    return None


def available():
    """True when the AX functions can be called at all."""
    return _api() is not None


def trusted():
    """True when this process is allowed to read other apps' AX trees.

    False also when the backend is missing -- callers only need one check.
    """
    ax = _api()
    if ax is None:
        return False
    fn = getattr(ax, "AXIsProcessTrusted", None)
    if fn is None:
        return False
    try:
        return bool(fn())
    except Exception:
        return False


def install_hint():
    """What to tell the user when this can't run, or None when it can."""
    if not available():
        return ("화면 내용 읽기에는 추가 패키지가 필요합니다: "
                "pip install pyobjc-framework-ApplicationServices")
    if not trusted():
        return ("시스템 설정 → 개인정보 보호 및 보안 → 손쉬운 사용 에서 "
                "claudlet 을 허용해 주세요.")
    return None


def _attr(ax, el, name):
    try:
        err, val = ax.AXUIElementCopyAttributeValue(el, name, None)
    except Exception:
        return None
    return val if err == 0 else None


def _walk(ax, el, out, depth, budget):
    if depth > MAX_DEPTH or budget[0] <= 0:
        return
    budget[0] -= 1
    for name in _TEXT_ATTRS:
        val = _attr(ax, el, name)
        if isinstance(val, str) and val.strip():
            out.append(val)
    kids = _attr(ax, el, "AXChildren") or ()
    try:
        kids = list(kids)
    except TypeError:
        return
    for kid in kids:
        _walk(ax, el, out, depth + 1, budget) if kid is None else \
            _walk(ax, kid, out, depth + 1, budget)


def read_window(win):
    """Strings visible in `win` (a geom.Win), or None if unreadable.

    Matches the window by AXWindow position/size against the window list's
    bounds: AX has no CGWindowID, so the frame is the only reliable join.
    """
    ax = _api()
    if ax is None or not trusted() or win is None:
        return None
    try:
        app = ax.AXUIElementCreateApplication(win.pid)
    except Exception:
        return None
    if app is None:
        return None
    windows = _attr(ax, app, "AXWindows") or ()
    try:
        windows = list(windows)
    except TypeError:
        return None
    target = _match_window(ax, windows, win)
    if target is None:
        return None
    out, budget = [], [MAX_NODES]
    _walk(ax, target, out, 0, budget)
    return out


def _match_window(ax, windows, win, tol=6):
    """The AX window whose frame matches `win`, else the only one, else None."""
    if not windows:
        return None
    for el in windows:
        pos, size = _attr(ax, el, "AXPosition"), _attr(ax, el, "AXSize")
        got = _frame(pos, size, ax)
        if got is None:
            continue
        x, y, w, h = got
        if (abs(x - win.x) <= tol and abs(y - win.y) <= tol
                and abs(w - win.w) <= tol and abs(h - win.h) <= tol):
            return el
    return windows[0] if len(windows) == 1 else None


def _frame(pos, size, ax=None):
    """(x,y,w,h) out of AXValue wrappers, or None. Split out to stay testable.

    The real API hands back opaque AXValue objects that must be unwrapped with
    AXValueGetValue -- verified 2026-09-22: they have no .x/.width attributes,
    so the attribute path below only ever serves fakes in tests. Kept anyway
    because it costs nothing and makes the pure logic testable without pyobjc.
    """
    if pos is None or size is None:
        return None
    ax = ax or _api()
    getter = getattr(ax, "AXValueGetValue", None) if ax else None
    if getter is not None:
        try:
            okp, pt = getter(pos, ax.kAXValueCGPointType, None)
            oks, sz = getter(size, ax.kAXValueCGSizeType, None)
            if okp and oks:
                return (int(pt.x), int(pt.y), int(sz.width), int(sz.height))
        except Exception:
            pass
    try:
        return (int(pos.x), int(pos.y), int(size.width), int(size.height))
    except (AttributeError, TypeError, ValueError):
        pass
    try:
        return (int(pos[0]), int(pos[1]), int(size[0]), int(size[1]))
    except (TypeError, IndexError, ValueError):
        return None


def intersects(frame, region):
    """True when an element's frame overlaps the selected region.

    Overlap, not containment: a label straddling the edge of the drag is part of
    what the user pointed at. Requiring full containment would silently drop the
    heading someone dragged the top half of.
    """
    if frame is None or region is None:
        return False
    x, y, w, h = frame
    rx, ry, rw, rh = region
    return not (x + w < rx or x > rx + rw or y + h < ry or y > ry + rh)


def _element_frame(ax, el):
    return _frame(_attr(ax, el, "AXPosition"), _attr(ax, el, "AXSize"), ax)


def _walk_region(ax, el, region, out, depth, budget):
    """Collect text from elements overlapping `region`.

    Descends into a non-matching container anyway: a scroll area's own frame may
    not overlap while its children do, and stopping at the first miss would drop
    everything inside it.
    """
    if depth > MAX_DEPTH or budget[0] <= 0:
        return
    budget[0] -= 1
    if intersects(_element_frame(ax, el), region):
        for name in _TEXT_ATTRS:
            val = _attr(ax, el, name)
            if isinstance(val, str) and val.strip():
                out.append(val)
                break
    kids = _attr(ax, el, "AXChildren") or ()
    try:
        kids = list(kids)
    except TypeError:
        return
    for kid in kids:
        if kid is not None:
            _walk_region(ax, kid, region, out, depth + 1, budget)


def read_region(win, region):
    """Strings from `win` whose elements overlap `region` (x,y,w,h global).

    None when unreadable, exactly like read_window -- the caller degrades to
    metadata rather than treating an empty read as an empty screen.
    """
    ax = _api()
    if ax is None or not trusted() or win is None or region is None:
        return None
    try:
        app = ax.AXUIElementCreateApplication(win.pid)
    except Exception:
        return None
    if app is None:
        return None
    windows = _attr(ax, app, "AXWindows") or ()
    try:
        windows = list(windows)
    except TypeError:
        return None
    target = _match_window(ax, windows, win)
    if target is None:
        return None
    out, budget = [], [MAX_NODES]
    _walk_region(ax, target, region, out, 0, budget)
    return out
