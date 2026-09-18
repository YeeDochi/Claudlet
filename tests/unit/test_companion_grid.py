import sys, os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication
from claudlet.core import creature as C
from claudlet import pet as P
from claudlet.core import petconfig

_app = QApplication.instance() or QApplication(sys.argv)


def test_companion_unit_is_whole_pixels_at_every_scale():
    # a fractional unit made every companion art pixel alternate 2px/3px wide,
    # so the companion scale must stay whole however the pet is scaled
    for u in range(petconfig.MIN_SCALE, petconfig.MAX_SCALE + 1):
        cu = P._companion_scale(u)
        assert float(cu).is_integer(), (u, cu)
        assert cu >= petconfig.MIN_SCALE, (u, cu)


def test_companion_is_never_bigger_than_the_pet_it_follows():
    # the floor was a hard 2, from when that was also the pet's minimum. A
    # creature carrying finer art runs at 1, and the floor then drew its
    # companion at twice the size of the pet it was trailing.
    for u in range(petconfig.MIN_SCALE, petconfig.MAX_SCALE + 1):
        assert P._companion_scale(u) <= u, u


def test_companion_window_holds_the_whole_sprite():
    # (GRID_H + 2 * PAD_Y) * 2.5 was 52.5, so int() clipped half a pixel off the
    # window and the sprite lost its bottom row
    for u in range(petconfig.MIN_SCALE, petconfig.MAX_SCALE + 1):
        cu = P._companion_scale(u)
        w = (C.GRID_W + 2 * P.PAD_X) * cu
        h = (C.GRID_H + 2 * P.PAD_Y) * cu
        assert int(w) == w and int(h) == h, (u, w, h)


def test_companion_draw_origin_is_on_the_grid():
    for u in range(petconfig.MIN_SCALE, petconfig.MAX_SCALE + 1):
        cu = P._companion_scale(u)
        assert float(P.PAD_X * cu).is_integer()
        assert float(P.PAD_Y * cu).is_integer()
