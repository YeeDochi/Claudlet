"""The avatar is an object the pet wears, not something baked into it.

The point of the seam is a second implementation — a creature built from a
user's own pixels — so these check that anything satisfying the contract can be
dropped in, including one with different proportions.
"""
import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication

from claudlet.core import avatars

_app = QApplication.instance() or QApplication(sys.argv)


class Tall:
    """A stand-in custom avatar: taller than the built-in, draws nothing."""
    name = "tall"
    grid = (16, 30)
    states = ("idle", "walk")
    hats = ()

    def __init__(self):
        self.painted = []

    def draw(self, p, ox, oy, u, state, frame, **kw):
        self.painted.append(state)

    def set_lang(self, lang):
        pass


def test_builtin_is_the_default():
    a = avatars.get()
    assert a.name == "claudlet"
    assert a.grid == (22, 17) and len(a.states) > 1


def test_an_unknown_name_falls_back_instead_of_raising():
    # a config or env var naming a removed avatar must not stop the pet starting
    assert avatars.get("no-such-avatar").name == "claudlet"
    assert avatars.get(None).name == "claudlet"


def test_available_lists_the_builtin_first():
    # what a selector would offer
    assert avatars.available()[0] == "claudlet"


def test_a_plain_object_satisfies_the_contract():
    # structural, not inheritance: a custom avatar won't subclass ours
    assert isinstance(Tall(), avatars.Avatar)
    assert not isinstance(object(), avatars.Avatar)


def test_the_pet_takes_its_window_size_from_the_avatar():
    from claudlet import pet as P
    p = P.Pet(session_id="avatarsize")
    try:
        gw, gh = p.avatar.grid
        assert p.w == (gw + 2 * P.PAD_X) * P.U
        assert p.h == (gh + 2 * P.PAD_Y) * P.U
    finally:
        p._cleanup()


def test_a_swapped_avatar_is_what_gets_painted():
    from claudlet import pet as P
    p = P.Pet(session_id="avatarswap")
    try:
        tall = Tall()
        p.avatar = tall
        p.grab()                      # runs paintEvent offscreen
        assert tall.painted, "the pet painted something other than its avatar"
    finally:
        p._cleanup()
