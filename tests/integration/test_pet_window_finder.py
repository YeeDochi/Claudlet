"""Window finder: list windows (minimized too) and pull one out — the pet
then heads into it. Driven through the socket; world set via the geom feed."""
from urllib.parse import quote

from harness import pet, send_hook, window_list, undock  # noqa: F401


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


def test_raise_sends_the_pet_into_the_pulled_out_window(pet):
    undock(pet)
    pet._on_geom(_row("w9", "slack", 200, 500, 600, 300, "Slack", "min"))
    pet.x, pet.y = 100.0, float(pet.floor_y)
    send_hook(pet, cmd="raise", id="w9")
    assert pet.snapshot()["fetching"] == "w9"
    pet._on_geom(_row("w9", "slack", 200, 500, 600, 300, "Slack"))   # WM restored it
    for _ in range(600):
        pet._tick()
        if pet.snapshot()["fetching"] is None:
            break
    assert pet.snapshot()["fetching"] is None
    assert pet.snapshot()["contained"] == "w9"           # it went in


def test_raise_ignores_ids_the_finder_does_not_list(pet):
    pet._on_geom(_row("w1", "konsole", 0, 0, 600, 400, "claude"))
    send_hook(pet, cmd="raise", id='x"; evil(); "')
    assert pet.snapshot()["fetching"] is None
