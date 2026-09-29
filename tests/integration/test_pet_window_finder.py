"""Window finder: list windows (minimized too) and pull one out — the pet
then brings it back. Driven through the socket; world set via the geom feed."""
from urllib.parse import quote

from harness import pet, send_hook, window_list  # noqa: F401


def _row(wid, cls, x, y, w, h, caption, flag=""):
    return "%s;%s;%d,%d,%d,%d;1;%s;%s" % (wid, cls, x, y, w, h, quote(caption, safe=""), flag)


def test_lists_minimized_windows_but_does_not_perch_on_them(pet):
    pet._on_geom("|".join([
        _row("w1", "konsole", 0, 0, 600, 400, "claude"),
        _row("w2", "slack", 300, 300, 500, 400, "Slack | 일반", "min"),
    ]))
    rows = window_list(pet)
    assert [(r["id"], r["state"]) for r in rows] == [("w2", "min"), ("w1", "shown")]
    assert rows[0]["title"] == "Slack | 일반"
    assert [w.wid for w in pet._wins] == ["w1"]      # hidden row never perched on


def _tick_until(pet, cond, n=600):
    for _ in range(n):
        pet._tick()
        if cond(pet.snapshot()):
            return True
    return False


def test_fetch_dashes_off_then_comes_back_riding_the_window(pet):
    # docked by default: fetching must still leave the slot
    pet._on_geom(_row("w9", "slack", 200, 400, 500, 300, "Slack", "min"))
    send_hook(pet, cmd="raise", id="w9")
    assert pet.snapshot()["fetch_phase"] == "out"
    # the window must NOT come up before the pet is out of sight
    assert _tick_until(pet, lambda s: s["fetch_phase"] == "gone")
    assert pet.snapshot()["hidden"]
    pet._tick()
    assert pet.snapshot()["fetch_phase"] == "gone"     # still waiting on the WM
    pet._on_geom(_row("w9", "slack", 200, 400, 500, 300, "Slack"))   # restored
    pet._tick()
    snap = pet.snapshot()
    assert snap["fetch_phase"] == "ride" and not snap["hidden"]
    assert snap["render"] == "celebrate"
    assert abs(pet.y + pet.foot_y - 400) < 1            # standing on its top edge
    assert 200 <= pet.x + pet.w / 2.0 <= 700


def test_fetch_rides_inside_a_maximized_window(pet):
    pet._on_geom(_row("w9", "code", 0, 0, 800, 800, "code", "min"))
    send_hook(pet, cmd="raise", id="w9")
    assert _tick_until(pet, lambda s: s["fetch_phase"] == "gone")
    pet._on_geom(_row("w9", "code", 0, 0, 800, 800, "code"))
    pet._tick()
    assert pet.snapshot()["contained"] == "w9"          # top edge is off-screen


def test_raise_ignores_ids_the_finder_does_not_list(pet):
    pet._on_geom(_row("w1", "konsole", 0, 0, 600, 400, "claude"))
    send_hook(pet, cmd="raise", id='x"; evil(); "')
    assert pet.snapshot()["fetching"] is None
