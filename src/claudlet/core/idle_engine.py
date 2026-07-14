"""Idle liveliness: an activity-based energy level and the pure behavior
selection that rides on it. No Qt/DBus imports — unit-tested by data, like
core/state_engine.py. Time (`now`, monotonic seconds) and randomness (`rng`)
are always injected so the logic is deterministic under test."""

HIGH, MID, LOW = "high", "mid", "low"

# level thresholds on energy in [0,1] (tune on hardware)
_HIGH_AT = 0.66
_LOW_AT = 0.33

# drain/recovery coefficients (energy units). Tuned so a long, busy session
# visibly tires the creature over tens of minutes, and a quiet rest revives it.
_EVENT_DRAIN = 0.004      # per hook event (session "filling up")
_ROAM_DRAIN = 0.0006      # per roam step/jump (moving around tires it)
_PASSIVE_DRAIN = 0.02     # per minute of wall time while not resting
_RECOVER = 0.05           # per minute of resting
_WAKE_REBOUND = 0.15      # startle bump when activity resumes


def _clamp(v):
    return 0.0 if v < 0.0 else 1.0 if v > 1.0 else v


class IdleEnergy:
    def __init__(self, energy=1.0):
        self.value = _clamp(energy)
        self._last = None      # last `now` seen by update() (for dt)

    def note_event(self, now):
        self.value = _clamp(self.value - _EVENT_DRAIN)

    def note_roam(self, now):
        self.value = _clamp(self.value - _ROAM_DRAIN)

    def update(self, now, resting):
        if self._last is None:
            self._last = now
            return
        dt_min = max(0.0, (now - self._last) / 60.0)
        self._last = now
        if resting:
            self.value = _clamp(self.value + _RECOVER * dt_min)
        else:
            self.value = _clamp(self.value - _PASSIVE_DRAIN * dt_min)

    def wake(self, now):
        self.value = _clamp(self.value + _WAKE_REBOUND)
        self._last = now

    def level(self):
        if self.value >= _HIGH_AT:
            return HIGH
        if self.value <= _LOW_AT:
            return LOW
        return MID


WALK = "walk"
EXPLORE = "explore_window"
HOP = "hop_between"
OBSERVE = "observe"
TIC = "tic"
SETTLE = "settle"
DOZE = "doze"

RESTING = frozenset({OBSERVE, TIC, SETTLE, DOZE})

# weight tables per energy level: behavior -> relative weight.
# EXPLORE/HOP are exploration; OBSERVE/TIC are light rest; SETTLE/DOZE are
# heavy rest (the slide toward sleep). HOP is only reachable when on a window.
_WEIGHTS = {
    HIGH: {WALK: 3, EXPLORE: 5, HOP: 4, OBSERVE: 2, TIC: 2, SETTLE: 0, DOZE: 0},
    MID:  {WALK: 3, EXPLORE: 2, HOP: 2, OBSERVE: 3, TIC: 3, SETTLE: 1, DOZE: 0},
    LOW:  {WALK: 1, EXPLORE: 0, HOP: 0, OBSERVE: 2, TIC: 1, SETTLE: 4, DOZE: 4},
}


def pick_behavior(level, rng, on_window):
    """Weighted choice of the next idle behavior for this energy level.
    `rng` is a random.Random (injected for determinism); `on_window` gates
    HOP (only meaningful when standing on a window)."""
    weights = dict(_WEIGHTS.get(level, _WEIGHTS[MID]))
    if not on_window:
        weights[HOP] = 0
    items = [(b, w) for b, w in weights.items() if w > 0]
    total = sum(w for _, w in items)
    r = rng.uniform(0, total)
    upto = 0.0
    for b, w in items:
        upto += w
        if r <= upto:
            return b
    return items[-1][0]


def pick_explore_point(wins, rng, current_wid=None):
    """Choose a window to go visit and return the point on its top surface
    (horizontal center, top edge) to aim at — feed this to
    follow_nav.plan_move as the (cursor_x, cursor_y) target. Skips the window
    currently under the feet. Returns None if nothing eligible."""
    candidates = [w for w in wins if getattr(w, "wid", None) != current_wid]
    if not candidates:
        return None
    w = rng.choice(candidates)
    return (w.x + w.w / 2.0, float(w.y))
