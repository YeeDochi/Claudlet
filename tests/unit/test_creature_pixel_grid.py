import sys, os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtGui import QImage, QPainter
from PyQt6.QtWidgets import QApplication
from claudlet.core import creature as C

_app = QApplication.instance() or QApplication(sys.argv)


def test_r_rounds_half_up():
    assert [C._r(v) for v in (4.5, 5.5, 2.5, 0.5)] == [5, 6, 3, 1]
    assert [C._r(v) for v in (4.4, 4.6, 0.0)] == [4, 5, 0]
    assert [C._r(v) for v in (-0.5, -1.5, -1.6)] == [0, -1, -2]


def test_snap_size_is_independent_of_position():
    # the whole point: one art size is one pixel size wherever the block sits
    sizes = {C._snap(x, x, 5.0, 5.0)[2:] for x in (0.0, 0.1, 0.4, 0.5, 0.9, 12.6, 12.4)}
    assert sizes == {(5, 5)}


def test_snap_puts_origin_on_whole_pixels():
    x, y, _, _ = C._snap(12.6, 7.4, 4.5, 4.5)
    assert (x, y) == (13, 7)


def test_snap_never_collapses_a_block():
    # a 0.45-art-pixel highlight at u=2 is 0.9px; rounding it away loses the detail
    assert C._snap(0.0, 0.0, 0.9, 0.2)[2:] == (1, 1)


def test_snap_offset_lands_on_whole_device_pixels():
    for u in (2, 3, 5, 6):
        for dy in (0.0, 0.13, 0.5, 0.9, 1.37, -0.6):
            assert (C._snap_offset(dy, u) * u).is_integer()


def test_snap_offset_keeps_whole_pixel_offsets_exact():
    assert C._snap_offset(1.0, 5) == 1.0
    assert C._snap_offset(0.0, 5) == 0.0


def test_tilt_kept_by_default():
    assert C.SMOOTH_TILT_DEG == 0.0
    for t in (-16.0, -2.0, 0.4, 3.0, 10.0):
        assert C._tilt_for(t) == t


def test_tilt_dropped_below_threshold(monkeypatch):
    monkeypatch.setattr(C, "SMOOTH_TILT_DEG", 5.0)
    assert C._tilt_for(2.0) == 0.0
    assert C._tilt_for(-4.9) == 0.0
    assert C._tilt_for(5.0) == 5.0
    assert C._tilt_for(-16.0) == -16.0


U = 5
W = (C.GRID_W + 2) * U
H = (C.GRID_H + 4) * U


def _opaque_pixels(state, frame, **kw):
    img = QImage(W, H, QImage.Format.Format_ARGB32)
    img.fill(0)
    p = QPainter(img)
    p.setRenderHint(QPainter.RenderHint.Antialiasing, False)
    C.draw_creature(p, U, 2 * U, U, state, frame, **kw)
    p.end()
    buf = bytes(img.constBits().asarray(img.sizeInBytes()))
    return sum(1 for a in buf[3::4] if a > 128)


def test_bob_steps_whole_pixels_so_the_silhouette_does_not_breathe():
    # These states bob but never tilt, so the only thing changing between frames
    # is the shared vertical offset. A fractional offset re-split every art pixel
    # and the opaque area wobbled by ~40px; quantised, the area must hold.
    for state, frames in (("idle", range(0, 34)), ("work_computer", range(0, 30))):
        areas = {_opaque_pixels(state, f) for f in frames}
        assert len(areas) == 1, "%s: silhouette area varied %s" % (state, sorted(areas))


def test_tilted_frames_still_render_every_state():
    for state in C.STATES:
        for frame in (0, 7, 33, 65):
            assert _opaque_pixels(state, frame) > 0
