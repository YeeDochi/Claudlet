from PyQt6.QtGui import QColor, QImage

from claudlet.core.appicon import icon_value, pixelize

CODE = "[Desktop Entry]\nName=VS Code\nIcon=/snap/code/current/meta/gui/vscode.png\nExec=code %F\n"
IDEA = "[Desktop Entry]\nName=IDEA\nIcon=/snap/idea.png\nStartupWMClass=jetbrains-idea\n"


def test_icon_value_matches_file_name_then_wm_class():
    entries = {"code_code.desktop": CODE,
               "intellij-idea-community_intellij-idea-community.desktop": IDEA,
               "broken.desktop": "not ini at all ["}
    assert icon_value("code_code", entries) == "/snap/code/current/meta/gui/vscode.png"
    assert icon_value("Jetbrains-Idea", entries) == "/snap/idea.png"
    assert icon_value("slack", entries) is None
    assert icon_value("", entries) is None


def _img(w, h, fill):
    img = QImage(w, h, QImage.Format.Format_ARGB32)
    img.fill(QColor(0, 0, 0, 0))
    for y in range(h):
        for x in range(w):
            if fill(x, y):
                img.setPixelColor(x, y, QColor(200, 30, 30))
    return img


def test_pixelize_shrinks_drops_faint_pixels_and_outlines():
    g = pixelize(_img(48, 48, lambda x, y: 12 <= x < 36 and 12 <= y < 36), size=8)
    assert len(g) == 8 and all(len(r) == 8 for r in g)
    red = [(x, y) for y, r in enumerate(g) for x, c in enumerate(r) if c == (200, 30, 30)]
    assert red and all(1 <= x <= 6 and 1 <= y <= 6 for x, y in red)
    # every icon pixel on the rim of its blob touches an outline pixel
    x, y = min(red)
    assert g[y][x - 1] == (24, 22, 30)
    assert g[0][0] is None                               # corners stay clear


def test_pixelize_of_nothing_is_none():
    assert pixelize(_img(16, 16, lambda x, y: False)) is None
    assert pixelize(QImage()) is None
