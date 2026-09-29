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


def test_fetch_sinks_into_the_floor_then_comes_back_riding_the_window(pet):
    # the plain path (Windows/macOS): the window shows itself, the pet hops on
    pet._can_pull = False
    # docked by default: fetching must still leave the slot
    pet._on_geom(_row("w9", "slack", 200, 400, 500, 300, "Slack", "min"))
    pet.y = 100.0                                      # up high: drops first
    send_hook(pet, cmd="raise", id="w9")
    assert pet.snapshot()["fetch_phase"] == "out"
    y0 = pet.y
    pet._tick()
    assert pet.y < y0 and pet.snapshot()["render"] == "jump"   # hops first
    assert _tick_until(pet, lambda s: s["fetch_phase"] == "sink", n=60)
    assert pet.snapshot()["render"] == "falling"       # dives into the floor
    pet._tick()
    assert pet.snapshot()["masked"] and not pet.snapshot()["hidden"]  # half sunk
    # the window must NOT come up before the pet is out of sight
    assert _tick_until(pet, lambda s: s["fetch_phase"] == "gone", n=50)  # ~1.5s at 20fps
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
    pet._can_pull = False
    pet._on_geom(_row("w9", "code", 0, 0, 800, 800, "code", "min"))
    send_hook(pet, cmd="raise", id="w9")
    assert _tick_until(pet, lambda s: s["fetch_phase"] == "gone")
    pet._on_geom(_row("w9", "code", 0, 0, 800, 800, "code"))
    pet._tick()
    assert pet.snapshot()["contained"] == "w9"          # top edge is off-screen


def _bottom(pet):
    return pet.screen_rect.bottom()


def test_kde_hauls_the_window_up_out_of_the_floor_with_the_pet_on_it(pet):
    pet._can_pull = True
    pet._on_geom(_row("w9", "slack", 200, 300, 500, 250, "Slack", "min"))
    send_hook(pet, cmd="raise", id="w9")
    assert _tick_until(pet, lambda s: s["fetch_phase"] == "pull", n=120)
    pet._tick()
    assert pet.snapshot()["hidden"]                     # parked below: nothing yet
    # KWin moves it up frame by frame; the pet hangs on to its top edge
    for y in (_bottom(pet) - 40, _bottom(pet) - 150):
        pet._on_geom(_row("w9", "slack", 200, y, 500, 250, "Slack"))
        pet._tick()
        snap = pet.snapshot()
        assert snap["fetch_phase"] == "pull" and snap["render"] == "strain"
        assert abs(pet.y + pet.foot_y - y) < 1 and 200 <= pet.x + pet.w / 2.0 <= 700
    assert not pet.snapshot()["hidden"]                 # coming up out of the floor
    pet._on_geom(_row("w9", "slack", 200, 300, 500, 250, "Slack"))   # home
    pet._tick()
    snap = pet.snapshot()
    assert snap["fetch_phase"] == "ride" and snap["render"] == "celebrate"
    assert abs(pet.y + pet.foot_y - 300) < 1 and not snap["masked"]


def test_kde_drops_into_a_maximized_window_once_it_is_up(pet):
    pet._can_pull = True
    pet._on_geom(_row("w9", "code", 0, 0, 800, 800, "code", "min"))
    send_hook(pet, cmd="raise", id="w9")
    assert _tick_until(pet, lambda s: s["fetch_phase"] == "pull", n=120)
    pet._on_geom(_row("w9", "code", 0, 0, 800, 800, "code"))
    pet._tick()
    snap = pet.snapshot()
    assert snap["fetch_phase"] == "ride" and snap["contained"] == "w9"
    assert snap["mode"] == "thrown"                     # falling in to land


def test_raise_ignores_ids_the_finder_does_not_list(pet):
    pet._on_geom(_row("w1", "konsole", 0, 0, 600, 400, "claude"))
    send_hook(pet, cmd="raise", id='x"; evil(); "')
    assert pet.snapshot()["fetching"] is None


def test_chat_opens_the_pets_own_chat_window(pet):
    send_hook(pet, cmd="chat")
    assert pet.snapshot()["chat_open"]


def test_grabbing_the_pet_mid_fetch_calls_the_fetch_off(pet):
    from PyQt6.QtCore import QPointF, Qt
    from PyQt6.QtGui import QMouseEvent
    pet._on_geom(_row("w9", "slack", 200, 400, 500, 300, "Slack", "min"))
    send_hook(pet, cmd="raise", id="w9")
    assert _tick_until(pet, lambda s: s["fetch_phase"] == "sink", n=60)
    pet._tick()
    assert pet.snapshot()["masked"]                    # half sunk
    pet.mousePressEvent(QMouseEvent(
        QMouseEvent.Type.MouseButtonPress, QPointF(5, 5), QPointF(5, 5),
        Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier))
    pet._tick()
    snap = pet.snapshot()
    assert snap["fetching"] is None and not snap["masked"]   # whole pet in hand


MAGENTA = (255, 0, 255)


def _paints(pet, rgb):
    img = pet.grab().toImage()
    return any(img.pixelColor(x, y).getRgb()[:3] == rgb
               for y in range(img.height()) for x in range(img.width()))


def test_fetch_carries_the_apps_icon_and_tosses_it_on_arrival(pet):
    pet._can_pull = False
    asked = []
    pet._app_sprite = lambda app: asked.append(app) or [[MAGENTA] * 8 for _ in range(8)]
    pet._on_geom(_row("w9", "slack", 200, 400, 500, 300, "Slack", "min"))
    send_hook(pet, cmd="raise", id="w9")
    assert asked == ["slack"] and pet.snapshot()["fetch_icon"]
    assert _paints(pet, MAGENTA)                       # in its mouth on the way out
    assert _tick_until(pet, lambda s: s["fetch_phase"] == "gone")
    pet._on_geom(_row("w9", "slack", 200, 400, 500, 300, "Slack"))
    for _ in range(12):                                # toss done (~0.6s)
        pet._tick()
    assert pet.snapshot()["fetch_phase"] == "ride" and _paints(pet, MAGENTA)
    pet._fetch["cheer"] = 0                            # cheering over
    assert not _paints(pet, MAGENTA)


def test_fetch_without_an_icon_is_the_plain_fetch(pet):
    pet._app_sprite = lambda app: None
    pet._on_geom(_row("w9", "slack", 200, 400, 500, 300, "Slack", "min"))
    send_hook(pet, cmd="raise", id="w9")
    assert pet.snapshot()["fetching"] == "w9" and not pet.snapshot()["fetch_icon"]


def test_sinking_slides_the_art_down_not_the_window_off_screen(pet):
    # the WM won't let a window leave the screen, so a pet that moved its
    # window down would just be erased in place: the art has to drop instead
    pet._can_pull = False
    pet._on_geom(_row("w9", "slack", 200, 400, 500, 300, "Slack", "min"))
    send_hook(pet, cmd="raise", id="w9")
    assert _tick_until(pet, lambda s: s["fetch_phase"] == "sink", n=60)
    bottom = pet.screen_rect.bottom()
    seen = []
    while pet.snapshot()["fetch_phase"] == "sink":
        pet._tick()
        assert pet.pos().y() + pet.h - 1 <= bottom           # window stays on screen
        img = pet.grab().toImage()
        rows = [y for y in range(img.height())
                if any(img.pixelColor(x, y).alpha() for x in range(img.width()))]
        if rows:
            seen.append(rows[0])
    assert len(seen) >= 2 and seen[-1] > seen[0]              # the art moved down


def test_a_perched_pet_dives_through_the_window_it_stands_on(pet):
    pet._can_pull = False
    pet._on_geom("|".join([_row("w1", "konsole", 100, 200, 600, 300, "claude"),
                           _row("w9", "slack", 200, 400, 500, 300, "Slack", "min")]))
    pet.x, pet.y = 300.0, 200.0 - pet.foot_y             # standing on w1's top
    send_hook(pet, cmd="raise", id="w9")
    assert _tick_until(pet, lambda s: s["hidden"], n=60)
    assert pet.y + pet.foot_y < 200 + pet.h + 60          # gone right there, not at the floor
