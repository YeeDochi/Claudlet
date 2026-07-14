from claudlet.core.idle_engine import IdleEnergy, HIGH, MID, LOW


def test_starts_full_and_high():
    e = IdleEnergy()
    assert e.value == 1.0
    assert e.level() == HIGH


def test_events_drain_energy():
    e = IdleEnergy()
    for i in range(200):
        e.note_event(now=float(i))
    assert e.value < 1.0


def test_roam_drains_energy():
    e = IdleEnergy()
    start = e.value
    for i in range(500):
        e.note_roam(now=float(i))
    assert e.value < start


def test_passive_time_drains_slowly_when_not_resting():
    e = IdleEnergy()
    e.update(now=0.0, resting=False)     # first call records the clock baseline
    e.update(now=300.0, resting=False)   # 5 min elapsed -> drains
    assert e.value < 1.0


def test_resting_recovers_energy():
    e = IdleEnergy(energy=0.3)
    low = e.value
    for i in range(1, 4000):
        e.update(now=float(i), resting=True)
    assert e.value > low


def test_energy_clamped_to_unit_interval():
    e = IdleEnergy(energy=0.02)
    for i in range(10000):
        e.note_event(now=float(i))
        e.note_roam(now=float(i))
    assert e.value >= 0.0
    e2 = IdleEnergy(energy=0.99)
    for i in range(1, 100000):
        e2.update(now=float(i), resting=True)
    assert e2.value <= 1.0


def test_levels_partition_by_threshold():
    assert IdleEnergy(energy=0.9).level() == HIGH
    assert IdleEnergy(energy=0.5).level() == MID
    assert IdleEnergy(energy=0.1).level() == LOW


def test_wake_rebounds_energy():
    e = IdleEnergy(energy=0.2)
    e.wake(now=100.0)
    assert e.value > 0.2


import random
from claudlet.core.idle_engine import (
    pick_behavior, WALK, EXPLORE, HOP, OBSERVE, TIC, SETTLE, DOZE, RESTING,
)


def _dist(level, on_window, n=4000, seed=1):
    rng = random.Random(seed)
    out = {}
    for _ in range(n):
        b = pick_behavior(level, rng, on_window=on_window)
        out[b] = out.get(b, 0) + 1
    return out


def test_pick_behavior_is_deterministic_for_a_seed():
    a = pick_behavior(HIGH, random.Random(42), on_window=False)
    b = pick_behavior(HIGH, random.Random(42), on_window=False)
    assert a == b


def test_high_energy_favors_exploration():
    d = _dist(HIGH, on_window=False)
    explore = d.get(EXPLORE, 0) + d.get(HOP, 0)
    rest = d.get(SETTLE, 0) + d.get(DOZE, 0)
    assert explore > rest


def test_low_energy_collapses_to_rest():
    d = _dist(LOW, on_window=False)
    rest = d.get(SETTLE, 0) + d.get(DOZE, 0)
    assert rest > d.get(EXPLORE, 0) + d.get(HOP, 0)
    assert DOZE in d


def test_low_energy_never_explores_or_hops():
    d = _dist(LOW, on_window=False)
    assert EXPLORE not in d and HOP not in d


def test_hop_only_offered_when_on_a_window():
    assert HOP not in _dist(HIGH, on_window=False)
    assert HOP in _dist(HIGH, on_window=True)


def test_all_choices_are_known_behaviors():
    known = {WALK, EXPLORE, HOP, OBSERVE, TIC, SETTLE, DOZE}
    for level in (HIGH, MID, LOW):
        assert set(_dist(level, on_window=True)).issubset(known)


def test_resting_set_contents():
    assert RESTING == frozenset({OBSERVE, TIC, SETTLE, DOZE})


from claudlet.core.idle_engine import pick_explore_point


class _W:
    def __init__(self, wid, x, y, w, h):
        self.wid, self.x, self.y, self.w, self.h = wid, x, y, w, h


def test_explore_point_none_when_no_windows():
    assert pick_explore_point([], random.Random(0), current_wid=None) is None


def test_explore_point_none_when_only_current_window():
    wins = [_W("A", 0, 100, 200, 150)]
    assert pick_explore_point(wins, random.Random(0), current_wid="A") is None


def test_explore_point_is_on_a_window_top_center():
    wins = [_W("A", 0, 100, 200, 150), _W("B", 400, 300, 100, 80)]
    pt = pick_explore_point(wins, random.Random(0), current_wid="A")
    assert pt is not None
    x, y = pt
    # must be window B's top surface, centered
    assert x == 400 + 100 / 2
    assert y == 300


def test_explore_point_skips_current_window():
    wins = [_W("A", 0, 100, 200, 150), _W("B", 400, 300, 100, 80)]
    for seed in range(20):
        x, y = pick_explore_point(wins, random.Random(seed), current_wid="A")
        assert (x, y) != (0 + 200 / 2, 100)   # never picks A
