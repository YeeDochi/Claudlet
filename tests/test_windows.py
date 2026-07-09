import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
import windows

SAMPLE = ("{id1};plasmashell;0,0,1920,1200|"         # desktop -> filtered
          "{id2};org.kde.konsole;100.5,200.2,400,300|"  # kept (float coords)
          "{id3};claude-pet;1356,1094,120,105|"        # pet -> filtered
          "{id4};;0,0,32,32")                          # empty class -> filtered


def test_parse_kwin_dump_filters_and_ints():
    wins = windows.parse_kwin_dump(SAMPLE)
    assert len(wins) == 1
    k = wins[0]
    assert k.title == "org.kde.konsole"
    assert (k.x, k.y, k.w, k.h) == (100, 200, 400, 300)   # floats floored to int


def test_parse_kwin_dump_skips_malformed():
    assert windows.parse_kwin_dump("garbage|;;|id;cls;1,2,3") == []


def test_window_at_and_surface_via_dump():
    wins = windows.parse_kwin_dump(SAMPLE)
    assert windows.window_at(150, 250, wins).title == "org.kde.konsole"
    assert windows.top_surface_under(150, wins, 1080) == 200
    assert windows.top_surface_under(3000, wins, 1080) == 1080


def test_window_at_outside_returns_none():
    wins = windows.parse_kwin_dump(SAMPLE)
    assert windows.window_at(5000, 5000, wins) is None
