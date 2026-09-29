"""An app's icon as a tiny pixel sprite the creature can carry.

Linux only for now: the window feed carries each window's desktop-file id
(KWin `desktopFileName`, falling back to its resourceClass). That id names a
`.desktop` entry whose `Icon=` is either an absolute image path (snaps) or a
theme icon name. The image is then shrunk nearest-neighbour to a few art
pixels so it reads like the rest of the code-drawn art.

`icon_value` and `pixelize` are the logic and are tested with data; `sprite_for`
is the thin IO shell (reads the XDG dirs, asks the icon theme)."""
import configparser
import functools
import os

SPRITE = 8          # art pixels per side of a carried icon
ALPHA_CUT = 110     # a pixel fainter than this is background, not icon


def icon_value(app_id, entries):
    """`Icon=` of the desktop entry for `app_id`, or None.

    `entries` is {filename: raw .desktop text}. Matches `<app_id>.desktop`
    first, then any entry whose StartupWMClass is `app_id` (IntelliJ's snap:
    class `jetbrains-idea`, file `intellij-idea-community_...desktop`). Case
    folded both ways — WM classes and file names disagree on case. Pure."""
    if not app_id:
        return None
    want = app_id.casefold()
    parsed = []
    for name, text in (entries or {}).items():
        try:
            cp = configparser.RawConfigParser(strict=False, interpolation=None)
            cp.read_string(text)
            entry = cp["Desktop Entry"]
        except Exception:
            continue
        parsed.append((name[:-len(".desktop")].casefold(), entry))
    for stem, entry in parsed:
        if stem == want and entry.get("Icon"):
            return entry.get("Icon")
    for _stem, entry in parsed:
        if (entry.get("StartupWMClass") or "").casefold() == want and entry.get("Icon"):
            return entry.get("Icon")
    return None


def pixelize(img, size=SPRITE):
    """QImage -> size x size rows of (r, g, b) or None (transparent).

    Nearest-neighbour shrink keeps hard edges; faint pixels drop out; every
    transparent pixel touching the icon becomes a dark outline so the icon
    stays legible on any wallpaper. None for an image with nothing opaque."""
    from PyQt6.QtCore import Qt
    from PyQt6.QtGui import QImage
    if img is None or img.isNull():
        return None
    img = img.convertToFormat(QImage.Format.Format_ARGB32)
    # shrink to the inner area: one pixel each side is kept for the outline
    inner = size - 2
    small = img.scaled(inner, inner, Qt.AspectRatioMode.KeepAspectRatio,
                       Qt.TransformationMode.FastTransformation)
    dx, dy = (size - small.width()) // 2, (size - small.height()) // 2
    grid = [[None] * size for _ in range(size)]
    for y in range(small.height()):
        for x in range(small.width()):
            c = small.pixelColor(x, y)
            if c.alpha() >= ALPHA_CUT:
                grid[y + dy][x + dx] = (c.red(), c.green(), c.blue())
    if not any(any(row) for row in grid):
        return None
    edge = (24, 22, 30)
    solid = [[c is not None for c in row] for row in grid]
    for y in range(size):
        for x in range(size):
            if solid[y][x]:
                continue
            if any(0 <= y + j < size and 0 <= x + i < size and solid[y + j][x + i]
                   for i, j in ((1, 0), (-1, 0), (0, 1), (0, -1))):
                grid[y][x] = edge
    return grid


def _data_dirs():
    home = os.environ.get("XDG_DATA_HOME") or os.path.expanduser("~/.local/share")
    rest = os.environ.get("XDG_DATA_DIRS") or "/usr/local/share:/usr/share"
    return [home] + [d for d in rest.split(":") if d]


@functools.lru_cache(maxsize=1)
def _entries():
    # ponytail: read once per pet; an app installed while the pet runs shows
    # no icon until restart
    out = {}
    for d in _data_dirs():
        apps = os.path.join(d, "applications")
        try:
            names = os.listdir(apps)
        except OSError:
            continue
        for name in names:
            if name.endswith(".desktop") and name not in out:   # earlier dir wins
                try:
                    with open(os.path.join(apps, name), encoding="utf-8") as f:
                        out[name] = f.read()
                except (OSError, UnicodeDecodeError):
                    continue
    return out


@functools.lru_cache(maxsize=64)
def sprite_for(app_id):
    """Carried-icon sprite for the app `app_id`, or None. Never raises."""
    try:
        from PyQt6.QtGui import QIcon, QImage
        value = icon_value(app_id, _entries()) or app_id
        if os.path.isabs(value):
            img = QImage(value)
        else:
            icon = QIcon.fromTheme(value)
            img = icon.pixmap(48, 48).toImage() if not icon.isNull() else None
        return pixelize(img)
    except Exception:
        return None
