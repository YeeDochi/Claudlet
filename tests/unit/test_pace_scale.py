"""pace_scale: walking pace follows the creature's on-screen body height."""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")   # before claudlet.pet forces xcb
from types import SimpleNamespace as NS

from claudlet.pet import pace_scale


def test_creature_without_crown_keeps_todays_pace():
    assert pace_scale(5, NS(foot_row=15.8)) == 1.0
    assert pace_scale(10, NS()) == 1.0          # built-in enlarged: unchanged
    assert pace_scale(5, None) == 1.0


def test_body_as_tall_as_builtin_is_one():
    assert pace_scale(5, NS(crown_row=3.0, foot_row=15.8)) == 1.0


def test_tall_sprite_creature_walks_faster_and_follows_its_size():
    big = NS(crown_row=58.0, foot_row=298.0)     # 240 dots at 1 px per dot
    assert pace_scale(1, big) == 240 / 64
    assert pace_scale(0.5, big) == 120 / 64      # user shrank it -> slower again


def test_clamped():
    assert pace_scale(1, NS(crown_row=0.0, foot_row=10000.0)) == 6.0
    assert pace_scale(1, NS(crown_row=0.0, foot_row=1.0)) == 0.5
