import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
import windows
from windows import Win

SAMPLE = (
    "0x01800007  0 -99  0    100 100 host Xwayland bridge\n"
    "0x01a0000d  0 1150 1094 120 105 host claude-pet-live\n"
    "0x02000001  0 100  200  400 300 host My Konsole Window\n"
)


def test_parse_fields_and_title_with_spaces():
    wins = windows.parse_wmctrl_lg(SAMPLE)
    assert len(wins) == 3
    k = wins[2]
    assert (k.x, k.y, k.w, k.h) == (100, 200, 400, 300)
    assert k.title == "My Konsole Window"


def test_parse_skips_malformed():
    assert windows.parse_wmctrl_lg("garbage\n0x1 0 a b c d host t") == []


def test_window_at():
    wins = windows.parse_wmctrl_lg(SAMPLE)
    hit = windows.window_at(150, 250, wins)      # inside Konsole rect
    assert hit is not None and hit.title == "My Konsole Window"
    assert windows.window_at(5000, 5000, wins) is None


def test_top_surface_under():
    wins = windows.parse_wmctrl_lg(SAMPLE)
    # cx=150 is over Konsole (x 100..500), its top y=200 is the surface
    assert windows.top_surface_under(150, wins, 1080) == 200
    # cx=3000 covers nothing -> screen bottom
    assert windows.top_surface_under(3000, wins, 1080) == 1080


def test_list_windows_gated_without_wmctrl(monkeypatch):
    monkeypatch.setattr(windows.shutil, "which", lambda _: None)
    assert windows.list_windows() == []


def test_list_windows_filters_prefix_and_small(monkeypatch):
    monkeypatch.setattr(windows.shutil, "which", lambda _: "/usr/bin/wmctrl")
    monkeypatch.setattr(windows.subprocess, "check_output", lambda *a, **k: SAMPLE)
    wins = windows.list_windows()
    titles = [w.title for w in wins]
    assert "My Konsole Window" in titles
    assert all(not t.startswith("claude-pet-") for t in titles)   # pet excluded
    # the 100x100 bridge passes min_size(40); the pet is excluded by prefix
