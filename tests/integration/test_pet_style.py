"""Colour and scale: what the pet wears, changed without restarting it.

Driven through the pet's real surfaces — a config file it reads and the same
socket command `claudlet-config ui` sends — and observed through snapshot().
"""
import json
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import sys

from PyQt6.QtWidgets import QApplication

from claudlet import pet as P
from claudlet.core import petconfig

_app = QApplication.instance() or QApplication(sys.argv)


def _config(tmp_path, monkeypatch, **keys):
    path = tmp_path / "config.json"
    path.write_text(json.dumps(keys), encoding="utf-8")
    monkeypatch.setattr(petconfig, "config_path", lambda: str(path))
    return path


def test_scale_sizes_the_window(tmp_path, monkeypatch):
    _config(tmp_path, monkeypatch, scale=8)
    p = P.Pet(session_id="scale8")
    try:
        snap = p.snapshot()
        gw, gh = p.avatar.grid
        assert snap["scale"] == 8
        assert snap["size"] == ((gw + 2 * P.PAD_X) * 8, (gh + 2 * P.PAD_Y) * 8)
    finally:
        p._cleanup()


def test_scale_outside_the_range_is_clamped(tmp_path, monkeypatch):
    _config(tmp_path, monkeypatch, scale=99)
    p = P.Pet(session_id="scalebig")
    try:
        assert p.snapshot()["scale"] == petconfig.MAX_SCALE
    finally:
        p._cleanup()


def test_a_picked_colour_becomes_the_palette(tmp_path, monkeypatch):
    _config(tmp_path, monkeypatch, palette="#4A90D9")
    p = P.Pet(session_id="bluepet")
    try:
        pal = p.snapshot()["palette"]
        # a derived palette, not a name from the table
        assert isinstance(pal, dict) and pal["body"] == "#4A90D9"
        assert pal["hi"] != pal["lo"] != pal["bang"]
    finally:
        p._cleanup()


def test_a_named_palette_still_comes_through_by_name(tmp_path, monkeypatch):
    _config(tmp_path, monkeypatch, palette="shiny_teal")
    p = P.Pet(session_id="tealpet")
    try:
        assert p.snapshot()["palette"] == "shiny_teal"
    finally:
        p._cleanup()


def test_restyle_redresses_a_running_pet(tmp_path, monkeypatch):
    path = _config(tmp_path, monkeypatch, scale=4, palette="default")
    p = P.Pet(session_id="restyled")
    try:
        assert p.snapshot()["scale"] == 4
        path.write_text(json.dumps({"scale": 9, "palette": "#2FA88C"}),
                        encoding="utf-8")
        p._handle_event({"cmd": "restyle"})         # what the settings UI sends
        snap = p.snapshot()
        gw, gh = p.avatar.grid
        assert snap["scale"] == 9
        assert snap["size"] == ((gw + 2 * P.PAD_X) * 9, (gh + 2 * P.PAD_Y) * 9)
        assert snap["palette"]["body"] == "#2FA88C"
    finally:
        p._cleanup()


def test_restyle_keeps_the_shiny_a_pet_was_born_with(tmp_path, monkeypatch):
    # the shiny roll happens once per pet; re-reading config must not re-roll it
    path = _config(tmp_path, monkeypatch, palette="auto")
    p = P.Pet(session_id="shinykeep")
    try:
        p._palette_roll = (0.0, 0.0)                 # force a shiny
        p._apply_style(petconfig.load_config())
        born = p.snapshot()["palette"]
        assert born in petconfig.SHINY_PALETTES
        path.write_text(json.dumps({"palette": "auto", "scale": 6}),
                        encoding="utf-8")
        p._handle_event({"cmd": "restyle"})
        assert p.snapshot()["palette"] == born
        assert p.snapshot()["scale"] == 6
    finally:
        p._cleanup()


def test_the_floor_line_follows_the_scale(tmp_path, monkeypatch):
    """The foot line was pinned to the default scale, so an enlarged pet stood
    with the floor running through the middle of its body."""
    _config(tmp_path, monkeypatch, scale=9)
    p = P.Pet(session_id="footscale")
    try:
        assert p.u == 9
        assert p.foot_y == (P.PAD_Y + P.FOOT_ROW) * 9
        assert p.foot_y > P.FOOT_Y          # the default-scale value it used to be
    finally:
        p._cleanup()


def test_the_floor_line_follows_the_creature(tmp_path, monkeypatch):
    """A creature whose feet are not where the built-in's are says so, rather
    than standing sunk into or floating above the window it perches on."""
    _config(tmp_path, monkeypatch)
    p = P.Pet(session_id="footcreature")
    try:
        class Stumpy:
            name, grid, states, hats = "stumpy", (22, 17), ("idle",), ()
            foot_row = 10.0
            def draw(self, *a, **k): pass
            def set_lang(self, lang): pass

        p.avatar = Stumpy()
        assert p.foot_y == (P.PAD_Y + 10.0) * p.u
    finally:
        p._cleanup()


def test_companions_wear_the_same_creature_as_the_pet():
    """A companion is one of the pet's own. Resolving the creature name itself
    meant every sidekick turned up as the built-in while the pet was a slime."""
    class Blob:
        name, grid, states, hats = "blob", (10, 24), ("idle", "walk"), ()
        def draw(self, *a, **k): pass
        def set_lang(self, lang): pass

    p = P.Pet(session_id="companionavatar")
    try:
        p.avatar = Blob()
        p._debug_companions = 1
        p._sync_companion()
        assert p._companions, "no companion spawned"
        assert p._companions[0].avatar is p.avatar
    finally:
        p._cleanup()


def test_companions_wear_the_pet_colour_and_follow_a_change(tmp_path, monkeypatch):
    """A sidekick is one of the pet's own, so it is the pet's colour. And a
    colour-only change has to reach it — the re-dress used to run only when the
    size or the creature changed."""
    path = _config(tmp_path, monkeypatch, avatar="claudlet",
                   creatures={"claudlet": {"palette": "#00FFCC"}})
    p = P.Pet(session_id="companioncolour")
    try:
        p._debug_companions = 1
        p._sync_companion()
        assert p._companions[0].palette == p._palette
        assert p._palette["body"] == "#00FFCC"

        path.write_text(json.dumps(
            {"avatar": "claudlet",
             "creatures": {"claudlet": {"palette": "#FF00AA"}}}), encoding="utf-8")
        p._handle_event({"cmd": "restyle"})
        assert p._palette["body"] == "#FF00AA"
        assert p._companions[0].palette == p._palette
    finally:
        p._cleanup()
