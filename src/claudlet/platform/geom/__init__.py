"""Read other windows' geometry (KDE, via a KWin script pushing over D-Bus) so
the pet can perch on and be contained by them.

Best-effort and GATED: if the KWin/D-Bus feed never arrives (non-KDE, no
session bus), the listing stays empty and the pet just uses the screen floor
as before. Coordinates are X screen pixels, matching Qt's move() under
XWayland — no remapping needed.
"""
import os
from collections import namedtuple
from urllib.parse import unquote

# `title` actually holds the resourceClass; `pid` is the owning process id (or
# None when the feed predates pid reporting); `caption` is the window's visible
# title, the only thing that tells two windows of ONE process apart (see
# find_host). Defaults keep old 6-arg callers OK.
Win = namedtuple("Win", "wid x y w h title pid caption", defaults=(None, ""))

# Shell chrome / helper window classes, never perch targets. Covers both the
# KDE feed (plasmashell, xwaylandvideobridge) and the Win32 feed: "progman" and
# "workerw" are the Windows desktop/wallpaper host windows — full-screen,
# bottom-of-stack, and (Progman) titled "Program Manager", so they pass the
# generic filters and would otherwise be treated as a perch/containment target
# under the whole desktop (inverting "a pet on the wallpaper is always visible").
EXCLUDE_CLASSES = {"plasmashell", "xwaylandvideobridge", "claudlet", "",
                   "progman", "workerw"}


def parse_dump(text, min_size=40):
    """Parse a pipe-delimited window geometry feed (shared wire format used by
    the KWin script and other backends).

    Format: `id;class;x,y,w,h;pid;caption|...`  (coords may be floats; pid and
    caption optional). The caption is percent-encoded by the sender because
    real window titles contain both of our delimiters ("Teams - 채팅 | ...").
    Filters shell chrome and sub-min_size junk. Pure."""
    wins = []
    for tok in text.split("|"):
        tok = tok.strip()
        if not tok:
            continue
        parts = tok.split(";")
        if len(parts) < 3:
            continue
        wid, cls, geo = parts[0], parts[1], parts[2]
        cls = cls.strip().lower()
        if cls in EXCLUDE_CLASSES:
            continue
        nums = geo.split(",")
        if len(nums) != 4:
            continue
        try:
            x, y, w, h = (int(float(n)) for n in nums)
        except ValueError:
            continue
        if w < min_size or h < min_size:
            continue
        pid = None
        if len(parts) >= 4 and parts[3].strip().isdigit():
            pid = int(parts[3])
        caption = unquote(parts[4]) if len(parts) >= 5 else ""
        wins.append(Win(wid, x, y, w, h, cls, pid, caption))
    return wins


# Window classes that share a pid with a legit ancestor yet are never the host.
# On Windows, Windows Terminal launches via COM / DelegateExecute, so a Claude
# process's ancestor chain runs up through explorer.exe — and explorer owns a
# visible File Explorer window ("CabinetWClass") plus the taskbar
# ("Shell_TrayWnd"). Without this guard find_host adopts the File Explorer window
# as the host and every click-to-focus raises Explorer instead of the terminal.
NON_HOST_CLASSES = EXCLUDE_CLASSES | {"cabinetwclass", "shell_traywnd",
                                      "shell_secondarytraywnd"}


def project_of(caption):
    """The project/workspace a host window's caption says it is showing, or "".

    Some hosts run every window in ONE process, so pid-ancestry finds the app
    but cannot pick OUR window — the caption is the only thing that separates
    them. Two shapes cover the IDEs we see::

        openstackit-java - telegraf.conf [openstackit-java]   name, then file
        serafin [/home/me/IdeaProjects/serafin_v2_be]         name, then path

    The leading segment (before the first dash separator or bracket) is the
    project's DISPLAY name, which is what we compare -- whole, never as a
    substring, because "bnk-approval" is a prefix of "bnk-approval-fe" and a
    substring test hands one project the other's window. Pure."""
    head = (caption or "").split(" [")[0]
    for sep in (" \u2014 ", " \u2013 ", " - "):     # em dash, en dash, hyphen
        head = head.split(sep)[0]
    return head.strip()


def bracketed_path(caption):
    """The absolute path a caption carries in brackets, or "". Pure."""
    if "[" not in caption or "]" not in caption:
        return ""
    inner = caption[caption.index("[") + 1:caption.rindex("]")].strip()
    return inner if ("/" in inner or "\\" in inner) else ""


def pick_by_project(wins, project, cwd):
    """The one window among `wins` that is showing OUR project, or None.

    None when nothing matches AND when several do: with two candidates we do
    not know which is ours, and raising a coin-flip window is worse than
    leaving the pid-chosen one alone. Pure."""
    if not project and not cwd:
        return None
    hits = []
    for w in wins:
        cap = w.caption or ""
        if not cap:
            continue
        path = bracketed_path(cap)
        if (cwd and path and os.path.normpath(path) == os.path.normpath(cwd)) \
                or (project and project_of(cap) == project):
            hits.append(w)
    return hits[0] if len(hits) == 1 else None


def find_host(wins, ancestor_pids, project=None, cwd=None):
    """The window owned by this session's host app: the first whose pid is in
    `ancestor_pids` (the pet's Claude process and its parents — the terminal/IDE
    that owns the window is one of them), skipping shell-chrome windows that
    merely share a pid with a fake ancestor (see NON_HOST_CLASSES). None if no
    such window matches (the caller then falls back to a class match).

    When SEVERAL windows share that pid, the pid has told us everything it can:
    JetBrains runs every open project in one JVM, so all of them match and the
    first one the WM happens to list wins — every pet then points at the same
    arbitrary project. `project`/`cwd` let the caption break that tie; an
    ambiguous or absent caption falls back to the first match, i.e. exactly the
    old behaviour."""
    if not ancestor_pids:
        return None
    owned = [w for w in wins
             if w.pid is not None and w.pid in ancestor_pids
             and (w.title or "").lower() not in NON_HOST_CLASSES]
    if not owned:
        return None
    if len(owned) > 1:
        mine = pick_by_project(owned, project, cwd)
        if mine is not None:
            return mine
    return owned[0]


def pick_focus_target(wins, ancestor_pids, class_subs):
    """Choose the click-to-focus target from `wins` and return its wid, or None.

    Differs from find_host: the caller passes a MINIMIZED-INCLUSIVE window list
    (so a minimized host can be restored, since activate handles SW_RESTORE).
    Prefers a window whose pid is an ancestor of the Claude process (skipping
    shell chrome like explorer's File Explorer), then falls back to a window
    whose class contains one of `class_subs` (native-terminal classes)."""
    for w in wins:
        if (w.pid is not None and w.pid in (ancestor_pids or set())
                and (w.title or "").lower() not in NON_HOST_CLASSES):
            return w.wid
    subs = [s.lower() for s in (class_subs or []) if s]
    for w in wins:
        t = (w.title or "").lower()
        if any(s in t for s in subs):
            return w.wid
    return None


def window_under_feet(cx, feet_y, wins, tol=6):
    """The window a creature at column cx with feet at feet_y is resting ON — its
    top edge at or just below the feet (within tol). Highest such top wins. None
    when the feet are on the bare desktop (mirrors support_surface_under, but
    returns the Win so callers know WHICH window the pet is perched on)."""
    best = None
    for w in wins:
        if w.x <= cx <= w.x + w.w and abs(w.y - feet_y) <= tol:
            if best is None or w.y < best.y:
                best = w
    return best


def covered_by_higher(target, wins):
    """True if some window stacked ABOVE `target` fully covers its rect. `wins`
    is bottom->top stacking order (as the feed delivers it). Only full coverage
    counts — a maximized window on top hides it; a partial overlap doesn't."""
    try:
        i = wins.index(target)
    except ValueError:
        return False
    tx2, ty2 = target.x + target.w, target.y + target.h
    for w in wins[i + 1:]:
        if (w.x <= target.x and w.y <= target.y
                and w.x + w.w >= tx2 and w.y + w.h >= ty2):
            return True
    return False


def window_at(px, py, wins):
    """Topmost window whose rect contains (px, py), or None. wmctrl lists
    bottom-to-top, so the LAST containing window is the topmost."""
    hit = None
    for win in wins:
        if win.x <= px <= win.x + win.w and win.y <= py <= win.y + win.h:
            hit = win
    return hit


def top_surface_under(cx, wins, screen_bottom):
    """Y of the highest window top-edge whose horizontal span covers column cx
    (and is on-screen above the floor); else screen_bottom."""
    best = screen_bottom
    for win in wins:
        if win.x <= cx <= win.x + win.w and 0 <= win.y < best:
            best = win.y
    return best


def support_surface_under(cx, wins, screen_bottom, feet_y, tol=6):
    """The surface a creature at column cx with its feet at feet_y is resting on.

    Only window tops that are AT or BELOW the feet (within tol) count — the
    creature can rest on / fall onto them, but never auto-climbs onto a window
    whose top is above its feet. Among the eligible surfaces the highest
    (smallest y) wins; the screen floor is the fallback.

    This is the key difference from top_surface_under: standing on the desktop
    floor, windows above the feet are ignored (no teleport-up), yet a creature
    dropped/thrown above a window still lands on it."""
    best = screen_bottom
    for win in wins:
        if win.x <= cx <= win.x + win.w and (feet_y - tol) <= win.y < best:
            best = win.y
    return best
