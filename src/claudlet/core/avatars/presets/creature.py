"""The claudlet shape, as rig data.

This preset exists first on purpose. Reproducing the built-in creature is how
the format gets checked: the reference art is right here, tuned across 28
states, so "can this format express a creature?" is answered by looking at the
two sprite sheets side by side rather than by arguing about the schema.

Not pixel-identical, and not meant to be. The built-in art is rectangles at
fractional art-pixel coordinates (`px(3.0, 5.0, 15.0, 7.5)`); pixels a person
draws land on whole ones. What has to survive the move is the SHAPE and the
MOTION, not the half-pixel.
"""
from claudlet.core.avatars.rig import Part, Rig


def _rows(w, h, ch):
    return [ch * w] * h


# body: cols 3..18, rows 5..12.5 in the built-in art -> 15 x 8 whole pixels,
# with the bevel highlight on top and the shade along the bottom
# rows 5..11 inclusive (7 tall, matching the built-in's 7.5): the top row is
# the bevel highlight, the bottom the shade the legs hang out of.
_BODY = _rows(15, 1, "h") + _rows(15, 5, "b") + _rows(15, 1, "l")

# Leg columns are the built-in's, rounded to whole pixels and kept symmetric
# about the body centre: centres at 5 / 8 / 13 / 16, i.e. pairs either side of
# 10.5. Four rows tall so they CLEAR the body's shade row — at three they
# merged with it into one notched block instead of reading as legs.
_LEG_COLS = (1, 4, 9, 12)          # relative to the body's left edge
_LEG_ROW, _LEG_H = 7, 4

# Eyes are the face. At three art pixels across they are crude, but a shut eye
# has to look shut or a sleeping creature reads as a staring one. Keys are the
# `eyes` values `creature.state_rig` produces.
# Eyes carry the expression, and in the built-in art they are not one shape
# moved around: each is its own size. The closed eye is wide and one pixel
# tall, the focused one is short, the surprised one is bigger in both
# directions. Variants that keep a constant box read as one face pulling the
# same expression over and over, so these vary like the original does.
#
# The squint is MIRRORED — ">" on the left eye and "<" on the right, points
# toward the nose. Which variants mirror is the avatar's business, not the
# engine's, so the right eye simply gets its own flipped table.
_EYES = {
    "open":   ["ee", "ee", ".."],          # 1.4 x 1.8 -> narrow and upright
    "blink":  ["..", "..", "ee"],          # 1.4 x 0.6 -> a line, low
    "sleep":  ["...", "...", "eee"],       # 2.6 x 0.6 -> wider line, low
    "focus":  ["..", "ee", ".."],          # 1.6 x 0.9 -> short, mid
    "up":     ["ee", "ee", ".."],          # raised by the gaze, same shape
    "wide":   ["eee", "eee", "eee"],       # 1.9 x 2.4 -> bigger both ways
    "x":      ["e.e", ".e.", "e.e"],
    "happy":  ["e.e", ".e.", "..."],       # ^ ^
    "squint": ["e..", ".e.", "e.."],       # >  (mirrored for the right eye)
}
_MIRRORED = ("squint", "x", "happy")


def _flip(rows):
    return [row[::-1] for row in rows]


_EYES_R = dict(_EYES)
for _k in _MIRRORED:
    _EYES_R[_k] = _flip(_EYES[_k])

CREATURE = Rig(
    name="creature",
    grid=(22, 17),
    foot_row=15.8,          # where the legs end; the pet stands on this line
    parts=[
        Part("body", "body", at=(3, 5), pixels=_BODY),
        # legs hang off the body, so moving the body moves them
        Part("leg0", "leg", at=(_LEG_COLS[0], _LEG_ROW),
             pixels=_rows(2, _LEG_H, "l"), parent="body", index=0),
        Part("leg1", "leg", at=(_LEG_COLS[1], _LEG_ROW),
             pixels=_rows(2, _LEG_H, "l"), parent="body", index=1),
        Part("leg2", "leg", at=(_LEG_COLS[2], _LEG_ROW),
             pixels=_rows(2, _LEG_H, "l"), parent="body", index=2),
        Part("leg3", "leg", at=(_LEG_COLS[3], _LEG_ROW),
             pixels=_rows(2, _LEG_H, "l"), parent="body", index=3),
        Part("arm0", "arm", at=(-2, 3), pixels=_rows(2, 2, "l"), parent="body", index=0),
        Part("arm1", "arm", at=(15, 3), pixels=_rows(2, 2, "l"), parent="body", index=1),
        Part("eye0", "eye", at=(3, 2), pixels=_EYES["open"], parent="body",
             index=0, variants=_EYES),
        Part("eye1", "eye", at=(11, 2), pixels=_EYES_R["open"], parent="body",
             index=1, variants=_EYES_R),
    ],
)
