"""Skeletons to start from.

Nobody builds a bone tree from nothing. A preset is a working creature — parts,
parents, pivots, roles already set — so making one of your own is painting
pixels onto parts that already move, and an agent fitting someone's drawing has
a known shape to fit it TO rather than a topology to invent.

The preset is also where quality lives: "how a humanoid walks" is tuned once
here and every humanoid avatar inherits it.
"""
from claudlet.core.avatars.presets.creature import CREATURE

PRESETS = {CREATURE.name: CREATURE}


def get(name):
    return PRESETS.get(name)


def available():
    return sorted(PRESETS)
