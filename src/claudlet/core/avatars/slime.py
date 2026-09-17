"""slime — a legless jelly blob that wobbles instead of walking.

Bundled as a worked example of a creature that is nothing like the built-in:
no legs, no rotation, its own idea of what "running unattended" looks like. If
you are writing one, read this next to `skill/creature-authoring.md`.

Everything about how a state LOOKS is in here; the pet only says which state
and which frame. Motion numbers come from `state_rig` and props from
`draw_prop`, so the slime inherits claudlet's whole motion vocabulary and only
re-draws the body: a dome of stacked slabs, widest at the floor, jiggling.

Two deliberate departures from the built-in:
  * it never ROTATES. The body is a stack of thin slabs, and rotating that
    turns every slab edge into a smeared stripe. A lean is applied as a SHEAR
    instead — each slab slides sideways with its height — which is also what
    jelly actually does when it leans.
  * it has no legs. A stride becomes a hop: squashed at the bottom of the
    cycle, stretched at the top.
"""
import math

from PyQt6.QtCore import QRect, Qt
from PyQt6.QtGui import QColor

from claudlet.core import creature as C

EYE = QColor("#20222A")
GLOSS = QColor(255, 255, 255, 215)
VISOR = QColor("#2A2E3A")
VISOR_HI = QColor("#5C6478")

GRID_W, GRID_H = 22, 17

TOP, FLOOR = 4.6, 13.4    # crown and floor rows of the body
HALF = 7.2                # half-width at the floor
ROW = 0.55                # one drawn slab

STATES = ("idle", "walk", "work_computer", "work_search", "work_web",
          "work_agent", "work_skill", "autopilot",
          "thinking", "attention", "asking", "error", "angry",
          "celebrate", "sleeping", "held", "falling", "jump", "wave", "sing",
          "juggle", "float", "climbdown", "strain", "leap",
          "observe", "tic", "settle", "doze")


def _profile(row):
    """Half-width of the body at an art row: round crown, flared skirt."""
    k = max(0.0, min(1.0, (FLOOR - row) / (FLOOR - TOP)))
    return HALF * (1.0 - k ** 3) ** (1 / 2.4)


class Slime:
    name = "slime"
    grid = (GRID_W, GRID_H)
    states = STATES
    hats = C.HAT_KINDS      # companions wear one; drawn by C.draw_hat
    palette = "#3FBF6F"        # its own default green, until the user picks
    # the dome ends at FLOOR, well above the built-in's 15.8 — say so or the pet
    # stands it sunk into whatever window it perches on
    foot_row = FLOOR

    def set_lang(self, lang):
        C.set_lang(lang)

    def draw(self, p, ox, oy, u, state, frame, facing=1, autonomous=False,
             cap=None, energy=1.0, palette=None, happy=False, hovering=False,
             gaze=(0.0, 0.0), **kw):
        p.setPen(Qt.PenStyle.NoPen)
        body, hi, lo, _bang = C.palette_colors(palette)

        rig = C.state_rig(state, frame, energy, happy, autonomous, gaze)
        sx, sy = rig["sx"], rig["sy"]
        eyes = "happy" if happy else rig["eyes"]
        body_dy = C._snap_offset(rig["bob"] + rig["baseline_lift"], u)

        if rig["walking"]:
            hop = math.sin(rig["legphase"] * 2 * math.pi)
            sx *= 1.0 + 0.10 * hop
            sy *= 1.0 - 0.10 * hop
        wob = 0.5 if rig["walking"] else 0.2       # jelly ripple amplitude
        shear = math.tan(math.radians(rig["tilt"])) * 1.15

        def lean(row):
            return shear * (FLOOR - row)

        # Snap BOUNDARIES, not origin-and-size: neighbouring slabs must share an
        # edge exactly, or a hairline seam rules across the body at every row.
        def xof(col):
            return ox + (10.5 + (col - 10.5) * sx) * u

        def yof(row):
            return oy + (10.5 + (row - 10.5) * sy + body_dy) * u

        def box(c0, r0, c1, r1, color):
            x0, x1 = C._r(xof(c0)), C._r(xof(c1))
            y0, y1 = C._r(yof(r0)), C._r(yof(r1))
            p.fillRect(QRect(x0, y0, max(1, x1 - x0), max(1, y1 - y0)), color)

        def px(col, row, w, h, color):
            d = lean(row + h / 2.0)
            box(col + d, row, col + d + w, row + h, color)

        p.save()
        if facing < 0:                      # body only — props stay upright
            p.translate(2 * (ox + GRID_W / 2.0 * u), 0)
            p.scale(-1, 1)

        # ---- arms: nubs pressed against the body wall at their own height ----
        arm, sw = rig["arm"], rig["arm_swing"]

        def nub(row, side, h=1.7, w=2.1):
            edge = _profile(row + h / 2.0) - 0.9
            col = 10.5 + side * edge if side > 0 else 10.5 - edge - w
            px(col, row, w, h, lo)

        if arm == "up":
            nub(6.4, -1); nub(6.4, +1)
        elif arm == "wave":
            nub(10.6, -1)
            nub(6.2 + C._sin(frame, 16, 1.4), +1)
        elif arm == "tap":
            nub(11.0 + rig["front_tap"], -1)
            nub(11.0 + (0.8 - rig["front_tap"]), +1)
        elif arm != "none":
            nub(10.6 + sw, -1); nub(10.6 - sw, +1)

        # ---- body ----
        n = int(round((FLOOR - TOP) / ROW))
        for i in range(n):
            y0, y1 = FLOOR - (i + 1) * ROW, FLOOR - i * ROW
            half = _profile((y0 + y1) / 2.0)
            # ripple travels UP the body, so the crown lags the floor
            half += C._sin(frame, 26, wob, phase=(FLOOR - y0) * 0.09)
            d = lean((y0 + y1) / 2.0)
            shade = lo if i == 0 else body
            box(10.5 - half + d, y0, 10.5 + half + d, y1, shade)

        cy = FLOOR - n * ROW                       # crown highlight
        chw = _profile(cy + ROW) * 0.55
        cd = lean(cy + ROW)
        box(10.5 - chw + cd, cy, 10.5 + chw + cd, cy + ROW * 1.7, hi)

        if cap:                      # dome crown, and it is widest at the floor
            C.draw_hat(px, cap, frame, crown_row=TOP + 0.2, cx=10.5,
                       head_w=_profile(TOP + 1.5) * 2.0)

        gr = 6.6                                   # gloss, inside the dome
        gx = 10.5 - _profile(gr) + 1.3
        px(gx, gr, 1.8, 0.9, GLOSS)
        px(gx, gr + 0.9, 0.9, 0.7, GLOSS)

        # ---- face ----
        er = 8.8
        inset = _profile(er) - 1.5          # keep both eyes inside the wall
        e1, e2 = 10.5 - inset, 10.5 + inset - 1.5

        def eye(col, kind):
            gazeable = kind in ("open", "focus", "up", "wide")
            c = col + (gaze[0] * facing * 0.65 if gazeable else 0.0)
            r = er + (gaze[1] * 0.45 if gazeable else 0.0)
            if kind == "open":
                px(c, r, 1.5, 1.9, EYE)
            elif kind == "blink":
                px(c, r + 1.1, 1.5, 0.6, EYE)
            elif kind == "sleep":
                px(c - 0.6, r + 1.1, 2.7, 0.6, EYE)
            elif kind == "focus":
                px(c, r + 0.6, 1.7, 0.9, EYE)
            elif kind == "squint":            # "> <" pointing at the nose
                left = c < 10.0
                m = c + (0.5 if left else -0.5)
                vtx = m + 0.9 if left else m
                out = m if left else m + 0.9
                px(out, r + 0.3, 1.1, 0.6, EYE)
                px(vtx, r + 0.85, 1.1, 0.6, EYE)
                px(out, r + 1.4, 1.1, 0.6, EYE)
            elif kind == "up":
                px(c, r - 0.4, 1.5, 1.6, EYE)
            elif kind == "wide":
                px(c - 0.3, r - 0.5, 2.1, 2.6, EYE)
            elif kind == "x":
                px(c, r + 0.6, 1.8, 0.5, EYE)
                px(c + 0.65, r, 0.5, 1.8, EYE)
            elif kind == "happy":
                px(c, r + 0.9, 0.6, 0.6, EYE)
                px(c + 0.55, r + 0.35, 0.6, 0.6, EYE)
                px(c + 1.1, r + 0.9, 0.6, 0.6, EYE)

        def band(row):
            w = _profile(row + 1.2) - 0.4
            px(10.5 - w, row, w * 2, 2.4, VISOR)
            px(10.5 - w, row, w * 2, 0.5, VISOR_HI)

        # This creature's answer to "running unattended": a band across the
        # dome, pulled down over the eyes while it is actually working and
        # resting up on the crown otherwise. Another creature may glow, recolour
        # itself, or ignore the flag entirely — that is the point of the flag.
        working = state.startswith("work_") or state == "autopilot"
        if autonomous and working:
            band(er - 0.4)
            if state == "work_skill" and frame % 24 < 12:
                px(12.0, er + 0.9, 1.1, 0.8, QColor("#FF3B3B"))
        else:
            eye(e1, eyes)
            eye(e2, eyes)
            if autonomous:
                band(er - 4.2)

        p.restore()
        C.draw_prop(p, ox, oy, u, rig["prop"], frame, state, body_dy, facing,
                    palette)


AVATAR = Slime
