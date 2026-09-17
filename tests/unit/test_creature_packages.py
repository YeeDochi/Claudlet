"""A creature is a package the pet loads, not a format the pet interprets.

The pet says which STATE to be in; everything about how that looks belongs to
the creature. These check that something dropped into the creatures directory
is found, worn, and that a broken one can't take the pet down with it.
"""
import os
import sys
import textwrap

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication

from claudlet.core import avatars

_app = QApplication.instance() or QApplication(sys.argv)

CREATURE = textwrap.dedent('''
    class Blob:
        name = "blob"
        grid = (10, 24)          # nothing like the built-in 22x17
        states = ("idle", "walk")
        hats = ()

        def __init__(self):
            self.painted = []

        def draw(self, p, ox, oy, u, state, frame, **kw):
            self.painted.append(state)

        def set_lang(self, lang):
            pass

    AVATAR = Blob
''')


def _install(tmp_path, monkeypatch, name, source):
    d = tmp_path / "creatures" / name
    d.mkdir(parents=True)
    (d / "__init__.py").write_text(source, encoding="utf-8")
    monkeypatch.setattr(avatars, "CREATURES_DIR", str(tmp_path / "creatures"))
    return d


def test_a_dropped_in_creature_is_offered(tmp_path, monkeypatch):
    _install(tmp_path, monkeypatch, "blob", CREATURE)
    assert "blob" in avatars.available()
    assert avatars.get("blob").name == "blob"


def test_a_creature_brings_its_own_proportions(tmp_path, monkeypatch):
    # the pet's window follows the creature, so one shaped nothing like the
    # built-in still gets a window that fits it
    _install(tmp_path, monkeypatch, "blob", CREATURE)
    from claudlet import pet as P
    monkeypatch.setenv("CLAUDLET_AVATAR", "blob")
    p = P.Pet(session_id="blobpet")
    try:
        snap = p.snapshot()
        assert snap["avatar"] == "blob"
        assert snap["size"] == ((10 + 2 * P.PAD_X) * p.u, (24 + 2 * P.PAD_Y) * p.u)
    finally:
        p._cleanup()


def test_a_broken_creature_is_skipped_not_fatal(tmp_path, monkeypatch):
    # someone's half-written creature must not stop the pet from starting
    _install(tmp_path, monkeypatch, "broken", "this is not python(")
    assert "broken" not in avatars.available()
    assert avatars.get("broken").name == "claudlet"


def test_a_creature_with_no_entry_point_is_skipped(tmp_path, monkeypatch):
    _install(tmp_path, monkeypatch, "empty", "# nothing exported\n")
    assert "empty" not in avatars.available()


def test_no_creatures_directory_at_all_is_fine(tmp_path, monkeypatch):
    monkeypatch.setattr(avatars, "CREATURES_DIR", str(tmp_path / "nope"))
    assert avatars.available()[0] == "claudlet"     # bundled ones still there


def test_a_dropped_in_creature_overrides_a_bundled_one_of_the_same_name(
        tmp_path, monkeypatch):
    # your own file wins: a bundled creature is a starting point, not a lock
    _install(tmp_path, monkeypatch, "slime", CREATURE.replace('"blob"', '"slime"'))
    assert avatars.get("slime").grid == (10, 24)     # the dropped-in one
