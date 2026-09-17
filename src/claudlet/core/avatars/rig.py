"""An avatar built from pixels somebody drew, instead of from our art code.

The built-in creature is rectangles in `creature.py`; its shape is decided by
the code that paints it. A custom creature can't be — it has to come from
pixels and a description of what those pixels ARE. This is that description.

    grid      art-pixel box the creature lives in; the pet's window follows it
    foot_row  where it touches the ground. Required even with no legs: the
              pet's physics stands it on windows by this line
    parts     a tree. Each part has pixels, a parent, where it attaches, and a
              ROLE that says how it moves

Roles, not per-part animation. A part says "I am a leg" and the leg motion in
`creature.state_rig` drives it, so a creature with six legs or none still gets
all 28 states without anyone authoring 28 animations for it. Turning a part off
is allowed and the roles degrade: no legs means the walk bounces instead of
striding, no arms means the body does the waving.

Transforms are TRANSLATION and vertical squash only, never rotation. At this
size a limb is two to four pixels; rotating pixel art shreds its edges and buys
no expression the offsets don't already give.
"""
import math

from claudlet.core import creature as C

# A pixel row is one character per art pixel; the character picks a palette
# slot. Readable in a diff, easy for a dot editor to export, easy for an agent
# to emit and edit by hand.
INK = {"b": "body", "h": "hi", "l": "lo", "e": "eye", "a": "bang"}
BLANK = "."

ROLES = ("body", "head", "leg", "arm", "eye", "decor")


class Part(object):
    """One piece of a creature: pixels, where it hangs, and what it is.

    `variants` is for parts whose SHAPE changes with the state rather than just
    its position — eyes above all, which the built-in creature draws ten ways
    (open, blink, sleep, focus, squint, x, happy, up, wide, shades). One bitmap
    per part was the first guess and it was wrong: a sleeping creature with its
    eyes wide open doesn't read as asleep. Keyed by the rig value for the role
    (`eyes` for an eye), falling back to `pixels` for anything not drawn."""

    __slots__ = ("id", "role", "parent", "at", "pixels", "enabled", "index",
                 "variants")

    def __init__(self, id, role, at, pixels, parent=None, enabled=True, index=0,
                 variants=None):
        self.variants = dict(variants or {})
        self.id = id
        self.role = role if role in ROLES else "decor"
        self.parent = parent
        self.at = tuple(at)           # (col, row) in art pixels, on the parent
        self.pixels = list(pixels)
        self.enabled = enabled
        self.index = index            # which leg/arm/eye this is (0-based)

    def shape(self, rig_values):
        """The pixels to draw this frame."""
        if self.role == "eye":
            return self.variants.get(rig_values.get("eyes"), self.pixels)
        return self.pixels

    def size(self):
        return (max((len(r) for r in self.pixels), default=0), len(self.pixels))


class Rig(object):
    def __init__(self, name, grid, foot_row, parts):
        self.name = name
        self.grid = tuple(grid)
        self.foot_row = foot_row
        self.parts = list(parts)
        self._by_id = {p.id: p for p in self.parts}

    def live(self):
        return [p for p in self.parts if p.enabled]

    def has(self, role):
        return any(p.role == role for p in self.live())

    def origin(self, part):
        """Absolute (col, row) of a part, walking up its parents. Pure."""
        col, row = part.at
        seen = set()
        cur = part.parent
        while cur and cur not in seen:
            seen.add(cur)                       # a cycle must not hang the pet
            up = self._by_id.get(cur)
            if up is None:
                break
            col += up.at[0]
            row += up.at[1]
            cur = up.parent
        return col, row


def part_offset(part, rig, r):
    """Where a part sits this frame, relative to its resting place.

    Every part rides the body's shared bob; a leg adds its own step, an arm its
    swing or pose, an eye the gaze. This is the whole of the animation: the
    numbers come from `creature.state_rig`, which is the same table the built-in
    art moves to."""
    dx = dy = 0.0
    role = part.role
    if role == "leg":
        # the cycle only means "mid-stride" while walking. Other states reuse
        # legphase for something else entirely -- jump/celebrate/doze set 0.5 to
        # mean "legs tucked together" -- and reading it as a stride there lifts
        # every other leg to its full height for no reason.
        if r["walking"]:
            ph = (r["legphase"] + (0.5 if part.index % 2 else 0.0)) % 1.0
            dy -= max(0.0, math.sin(ph * math.pi)) * 1.3
        dy -= r["front_tap"] if part.index >= 2 else 0.0
    elif role == "arm":
        pose = r["arm"]
        side = -1.0 if part.index % 2 == 0 else 1.0
        if pose == "up":
            dy -= 3.3
        elif pose == "wave" and part.index % 2:
            dy -= 4.5 + C._sin(r.get("frame", 0), 16, 1.4)
        elif pose == "tap":
            dy += 2.1 - (r["front_tap"] if part.index % 2 else 0.0)
        else:
            dy += r["arm_swing"] * side
    elif role == "eye":
        dx += r.get("gaze", (0.0, 0.0))[0] * 0.65
        dy += r.get("gaze", (0.0, 0.0))[1] * 0.45
    return dx, dy


def _edge(origin, centre, start, i, scale, u):
    """Device pixel of art-pixel boundary `i` of a part starting at `start`.

    Squash is about the creature's centre, like the built-in art."""
    a = start + i
    return int(math.floor(origin + (centre + (a - centre) * scale) * u + 0.5))


def legless_bounce(rig, r):
    """A creature with no legs still has to look like it is going somewhere.

    The stride is what reads as walking; without legs the body has to carry it,
    so the leg cycle becomes a hop of the whole creature."""
    if rig.has("leg") or not r["walking"]:
        return 0.0
    return -abs(math.sin(r["legphase"] * math.pi)) * 1.1


class RigAvatar(object):
    """An Avatar (see the package docstring) drawn from a Rig."""

    hats = ()

    def __init__(self, rig, states=None):
        self.rig = rig
        self.name = rig.name
        self.grid = rig.grid
        self.states = tuple(states or C.STATES)

    def set_lang(self, lang):
        pass                     # no text of its own yet

    def draw(self, p, ox, oy, u, state, frame, **kw):
        from PyQt6.QtCore import QRect
        from PyQt6.QtCore import Qt
        p.setPen(Qt.PenStyle.NoPen)
        body, hi, lo, bang = C.palette_colors(kw.get("palette"))
        eye = C.EYE if hasattr(C, "EYE") else lo
        ink = {"body": body, "hi": hi, "lo": lo, "bang": bang, "eye": eye}

        r = C.state_rig(state, frame, kw.get("energy", 1.0),
                        kw.get("happy", False), kw.get("visor"),
                        kw.get("gaze", (0.0, 0.0)))
        r["frame"] = frame
        r["gaze"] = kw.get("gaze", (0.0, 0.0))
        shared = r["bob"] + r["baseline_lift"] + legless_bounce(self.rig, r)
        sx, sy = r["sx"], r["sy"]
        bcx, bcy = self.grid[0] / 2.0, self.grid[1] / 2.0

        for part in self.rig.live():
            pcol, prow = self.rig.origin(part)
            dx, dy = part_offset(part, self.rig, r)
            shape = part.shape(r)
            w = max((len(line) for line in shape), default=0)
            # Snap the cell BOUNDARIES, not each cell's origin and size apart.
            # Rounding a cell's position and its width independently lets
            # neighbours miss each other once squash makes the cells
            # non-integral, and the creature comes out with seams ruled through
            # it. Sharing one edge between adjacent cells means they always
            # tile: cell c spans xs[c]..xs[c+1].
            xs = [_edge(ox, bcx, pcol + dx, i, sx, u) for i in range(w + 1)]
            ys = [_edge(oy, bcy, prow + dy + shared, j, sy, u)
                  for j in range(len(shape) + 1)]
            for row, line in enumerate(shape):
                for col, ch in enumerate(line):
                    if ch == BLANK:
                        continue
                    p.fillRect(QRect(xs[col], ys[row],
                                     max(1, xs[col + 1] - xs[col]),
                                     max(1, ys[row + 1] - ys[row])),
                               ink.get(INK.get(ch, "body"), body))
