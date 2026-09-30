"""companion_class / companion_unit: which creature a sidekick wears, how big."""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from types import SimpleNamespace as NS

from claudlet.pet import companion_class, companion_unit


def test_none_declared_is_small_copy():
    assert companion_class(NS(), 0) is None


def test_one_or_many_in_turn():
    class Cub: pass
    class Flake: pass
    assert companion_class(NS(companions=Cub), 3) is Cub
    av = NS(companions=(Cub, Flake))
    assert [companion_class(av, i) for i in range(3)] == [Cub, Flake, Cub]


def test_unit_is_its_life_size_resized_with_the_pet():
    pet = NS(scale=1, fractional_scale=True)
    assert companion_unit(pet, 1, NS(scale=2)) == 2
    assert companion_unit(pet, 2, NS(scale=2)) == 4          # user doubled the pet
    assert companion_unit(pet, 0.5, NS(scale=0.6, fractional_scale=True)) == 0.3
    assert companion_unit(pet, 0.1, NS(scale=2)) == 1        # whole-unit art never below 1
