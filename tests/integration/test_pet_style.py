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
