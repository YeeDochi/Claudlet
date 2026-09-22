"""codex — the cloud-headed terminal mascot.

A puffy periwinkle cloud of a head with a terminal screen set into it, a round
torso wearing a small `>_`, stubby arms and two short legs. The face is the
prompt: a chevron and a cursor. There is no mouth — every expression is those
two glyphs, which is why they get their own table below.

Nothing rotates. The head is a union of lobes and rotating that shreds every
lobe edge, so a lean is applied as a SHEAR — each row slides with its height,
and the cloud leans over its own feet.

Motion numbers come from `state_rig` and props from `draw_prop`, so it inherits
claudlet's whole motion vocabulary and only redraws the body.
"""
import math

from PyQt6.QtCore import QRect, Qt
from PyQt6.QtGui import QColor

from claudlet.core import creature as C

GRID_W, GRID_H = 22, 17
CX = 10.5

HEAD_T, HEAD_B = 2.2, 10.0         # cloud crown / chin rows
HEAD_W = 10.2
SCR_L, SCR_R = 7.9, 13.1           # terminal screen set into the cloud
SCR_T, SCR_B = 5.5, 8.8
TORSO_T, TORSO_B = 9.3, 13.4
TORSO_HW = 2.9
FLOOR = 15.8                       # where the legs end == foot_row

SCREEN = QColor("#23255C")         # the dark terminal pane
GLOW = QColor("#D9E8FF")           # prompt glyphs
GLOW_DIM = QColor(217, 232, 255, 95)
AUTO_GLOW = QColor("#FFC24A")      # the prompt, running unattended
SCAN = QColor(255, 255, 255, 24)

# Limbs are the SAME colour as the body — they are only in shadow. Painting
# them with the palette's dark tone makes them a different-coloured leg, which
# is what they looked like. These go ON TOP of a body-coloured shape instead.
SHADE_NECK = QColor(0, 0, 0, 62)   # the head's shadow on the torso
SHADE_NECK2 = QColor(0, 0, 0, 28)  # ... fading out a row further down
SHADE_LEG = QColor(0, 0, 0, 62)
SHADE_ARM = QColor(0, 0, 0, 28)
SHADE_PUFF = QColor(0, 0, 0, 32)   # one puff of the cloud behind another
# The counterpart to the shadows: light on the body colour, not the palette's
# separate bright tone — that reads as a second colour painted on, not as a lit
# surface of the same one.
LIT_PUFF = QColor(255, 255, 255, 38)
LIT_EAR = QColor(255, 255, 255, 26)
LIT_SOFT = QColor(255, 255, 255, 20)   # the second step off a highlight
SHADE_VOL = QColor(0, 0, 0, 36)        # the underside of a round thing
SHADE_SEAM = QColor(0, 0, 0, 46)       # the dip where the two peaks meet
CHEST = QColor(255, 255, 255, 120)

# The cloud: lobes around a filled core. Each is (centre col, centre row,
# radius) in art pixels; a "circle" this small is a box with its corners bitten.
# The crown is FLAT in silhouette and the two peaks are drawn with light and
# shadow instead. A notch cut into the outline is a staircase at this size —
# three device pixels of it read as a dent, not as two puffs.
CREST = (6.5, 2.6, 14.5, 6.2)      # c0, r0, c1, r1 — runs down far enough
                                   # to MEET the side puffs; stop it short and
                                   # the shoulders are left cut away
PEAKS = (8.8, 12.6)                # where the two puffs catch the light —
                                   # the right one sits wider, so the gap
                                   # between them reads as the seam
CHIN = (6.2, 7.8, 14.8, 10.9)      # the underside, one panel — three separate
                                   # puffs down here turn the jaw into a saw
SIDE_LOBES = ((6.4, 7.0, 2.3), (14.6, 7.0, 2.3))

STATES = ("idle", "walk", "work_computer", "work_search", "work_web",
          "work_agent", "work_skill", "autopilot",
          "thinking", "attention", "asking", "error", "angry",
          "celebrate", "sleeping", "held", "falling", "jump", "wave", "sing",
          "juggle", "float", "climbdown", "strain", "leap",
          "observe", "tic", "settle", "doze")


class Codex:
    name = "codex"
    grid = (GRID_W, GRID_H)
    states = STATES
    hats = C.HAT_KINDS
    palette = "#7C86E8"            # periwinkle, until the user picks
    foot_row = FLOOR

    def set_lang(self, lang):
        C.set_lang(lang)

    def draw(self, p, ox, oy, u, state, frame, facing=1, autonomous=False,
             cap=None, energy=1.0, palette=None, happy=False, hovering=False,
             gaze=(0.0, 0.0), **kw):
        p.setPen(Qt.PenStyle.NoPen)
        body, hi, lo, bang = C.palette_colors(palette)

        rig = C.state_rig(state, frame, energy, happy, autonomous, gaze)
        sx, sy = rig["sx"], rig["sy"]
        eyes = "happy" if happy else rig["eyes"]
        body_dy = C._snap_offset(rig["bob"] + rig["baseline_lift"], u)
        shear = math.tan(math.radians(rig["tilt"])) * 1.1

        def xof(col):
            return ox + (CX + (col - CX) * sx) * u

        def yof(row):
            return oy + (10.5 + (row - 10.5) * sy + body_dy) * u

        # Snap BOUNDARIES, not origin-and-size: neighbouring cells must share an
        # edge exactly or hairline seams rule across the body.
        def box(c0, r0, c1, r1, color):
            x0, x1 = C._r(xof(c0)), C._r(xof(c1))
            y0, y1 = C._r(yof(r0)), C._r(yof(r1))
            p.fillRect(QRect(x0, y0, max(1, x1 - x0), max(1, y1 - y0)), color)

        def px(col, row, w, h, color):
            d = shear * (FLOOR - (row + h / 2.0))
            box(col + d, row, col + d + w, row + h, color)

        def bite(c0, r0, c1, r1, color, inset=0.9):
            """A box with its four corner pixels bitten off — reads as round."""
            px(c0, r0 + inset, c1 - c0, (r1 - r0) - 2 * inset, color)
            px(c0 + inset, r0, (c1 - c0) - 2 * inset, inset, color)
            px(c0 + inset, r1 - inset, (c1 - c0) - 2 * inset, inset, color)

        def lobe(cx_, cy_, r, color):
            bite(cx_ - r, cy_ - r, cx_ + r, cy_ + r, color, inset=r * 0.42)

        p.save()
        if facing < 0:                  # body only — props and text stay upright
            p.translate(2 * (ox + GRID_W / 2.0 * u), 0)
            p.scale(-1, 1)

        # ---- legs: two stubby pegs. legphase is a stride only while walking --
        if rig["walking"]:
            ph = rig["legphase"] * 2 * math.pi
            swing = [math.sin(ph) * 1.0, math.sin(ph + math.pi) * 1.0]
            lift = [max(0.0, math.sin(ph)) * 0.8,
                    max(0.0, math.sin(ph + math.pi)) * 0.8]
        elif rig["legphase"]:           # jump / doze: tucked, not striding
            swing, lift = [0.7, -0.7], [0.9, 0.9]
        else:
            swing, lift = [0.0, 0.0], [0.0, 0.0]
        for i, base in enumerate((CX - 2.3, CX + 0.4)):
            c0, r0 = base + swing[i], TORSO_B - 0.4
            c1, r1 = c0 + 1.9, FLOOR - lift[i]
            # square at the top, rounded only at the foot: biting both ends
            # turns a leg into a ball on a stick
            for color in (body, SHADE_LEG):
                px(c0, r0, c1 - c0, (r1 - r0) - 0.6, color)
                px(c0 + 0.6, r1 - 0.6, (c1 - c0) - 1.2, 0.6, color)

        # ---- arms: stubby nubs on the torso wall ----
        arm, sw = rig["arm"], rig["arm_swing"]

        # Arms are the BODY colour, not the legs' shade: an arm the same colour
        # as a leg, at the same height, just reads as more leg. They sit at
        # shoulder height and stick a clear pixel clear of the torso wall, so
        # the silhouette is what shows them.
        def nub(row, side, h=2.4, w=2.1):
            col = CX + TORSO_HW - 0.5 if side > 0 else CX - TORSO_HW - w + 0.5
            # a capsule: round at the shoulder AND at the hand, square across
            # the middle. Biting all four CORNERS off something two art pixels
            # across leaves a plus sign; capping the two ENDS leaves an arm.
            ins = 0.55
            for color in (body, SHADE_ARM):
                px(col + ins, row, w - 2 * ins, h, color)
                px(col, row + ins, ins, h - 2 * ins, color)
                px(col + w - ins, row + ins, ins, h - 2 * ins, color)
            px(col + 0.35, row + 0.15, w - 0.7, 0.5, LIT_SOFT)

        if arm == "up":
            nub(10.1, -1); nub(10.1, +1)
        elif arm == "wave":
            nub(11.1, -1)
            nub(9.5 + C._sin(frame, 16, 1.3), +1)
        elif arm == "tap":
            nub(11.1 + rig["front_tap"], -1)
            nub(11.1 + (0.8 - rig["front_tap"]), +1)
        elif arm != "none":
            nub(10.9 + sw, -1); nub(10.9 - sw, +1)

        # ---- torso, and the `>_` on its chest ----
        bite(CX - TORSO_HW, TORSO_T, CX + TORSO_HW, TORSO_B, body, inset=0.85)
        bite(CX - TORSO_HW, TORSO_T, CX + TORSO_HW, TORSO_B, SHADE_VOL, inset=0.85)
        bite(CX - TORSO_HW + 0.15, TORSO_T - 0.6, CX + TORSO_HW - 0.15,
             TORSO_B - 0.95, body, inset=0.85)                 # belly underside
        px(CX - 1.5, TORSO_T + 0.15, 3.0, 0.55, LIT_SOFT)
        cr = 11.8 + C._sin(frame, 44, 0.2)
        px(CX - 1.8, cr - 0.62, 0.62, 0.62, CHEST)   # chest `>`
        px(CX - 1.18, cr, 0.62, 0.62, CHEST)
        px(CX - 1.8, cr + 0.62, 0.62, 0.62, CHEST)
        px(CX - 0.1, cr + 0.62, 1.7, 0.62, CHEST)    # chest `_`

        # ---- the cloud head ----
        for cx_, cy_, r in SIDE_LOBES:
            lobe(cx_, cy_, r, body)
        bite(*CHIN, body, inset=0.9)
        bite(*CREST, body, inset=0.8)
        bite(7.2, 4.0, 13.8, 9.2, body, inset=0.7)           # core fill
        # flat body with light skimming the crown only — shading each lobe
        # separately reads as three clouds, not one head, and a shade along the
        # BOTTOM lobes lands outside their round underside and becomes a bar
        # slung across the neck rather than a shadow under the chin
        # A cloud is puffs, not a ball. What separates them is the CRESCENT one
        # puff casts on the one behind it — shading a whole lobe instead just
        # darkens the middle of the head and buys nothing. So: drop a copy of
        # each front puff, ink it, then re-cover with the puff itself; only the
        # sliver that pokes out below survives.
        for cx_, cy_, r in SIDE_LOBES:
            lobe(cx_, cy_ + 0.95, r, SHADE_PUFF)
        for cx_, cy_, r in SIDE_LOBES:
            lobe(cx_, cy_, r, body)
        # Volume: ink the whole puff, then cover it with a copy of ITSELF lifted
        # a little. What survives is a crescent hugging the puff's own curve —
        # a rectangle of shade painted over a round thing just looks like a
        # stain, which is what the first attempt at this looked like.
        for cx_, cy_, r in SIDE_LOBES:
            lobe(cx_, cy_, r, SHADE_VOL)
            lobe(cx_, cy_ - 0.9, r * 0.92, body)
            px(cx_ - r * 0.36, cy_ - r * 0.92, r * 0.72, 0.6, LIT_SOFT)
        bite(*CHIN, SHADE_VOL, inset=0.9)
        bite(CHIN[0] + 0.15, CHIN[1] - 0.8, CHIN[2] - 0.15, CHIN[3] - 0.85,
             body, inset=0.9)

        # The two peaks: each rises half a pixel proud of the crest, so the
        # outline dips between them, and the seam is inked below. One shallow
        # step plus the shadow separates them; a deeper notch just looks dented.
        for cx_ in PEAKS:
            # the right peak's top is a touch shorter on its outer side, so the
            # two crowns are not a stamped pair
            px(cx_ - 1.1, CREST[1] - 0.45,
               2.2 - (0.35 if cx_ > CX else 0.0), 0.45, body)
        px(CX - 0.45, CREST[1], 0.9, 1.9, SHADE_SEAM)      # the seam between
        for cx_ in PEAKS:                                  # ... and the peaks
            px(cx_ - 0.9, CREST[1] - 0.45, 1.8, 0.45, LIT_PUFF)
            px(cx_ - 0.9, CREST[1] + 0.05, 1.8, 0.75, LIT_PUFF)
            px(cx_ - 0.9, CREST[1] + 0.8, 1.8, 0.6, LIT_SOFT)
        for cx_, cy_, r in SIDE_LOBES:      # the ear puffs catch light too
            px(cx_ - r * 0.32, cy_ - r, r * 0.64, 0.65, LIT_EAR)

        # the head's shadow on the torso, in the same ink as the limbs — one
        # translucent black over the body colour, never a second blue
        px(CX - TORSO_HW + 0.55, HEAD_B + 0.5, TORSO_HW * 2 - 1.1, 0.55,
           SHADE_NECK)
        px(CX - TORSO_HW + 1.1, HEAD_B + 1.05, TORSO_HW * 2 - 2.2, 0.5,
           SHADE_NECK2)

        # screen
        bite(SCR_L, SCR_T, SCR_R, SCR_B, SCREEN, inset=0.7)

        if cap:
            C.draw_hat(px, cap, frame, crown_row=HEAD_T + 0.2, cx=CX,
                       head_w=HEAD_W)

        # ---- the face: a prompt. `>` carries the expression, `_` the cursor --
        ink = AUTO_GLOW if autonomous else GLOW
        gazeable = eyes in ("open", "focus", "up", "wide")
        gx = gaze[0] * facing * 0.6 if gazeable else 0.0
        gy = gaze[1] * 0.4 if gazeable else 0.0
        ax, ay = 8.6 + gx, 6.2 + gy          # chevron anchor (top-left arm)
        bx, by = 11.2 + gx, 6.2 + gy         # cursor anchor

        def chevron(x, y, s=1.0, flip=1, color=None):
            c = color or ink
            px(x, y, 0.62 * s, 0.62 * s, c)
            px(x + 0.62 * s * flip, y + 0.62 * s, 0.62 * s, 0.62 * s, c)
            px(x, y + 1.24 * s, 0.62 * s, 0.62 * s, c)

        if eyes == "blink":
            px(ax - 0.1, ay + 0.75, 1.7, 0.55, ink)
            px(bx, by + 0.75, 1.7, 0.55, ink)
        elif eyes == "sleep":
            px(ax - 0.3, ay + 0.8, 2.1, 0.55, GLOW_DIM)
            px(bx - 0.2, by + 0.8, 2.1, 0.55, GLOW_DIM)
        elif eyes == "focus":
            chevron(ax + 0.3, ay + 0.3, 0.8)
            px(bx, by + 1.05, 1.5, 0.55, ink)
        elif eyes == "squint":               # `>` `<` aimed at the nose
            chevron(ax, ay)
            chevron(bx + 0.62, ay, 1.0, -1)
        elif eyes == "up":
            chevron(ax, ay - 0.5)
            px(bx, by + 0.45, 1.7, 0.55, ink)
        elif eyes == "wide":
            chevron(ax - 0.2, ay - 0.3, 1.2)
            px(bx - 0.1, by - 0.2, 1.9, 1.9, ink)      # block cursor
        elif eyes == "x":
            for x0 in (ax, bx):
                px(x0, ay + 0.6, 1.8, 0.5, bang)
                px(x0 + 0.65, ay, 0.5, 1.7, bang)
        elif eyes == "happy":                # `^ ^`
            chevron(ax + 0.62, ay + 0.6, 1.0, -1)
            px(ax, ay + 1.22, 0.62, 0.62, ink)
            px(ax + 1.24, ay + 1.22, 0.62, 0.62, ink)
            chevron(bx + 0.62, by + 0.6, 1.0, -1)
            px(bx, by + 1.22, 0.62, 0.62, ink)
            px(bx + 1.24, by + 1.22, 0.62, 0.62, ink)
        else:                                # open — the resting prompt
            chevron(ax, ay)
            if state in ("sleeping", "doze") or frame % 30 < 20:
                px(bx, by + 1.05, 1.7, 0.55, ink)

        # This mascot's answer to "running unattended": its own prompt burns
        # amber and a scanline crawls the pane. The face stays readable — you
        # can still see what it feels while it drives itself.
        if autonomous:
            sr = SCR_T + 0.4 + ((frame * 0.16) % (SCR_B - SCR_T - 0.8))
            px(SCR_L + 0.4, sr, SCR_R - SCR_L - 0.8, 0.4, SCAN)

        p.restore()
        C.draw_prop(p, ox, oy, u, rig["prop"], frame, state, body_dy, facing,
                    palette)
