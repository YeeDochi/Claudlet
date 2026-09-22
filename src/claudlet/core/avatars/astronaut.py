"""astronaut — a humanoid in a pressure suit.

Bundled as a worked example alongside `slime.py`. Where the slime shows that a
creature need not have legs at all, this one shows that it need not be shaped
like the built-in either: it stands upright, and it answers the "running
unattended" flag with a lit visor rather than a headset.

Unlike the built-in (a four-legged critter) this one stands upright: helmet,
torso, two arms, two legs, a life-support pack on its back. It keeps the
built-in 22x17 grid on purpose — draw_prop's laptop/bubble/z's are drawn in
those coordinates, so a taller box would hang them in mid-air.

Notes on what it does its own way:
  * no rotation. Limbs here are 2 art pixels wide; rotating them shreds the
    edges. A lean is a SHEAR (each row slid sideways with its height), and a
    stride is the legs translating, never swinging around a hip joint.
  * its unattended look is the visor: it lights up with a scan line and the
    antenna beacon blinks, instead of the built-in's VR headset.
  * the suit takes the user's palette (hi = fabric, body = shaded side,
    lo = gloves/boots/pack) so the colour picker actually drives it.
"""
import math

from PyQt6.QtCore import QRect, Qt
from PyQt6.QtGui import QColor

from claudlet.core import creature as C

GRID_W, GRID_H = 22, 17
CX, FLOOR = 11.0, 13.4          # centre column, floor row

VISOR = QColor("#1B2030")
VISOR_HI = QColor("#5E7BA8")
GLINT = QColor(255, 255, 255, 200)
EYE = QColor("#BFE9FF")
BEACON = QColor("#FF4D4D")
PANEL = QColor("#2A2E3A")
LED_G = QColor("#5CE07A")
LED_A = QColor("#FFC24D")

STATES = ("idle", "walk", "work_computer", "work_search", "work_web",
          "work_agent", "work_skill", "autopilot",
          "thinking", "attention", "asking", "error", "angry",
          "celebrate", "sleeping", "held", "falling", "jump", "wave", "sing",
          "juggle", "float", "climbdown", "strain", "leap",
          "observe", "tic", "settle", "doze")


class Astronaut:
    name = "astronaut"
    grid = (GRID_W, GRID_H)
    states = STATES
    hats = C.HAT_KINDS      # companions wear one; drawn by C.draw_hat
    palette = "#C9D2E0"          # suit white-blue, until the user picks
    persona = "무전 교신하듯 담담하고 침착한 말투. 짧게."
    # boots end well above the built-in's 15.8, so say so or the pet stands it
    # sunk into whatever window it perches on
    foot_row = FLOOR

    def set_lang(self, lang):
        C.set_lang(lang)

    def draw(self, p, ox, oy, u, state, frame, facing=1, autonomous=False,
             cap=None, energy=1.0, palette=None, happy=False, hovering=False,
             gaze=(0.0, 0.0), **kw):
        p.setPen(Qt.PenStyle.NoPen)
        body, hi, lo, _bang = C.palette_colors(palette)
        suit, shade, gear = hi, body, lo

        rig = C.state_rig(state, frame, energy, happy, autonomous, gaze)
        sx, sy = rig["sx"], rig["sy"]
        eyes = "happy" if happy else rig["eyes"]
        body_dy = C._snap_offset(rig["bob"] + rig["baseline_lift"], u)
        shear = math.tan(math.radians(rig["tilt"])) * 1.1

        # squash about the body centre; snap BOUNDARIES so cells share edges
        def xof(col):
            return ox + (CX + (col - CX) * sx) * u

        def yof(row):
            return oy + (10.0 + (row - 10.0) * sy + body_dy) * u

        def px(col, row, w, h, color):
            d = shear * (FLOOR - (row + h / 2.0))
            x0, x1 = C._r(xof(col + d)), C._r(xof(col + d + w))
            y0, y1 = C._r(yof(row)), C._r(yof(row + h))
            p.fillRect(QRect(x0, y0, max(1, x1 - x0), max(1, y1 - y0)), color)

        p.save()
        if facing < 0:                      # body only — props stay upright
            p.translate(2 * (ox + GRID_W / 2.0 * u), 0)
            p.scale(-1, 1)

        # ---- legs (shaded, split, so they read as two limbs) ----------
        if rig["walking"]:
            sw = math.sin(rig["legphase"] * 2 * math.pi) * 1.1
            liftL = max(0.0, sw) * 0.5
            liftR = max(0.0, -sw) * 0.5
        else:
            sw = liftL = liftR = 0.0
        tuck = 1.0 if (not rig["walking"] and rig["legphase"] >= 0.5) else 0.0

        def leg(col, lift):
            top = 11.1 + tuck
            px(col, top, 1.6, 12.6 - top - lift, shade)
            px(col - 0.3, 12.6 - lift, 2.2, 0.8, gear)       # boot

        # front view: a stride is legs LIFTING in turn plus a small shared
        # sway. Swinging them toward each other merges them into one slab.
        leg(CX - 2.0 + sw * 0.3, liftL)
        leg(CX + 0.4 + sw * 0.3, liftR)

        # ---- life-support pack (worn on the back) ------------------------
        px(CX - 3.7, 8.2, 1.6, 2.8, gear)
        px(CX - 3.7, 8.2, 1.6, 0.5, shade)
        px(CX - 3.4, 8.9, 0.9, 1.4, PANEL)

        # ---- torso -------------------------------------------------------
        px(CX - 2.2, 8.2, 4.4, 3.0, suit)
        px(CX + 1.2, 8.2, 1.0, 3.0, shade)                   # shaded side
        px(CX - 2.2, 10.7, 4.4, 0.6, gear)                   # belt
        px(CX - 1.2, 8.9, 2.4, 1.4, PANEL)                   # control panel
        px(CX - 0.8, 9.2, 0.6, 0.5, LED_G if frame % 40 < 28 else LED_A)
        px(CX + 0.2, 9.2, 0.6, 0.5, LED_A)
        px(CX - 0.8, 9.9, 1.6, 0.3, VISOR_HI)

        # ---- helmet ------------------------------------------------------
        # Kept LOW and the antenna swept out to the side: props are drawn in
        # this same box and the speech bubble owns rows 0-4. A tall crown (or
        # an upright aerial) pokes straight through the bubble.
        px(CX - 1.0, 7.9, 2.0, 0.6, gear)                    # neck ring
        px(CX - 3.0, 5.0, 6.0, 3.0, suit)                    # dome
        px(CX - 2.4, 4.6, 4.8, 0.4, suit)                    # crown, step 1
        px(CX - 1.5, 4.3, 3.0, 0.3, suit)                    # crown, step 2
        px(CX + 2.0, 5.0, 1.0, 3.0, shade)                   # shaded side
        px(CX - 3.0, 7.6, 6.0, 0.4, shade)                   # chin shadow

        vx, vy, vw, vh = CX - 1.9, 5.5, 3.8, 1.9
        px(vx, vy, vw, vh, VISOR)
        px(vx + 0.5, vy - 0.35, vw - 1.0, 0.35, VISOR)       # domed top
        px(vx + 0.5, vy - 0.35, vw - 1.0, 0.3, VISOR_HI)

        # antenna, swept out of the bubble's way + beacon
        px(CX + 2.7, 4.8, 0.5, 0.9, gear)
        px(CX + 3.1, 4.3, 0.5, 0.6, gear)
        lit = autonomous and frame % 30 < 15
        px(CX + 2.95, 3.9, 0.9, 0.6, BEACON if lit else VISOR_HI)

        if cap:                      # helmet is 6 wide and its crown is at 4.3
            C.draw_hat(px, cap, frame, crown_row=4.3, cx=CX, head_w=6.0)

        # ---- arms (drawn AFTER the helmet so a raised one stays visible) --
        # The SHOULDER is fixed and the HAND moves. Translating the whole arm
        # up instead leaves the glove down by the hip and reads as a shrug.
        arm, asw = rig["arm"], rig["arm_swing"]
        SHOULDER, GLOVE = 8.3, 0.9

        def limb(side, hand):
            up = hand < SHOULDER
            # a raised arm swings OUT past the helmet: at the torso edge it
            # sits behind the dome, same tone, and disappears
            col = CX + (2.2 + (0.9 if up else 0.0)) * side + (0.0 if side > 0 else -1.5)
            if up:
                px(col, hand + GLOVE, 1.5, SHOULDER - hand - GLOVE + 0.4, shade)
                px(col - 0.15, hand, 1.8, GLOVE, gear)
            else:
                px(col, SHOULDER, 1.5, hand - SHOULDER, shade)
                px(col - 0.15, hand, 1.8, GLOVE, gear)

        if arm == "up":
            limb(-1, 5.4); limb(+1, 5.4)
        elif arm == "wave":
            limb(-1, 10.4 + asw)
            limb(+1, 5.3 + C._sin(frame, 16, 0.8))
        elif arm == "tap":
            limb(-1, 10.3 + rig["front_tap"])
            limb(+1, 10.3 + (0.8 - rig["front_tap"]))
        elif arm != "none":
            limb(-1, 10.4 + asw); limb(+1, 10.4 - asw)

        # ---- face, inside the glass --------------------------------------
        def eye(col, kind):
            gazeable = kind in ("open", "focus", "up", "wide")
            c = col + (gaze[0] * facing * 0.5 if gazeable else 0.0)
            r = vy + 0.8 + (gaze[1] * 0.35 if gazeable else 0.0)
            if kind == "open":
                px(c, r, 1.2, 1.4, EYE)
            elif kind == "blink":
                px(c, r + 0.9, 1.2, 0.5, EYE)
            elif kind == "sleep":
                px(c - 0.1, r + 0.9, 1.5, 0.5, EYE)
            elif kind == "focus":
                px(c, r + 0.5, 1.4, 0.7, EYE)
            elif kind == "squint":                 # "> <" pointing at the nose
                left = c < CX
                m = c + (0.4 if left else -0.4)
                vtx = m + 0.7 if left else m
                out = m if left else m + 0.7
                px(out, r + 0.1, 0.9, 0.5, EYE)
                px(vtx, r + 0.65, 0.9, 0.5, EYE)
                px(out, r + 1.2, 0.9, 0.5, EYE)
            elif kind == "up":
                px(c, r - 0.4, 1.2, 1.2, EYE)
            elif kind == "wide":
                px(c - 0.25, r - 0.4, 1.8, 2.1, EYE)
            elif kind == "x":
                px(c, r + 0.5, 1.5, 0.4, EYE)
                px(c + 0.55, r - 0.05, 0.4, 1.5, EYE)
            elif kind == "happy":
                px(c, r + 0.8, 0.5, 0.5, EYE)
                px(c + 0.45, r + 0.3, 0.5, 0.5, EYE)
                px(c + 0.9, r + 0.8, 0.5, 0.5, EYE)

        working = state.startswith("work_") or state == "autopilot"
        if autonomous and working:
            # glass goes opaque and a scan line sweeps it: this creature's
            # answer to "running unattended"
            px(vx, vy, vw, vh, VISOR_HI)
            px(vx, vy + (frame % 26) / 26.0 * (vh - 0.4), vw, 0.4, EYE)
        else:
            eye(CX - 1.7, eyes)
            eye(CX + 0.5, eyes)

        px(vx + 0.3, vy + 0.35, 1.0, 0.5, GLINT)   # glass glint
        px(vx + 0.3, vy + 0.85, 0.5, 0.4, GLINT)

        p.restore()
        C.draw_prop(p, ox, oy, u, rig["prop"], frame, state, body_dy, facing,
                    palette)


AVATAR = Astronaut
