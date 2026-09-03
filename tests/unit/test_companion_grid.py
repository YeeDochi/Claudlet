import sys, os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication
from claudlet.core import creature as C
from claudlet import pet as P

_app = QApplication.instance() or QApplication(sys.argv)


def test_companion_unit_is_whole_pixels():
    # a fractional unit made every companion art pixel alternate 2px/3px wide
    assert float(P.COMPANION_U).is_integer(), P.COMPANION_U


def test_companion_window_holds_the_whole_sprite():
    # (GRID_H + 2 * PAD_Y) * 2.5 was 52.5, so int() clipped half a pixel off the
    # window and the sprite lost its bottom row
    w = (C.GRID_W + 2 * P.PAD_X) * P.COMPANION_U
    h = (C.GRID_H + 2 * P.PAD_Y) * P.COMPANION_U
    assert int(w) == w and int(h) == h, (w, h)


def test_companion_draw_origin_is_on_the_grid():
    assert float(P.PAD_X * P.COMPANION_U).is_integer()
    assert float(P.PAD_Y * P.COMPANION_U).is_integer()
