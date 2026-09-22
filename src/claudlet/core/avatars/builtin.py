"""The built-in claudlet — the code-drawn creature, as an Avatar.

Holds no art of its own: `core.creature` stays the single place the creature is
drawn (it is also the sprite-sheet entry point). This is the thin object that
lets the pet treat it as one avatar among others.
"""
from claudlet.core import creature as C


class Claudlet:
    name = "claudlet"
    persona = "짧고 명랑하게, 한 줄로."
    grid = (C.GRID_W, C.GRID_H)
    states = C.STATES
    hats = C.HAT_KINDS

    def draw(self, p, ox, oy, u, state, frame, **kw):
        C.draw_creature(p, ox, oy, u, state, frame, **kw)

    def set_lang(self, lang):
        C.set_lang(lang)
