import sys, os, json, types

MOD_PATH = os.path.join(os.path.dirname(__file__), "..", "bin", "claude-pet-motion")
mod = types.ModuleType("claude_pet_motion")
mod.__file__ = MOD_PATH
with open(MOD_PATH) as f:
    exec(compile(f.read(), MOD_PATH, "exec"), mod.__dict__)


def test_new_motions_present():
    for m in ("jump", "wave", "sing", "juggle", "float"):
        assert m in mod.MOTIONS


def test_float_holds_by_default():
    assert mod.MOTIONS["float"] == 0.0
    assert mod.resolve_dur("float", None) == 0.0


def test_resolve_dur_override_wins():
    assert mod.resolve_dur("jump", "5") == 5.0
    assert mod.resolve_dur("jump", None) == mod.MOTIONS["jump"]


def test_build_message_is_json_line():
    line = mod.build_motion_message("jump", 2.5)
    assert line.endswith("\n")
    obj = json.loads(line)
    assert obj == {"cmd": "motion", "motion": "jump", "dur": 2.5}


def test_build_message_clear():
    obj = json.loads(mod.build_motion_message(None, 0))
    assert obj["cmd"] == "motion" and obj["motion"] is None


def test_main_list_and_unknown(capsys):
    assert mod.main(["claude-pet-motion", "list"]) == 0
    assert mod.main(["claude-pet-motion", "bogus"]) == 1
