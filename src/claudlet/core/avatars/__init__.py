"""The creature the pet wears — swappable.

`pet.py` owns a window, movement and interaction; it should not also know how
the creature is drawn. Everything it needs from an avatar is here: how big the
art is (the window is sized from it), what it can render, and how to paint a
frame. Anything satisfying `Avatar` can be dropped in, which is what a custom
avatar built from a user's own pixels will be.

`Avatar` is a `Protocol`, not a base class, on purpose. A custom avatar will be
built from a data file rather than written as a subclass of ours, and structural
typing lets it satisfy the contract without inheriting anything. Nothing here
runs at import time beyond building the registry.
"""
try:
    from typing import Protocol, runtime_checkable
except ImportError:                       # py<3.8 — the contract is documentation
    Protocol = object

    def runtime_checkable(c):
        return c


@runtime_checkable
class Avatar(Protocol):
    """What the pet needs from whatever it is wearing.

    name   — id a selector stores and `get()` resolves.
    grid   — (w, h) bounding box in ART PIXELS. The pet's window is sized from
             this, so an avatar with different proportions gets a window that
             fits it; never assume the built-in 22x17.
    states — display states this avatar can draw. The pet falls back to a state
             in here rather than painting nothing.
    hats   — hat kinds companions may wear ( () if the avatar has none).
    """

    name: str
    grid: tuple
    states: tuple
    hats: tuple

    def draw(self, p, ox, oy, u, state, frame, **kw):
        """Paint one frame at (ox, oy), `u` device pixels per art pixel.

        Keywords are optional dressing (facing, visor, cap, energy, palette,
        happy, pocket, gaze); an avatar ignores what it doesn't support rather
        than raising, so the pet can pass everything it knows."""

    def set_lang(self, lang):
        """Language for any text the avatar draws (speech bubbles)."""


DEFAULT = "claudlet"


def _registry():
    # imported lazily: this package is pulled in by Qt-free modules too, and
    # the built-in avatar's art module needs QtGui.
    from claudlet.core.avatars.builtin import Claudlet
    return {Claudlet.name: Claudlet}


def available():
    """Avatar names a selector can offer, the built-in one first."""
    names = sorted(_registry())
    return [DEFAULT] + [n for n in names if n != DEFAULT]


def get(name=None):
    """The named avatar, or the built-in one.

    An unknown name falls back rather than raising: a config or env var naming
    an avatar that has been removed must not stop the pet from starting."""
    reg = _registry()
    cls = reg.get(name) or reg[DEFAULT]
    return cls()
