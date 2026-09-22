"""The accessibility backend is optional; absence must never be fatal.

Verified 2026-09-22 on the dev machine: pyobjc-core/Cocoa/Quartz/WebKit are
installed and none export AXUIElementCreateApplication, so this is the live
path for anyone who hasn't installed pyobjc-framework-ApplicationServices --
not a hypothetical branch.
"""
from claudlet.platform import axtree


def _reset():
    axtree._AX = None
    axtree._TRIED = False


def test_importing_the_module_never_raises():
    assert axtree.available() in (True, False)


def test_unreadable_backend_returns_none_not_an_exception(monkeypatch):
    _reset()
    monkeypatch.setattr(axtree, "_api", lambda: None)
    assert axtree.read_window(object()) is None
    assert axtree.trusted() is False


def test_none_window_is_handled():
    assert axtree.read_window(None) is None


def test_hint_names_the_missing_package(monkeypatch):
    _reset()
    monkeypatch.setattr(axtree, "_api", lambda: None)
    hint = axtree.install_hint()
    assert "ApplicationServices" in hint


def test_hint_asks_for_permission_when_the_package_is_there(monkeypatch):
    _reset()
    monkeypatch.setattr(axtree, "_api", lambda: object())
    monkeypatch.setattr(axtree, "trusted", lambda: False)
    assert "손쉬운 사용" in axtree.install_hint()


def test_no_hint_when_everything_is_available(monkeypatch):
    _reset()
    monkeypatch.setattr(axtree, "_api", lambda: object())
    monkeypatch.setattr(axtree, "trusted", lambda: True)
    assert axtree.install_hint() is None


def test_trusted_is_false_when_the_check_itself_blows_up(monkeypatch):
    class Boom:
        @staticmethod
        def AXIsProcessTrusted():
            raise OSError("denied")
    _reset()
    monkeypatch.setattr(axtree, "_api", lambda: Boom)
    assert axtree.trusted() is False


def test_frame_reads_object_style_values():
    class P:
        x, y = 5, 6
    class S:
        width, height = 7, 8
    assert axtree._frame(P, S) == (5, 6, 7, 8)


def test_frame_reads_sequence_style_values():
    assert axtree._frame((1, 2), (3, 4)) == (1, 2, 3, 4)


def test_frame_of_garbage_is_none():
    assert axtree._frame(None, None) is None
    assert axtree._frame("x", "y") is None


# ---------- region filtering ----------

def test_intersects_is_overlap_not_containment():
    # a label straddling the edge of the drag is part of what was pointed at
    assert axtree.intersects((90, 90, 40, 40), (100, 100, 100, 100))


def test_intersects_rejects_a_disjoint_frame():
    assert not axtree.intersects((0, 0, 10, 10), (100, 100, 50, 50))


def test_intersects_accepts_a_contained_frame():
    assert axtree.intersects((110, 110, 10, 10), (100, 100, 100, 100))


def test_intersects_of_missing_data_is_false():
    assert not axtree.intersects(None, (0, 0, 10, 10))
    assert not axtree.intersects((0, 0, 10, 10), None)


def test_read_region_degrades_without_a_backend(monkeypatch):
    _reset()
    monkeypatch.setattr(axtree, "_api", lambda: None)
    assert axtree.read_region(object(), (0, 0, 10, 10)) is None


def test_read_region_of_nothing_is_none():
    assert axtree.read_region(None, (0, 0, 10, 10)) is None
    assert axtree.read_region(object(), None) is None


def test_frame_unwraps_axvalue_objects():
    """The real API returns opaque AXValues; only AXValueGetValue unwraps them."""
    class Pt:
        x, y = 5.0, 6.0
    class Sz:
        width, height = 7.0, 8.0
    class FakeAX:
        kAXValueCGPointType = 1
        kAXValueCGSizeType = 2
        @staticmethod
        def AXValueGetValue(val, kind, _):
            return True, (Pt if kind == 1 else Sz)
    assert axtree._frame(object(), object(), FakeAX) == (5, 6, 7, 8)


def test_frame_falls_back_when_unwrapping_fails():
    class FakeAX:
        kAXValueCGPointType = 1
        kAXValueCGSizeType = 2
        @staticmethod
        def AXValueGetValue(val, kind, _):
            return False, None
    class P:
        x, y = 1, 2
    class S:
        width, height = 3, 4
    assert axtree._frame(P, S, FakeAX) == (1, 2, 3, 4)
