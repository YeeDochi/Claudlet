"""companion_name / companion_unit: which creature a sidekick wears, how big."""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from types import SimpleNamespace as NS

from claudlet.pet import companion_name, companion_unit


def test_none_declared_is_small_copy():
    assert companion_name(NS(), 0, {"a"}) is None


def test_one_name_or_many_in_turn_skipping_missing():
    assert companion_name(NS(companion="cub"), 3, {"cub"}) == "cub"
    av = NS(companion=("cub", "gone", "flake"))
    assert [companion_name(av, i, {"cub", "flake"}) for i in range(3)] == ["cub", "flake", "cub"]
    assert companion_name(NS(companion=("gone",)), 0, {"cub"}) is None


def test_unit_is_its_life_size_resized_with_the_pet():
    pet = NS(scale=1, fractional_scale=True)
    assert companion_unit(pet, 1, NS(scale=2)) == 2
    assert companion_unit(pet, 2, NS(scale=2)) == 4          # user doubled the pet
    assert companion_unit(pet, 0.5, NS(scale=0.6, fractional_scale=True)) == 0.3
    assert companion_unit(pet, 0.1, NS(scale=2)) == 1        # whole-unit art never below 1
