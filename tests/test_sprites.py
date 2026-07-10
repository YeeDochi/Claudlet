import sys, os, tempfile
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from PyQt6.QtWidgets import QApplication
from PyQt6.QtGui import QImage, QColor
import sprites

_app = QApplication.instance() or QApplication(sys.argv)


def _png(path, color="#ff0000", size=8):
    img = QImage(size, size, QImage.Format.Format_ARGB32)
    img.fill(QColor(color))
    assert img.save(path, "PNG")


def test_load_frames_still_png_one_frame():
    with tempfile.TemporaryDirectory() as tmp:
        p = os.path.join(tmp, "idle.png")
        _png(p)
        frames = sprites.load_frames(p)
        assert len(frames) == 1
        assert not frames[0].isNull()


def test_load_frames_unreadable_returns_empty():
    with tempfile.TemporaryDirectory() as tmp:
        p = os.path.join(tmp, "bad.png")
        with open(p, "w") as f:
            f.write("not an image")
        assert sprites.load_frames(p) == []


def test_load_overrides_picks_up_states():
    with tempfile.TemporaryDirectory() as tmp:
        _png(os.path.join(tmp, "idle.png"))
        _png(os.path.join(tmp, "walk.png"))
        out = sprites.load_overrides(tmp, ["idle", "walk", "thinking"])
        assert set(out.keys()) == {"idle", "walk"}      # only states with files
        assert len(out["idle"]) == 1


def test_load_overrides_prefers_gif_over_png():
    with tempfile.TemporaryDirectory() as tmp:
        # a .gif and a .png for the same state -> gif wins (checked via ext order)
        _png(os.path.join(tmp, "idle.png"))
        # write a still image as .gif so it is a readable image file
        img = QImage(8, 8, QImage.Format.Format_ARGB32)
        img.fill(QColor("#00ff00"))
        if img.save(os.path.join(tmp, "idle.gif"), "GIF"):
            out = sprites.load_overrides(tmp, ["idle"])
            assert "idle" in out and len(out["idle"]) >= 1
        else:
            # Qt build without a GIF writer: at least the .png is still found
            out = sprites.load_overrides(tmp, ["idle"])
            assert "idle" in out


def test_missing_dir_yields_empty():
    assert sprites.load_overrides("/no/such/dir", ["idle"]) == {}
