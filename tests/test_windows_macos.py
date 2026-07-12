"""Tests for the pure parts of the macOS Quartz geometry backend.

The actual CGWindowListCopyWindowInfo call can only be exercised on real
macOS hardware (which nobody writing this had — the module is SPECULATIVE);
these tests cover what's testable anywhere: import safety, the no-backend
no-op path, the info-dict -> row filtering, and the wire-format output
round-tripping through windows.parse_kwin_dump."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
from claudlet import windows_macos
from claudlet import windows


def _info(layer=0, x=10, y=20, w=300, h=200, pid=555, owner="Terminal",
          name=None, alpha=None, number=42):
    d = {
        windows_macos.K_LAYER: layer,
        windows_macos.K_BOUNDS: {"X": float(x), "Y": float(y),
                              "Width": float(w), "Height": float(h)},
        windows_macos.K_OWNER_PID: pid,
        windows_macos.K_NUMBER: number,
    }
    if owner is not None:
        d[windows_macos.K_OWNER_NAME] = owner
    if name is not None:
        d[windows_macos.K_NAME] = name
    if alpha is not None:
        d[windows_macos.K_ALPHA] = alpha
    return d


def test_import_and_dump_noop_without_quartz(monkeypatch):
    # On non-macOS (and macOS without pyobjc) Quartz is None: importable,
    # available() False, dump() just "".
    monkeypatch.setattr(windows_macos, "Quartz", None)
    assert windows_macos.available() is False
    assert windows_macos.dump() == ""
    assert windows_macos.dump(exclude_pid=123) == ""
    assert windows_macos._enum_windows() == []


def test_row_from_info_normal_window():
    row = windows_macos._row_from_info(_info())
    assert row == (42, "terminal", 10, 20, 300, 200, 555)


def test_row_from_info_filters():
    assert windows_macos._row_from_info(_info(layer=25)) is None      # menu bar etc.
    assert windows_macos._row_from_info(_info(alpha=0.0)) is None     # fully transparent
    assert windows_macos._row_from_info(_info(w=0)) is None           # degenerate rect
    assert windows_macos._row_from_info(_info(), exclude_pid=555) is None  # the pet itself
    assert windows_macos._row_from_info({windows_macos.K_LAYER: 0}) is None   # no bounds
    assert windows_macos._row_from_info({}) is None                   # empty/odd dict


def test_row_from_info_alpha_partial_kept():
    assert windows_macos._row_from_info(_info(alpha=0.9)) is not None


def test_row_class_falls_back_to_window_name():
    # No Screen Recording permission normally means kCGWindowName is absent
    # and kCGWindowOwnerName present; the reverse fallback still yields a class.
    row = windows_macos._row_from_info(_info(owner=None, name="My App"))
    assert row[1] == "my app"
    row = windows_macos._row_from_info(_info(owner=None, name=None))
    assert row[1] == ""      # parse_kwin_dump's EXCLUDE_CLASSES drops it later


def test_row_class_sanitizes_wire_delimiters():
    row = windows_macos._row_from_info(_info(owner="We;rd|App"))
    assert ";" not in row[1] and "|" not in row[1]


def test_row_rounds_float_bounds():
    row = windows_macos._row_from_info(_info(x=10.6, y=19.4, w=300.5, h=199.5))
    assert row[2:6] == (11, 19, 300, 200)


class _FakeQuartz:
    """Just enough Quartz surface for dump(): option constants + the call."""
    kCGWindowListOptionOnScreenOnly = 1
    kCGWindowListExcludeDesktopElements = 16
    kCGNullWindowID = 0

    def __init__(self, infos):
        self._infos = infos
        self.calls = []

    def CGWindowListCopyWindowInfo(self, opts, relative_to):
        self.calls.append((opts, relative_to))
        return self._infos


def test_dump_reverses_to_bottom_up_and_roundtrips(monkeypatch):
    # CGWindowListCopyWindowInfo returns topmost-FIRST; the wire format wants
    # bottom-to-top, so the front window must come LAST in the dump.
    fake = _FakeQuartz([
        _info(number=1, owner="Front App", x=0, y=0, w=500, h=400, pid=100),
        _info(number=99, layer=25, owner="Menubar"),          # filtered out
        _info(number=2, owner="Back App", x=50, y=60, w=640, h=480, pid=200),
    ])
    monkeypatch.setattr(windows_macos, "Quartz", fake)
    dump = windows_macos.dump()
    assert dump == "2;back app;50,60,640,480;200|1;front app;0,0,500,400;100"
    # both option flags requested, relative to the null window id
    assert fake.calls == [(17, 0)]

    wins = windows.parse_kwin_dump(dump)
    assert [w.wid for w in wins] == ["2", "1"]
    assert wins[-1].title == "front app"        # topmost last, per contract
    assert wins[-1].pid == 100
    # topmost-last order is what windows.window_at relies on
    assert windows.window_at(10, 10, wins).wid == "1"


def test_dump_excludes_pid(monkeypatch):
    fake = _FakeQuartz([
        _info(number=1, pid=100),
        _info(number=2, pid=200),
    ])
    monkeypatch.setattr(windows_macos, "Quartz", fake)
    dump = windows_macos.dump(exclude_pid=100)
    assert "100" not in dump
    assert dump.startswith("2;")


def test_dump_empty_feed(monkeypatch):
    monkeypatch.setattr(windows_macos, "Quartz", _FakeQuartz(None))
    assert windows_macos.dump() == ""
    monkeypatch.setattr(windows_macos, "Quartz", _FakeQuartz([]))
    assert windows_macos.dump() == ""


def test_dump_survives_raising_backend(monkeypatch):
    class _Boom(_FakeQuartz):
        def CGWindowListCopyWindowInfo(self, opts, relative_to):
            raise RuntimeError("no window server connection")
    monkeypatch.setattr(windows_macos, "Quartz", _Boom([]))
    assert windows_macos.dump() == ""      # never raises into the poll timer


# --- proc_ancestors (ps-based; does NOT need pyobjc, so it's exercised anywhere) ---

def test_proc_ancestors_empty_for_bad_pid():
    assert windows_macos.proc_ancestors(None) == set()
    assert windows_macos.proc_ancestors("not-a-pid") == set()


def test_proc_ancestors_empty_without_ps(monkeypatch):
    monkeypatch.setattr(windows_macos, "_proc_parents", lambda: {})
    assert windows_macos.proc_ancestors(1234) == set()


def test_proc_ancestors_walks_mocked_tree(monkeypatch):
    # 4321 -> 300 -> 200 -> 1 (init); the walk collects the chain, stops at root
    monkeypatch.setattr(windows_macos, "_proc_parents",
                        lambda: {4321: 300, 300: 200, 200: 1, 999: 998})
    assert windows_macos.proc_ancestors(4321) == {4321, 300, 200}


def test_proc_ancestors_survives_a_cycle(monkeypatch):
    # a bogus ppid cycle must terminate (cur-in-acc guard), not spin forever
    monkeypatch.setattr(windows_macos, "_proc_parents", lambda: {10: 20, 20: 10})
    assert windows_macos.proc_ancestors(10) == {10, 20}


def test_proc_ancestors_respects_max_hops(monkeypatch):
    chain = {i: i + 1 for i in range(2, 100)}
    monkeypatch.setattr(windows_macos, "_proc_parents", lambda: chain)
    assert len(windows_macos.proc_ancestors(2, max_hops=5)) == 5


def test_proc_ancestors_walks_real_process_tree():
    if sys.platform != "darwin":
        return
    acc = windows_macos.proc_ancestors(os.getpid())
    assert os.getpid() in acc
    assert len(acc) >= 1


# --- self-calibration (CG coords -> Qt logical, from the pet's own window) -----

def test_calibration_noop_without_own_or_ref():
    assert windows_macos._calibration(None, (150, 200, 0, 0)) == (1.0, 0.0, 0.0)
    assert windows_macos._calibration((0, 0, 300, 400), None) == (1.0, 0.0, 0.0)


def test_calibration_detects_2x_pixels():
    # CG reports our 150x200-pt window as 300x400 px -> scale 2.0 (Retina)
    scale, ox, oy = windows_macos._calibration((0, 0, 300, 400), (150, 200, 0, 0))
    assert scale == 2.0 and (ox, oy) == (0.0, 0.0)


def test_calibration_recovers_origin_offset():
    # window at CG (100,200) size 300x400; Qt says it's at (10,20) size 150x200
    scale, ox, oy = windows_macos._calibration((100, 200, 300, 400), (150, 200, 10, 20))
    assert scale == 2.0
    assert ox == 100 / 2.0 - 10 and oy == 200 / 2.0 - 20    # 40, 80


def test_calibration_refuses_implausible_scale():
    # a bogus tiny/huge ratio must NOT be trusted (feature stays unscaled)
    assert windows_macos._calibration((0, 0, 3000, 4000), (150, 200, 0, 0)) == (1.0, 0.0, 0.0)


def test_own_bounds_finds_largest_any_layer():
    # our window is a Tool/always-on-top window (layer != 0); _own_bounds must
    # still find it (unlike the layer-0-only feed filter), and pick the largest.
    infos = [
        _info(number=1, pid=42, layer=25, x=0, y=0, w=300, h=400),   # ours (big)
        _info(number=2, pid=42, layer=25, x=5, y=5, w=20, h=20),     # ours (tiny popup)
        _info(number=3, pid=99, layer=0, x=0, y=0, w=999, h=999),    # someone else
    ]
    assert windows_macos._own_bounds(infos, 42) == (0.0, 0.0, 300.0, 400.0)
    assert windows_macos._own_bounds(infos, 12345) is None


def test_own_bounds_with_ref_ignores_a_bigger_menu_popup():
    # Bug repro: right-clicking opens a QMenu — another window owned by the pet's
    # pid, on a higher layer, and LARGER than the pet's tiny body. The old
    # "pick the largest owned window" rule made that MENU the calibration ruler,
    # yielding a wrong scale/offset that flung the pet across the screen. With the
    # Qt ref given, _own_bounds must pick the window whose aspect matches the pet
    # (uniform DPR scaling), i.e. the body, not the aspect-mismatched menu.
    ref = (150, 200, 0, 0)                                  # pet Qt logical size 150x200
    infos = [
        _info(number=1, pid=42, layer=25, x=0, y=0, w=300, h=400),      # pet body, 2x -> aspect matches
        _info(number=2, pid=42, layer=101, x=40, y=40, w=360, h=520),   # right-click menu, bigger, wrong aspect
    ]
    assert windows_macos._own_bounds(infos, 42, ref) == (0.0, 0.0, 300.0, 400.0)
    # without a ref, the old largest-wins behaviour is preserved.
    assert windows_macos._own_bounds(infos, 42) == (40.0, 40.0, 360.0, 520.0)


def test_dump_with_ref_scales_other_windows(monkeypatch):
    SELF = 42
    fake = _FakeQuartz([
        _info(number=1, pid=SELF, layer=25, x=0, y=0, w=300, h=400),   # pet window (ruler)
        _info(number=2, pid=200, layer=0, x=100, y=120, w=640, h=480),  # a real window
    ])
    monkeypatch.setattr(windows_macos, "Quartz", fake)
    dump = windows_macos.dump(exclude_pid=SELF, ref=(150, 200, 0, 0))   # -> scale 2.0
    # the other window's coords are halved into Qt points; our own window (the
    # ruler) is excluded from the feed. _info's default owner is "Terminal".
    assert dump == "2;terminal;50,60,320,240;200"
    assert windows_macos.LAST_CAL[0] == 2.0
    # one CGWindowListCopyWindowInfo call serves both the feed and calibration
    assert fake.calls == [(17, 0)]
