import pytest
import os, json, tempfile

from claudlet.core import petconfig


def _write(tmp, obj):
    p = os.path.join(tmp, "config.json")
    with open(p, "w", encoding="utf-8") as f:
        json.dump(obj, f)
    return p


EMPTY = {"tool_states": {}, "event_states": {}, "raw_events": {}, "lang": "auto",
         "roam_area": None, "no_go": [], "palette": "auto",
         "scale": petconfig.DEFAULT_SCALE, "avatar": None, "creatures": {},
         "dock": petconfig.default_dock()}


def test_valid_overrides_kept():
    with tempfile.TemporaryDirectory() as tmp:
        p = _write(tmp, {"tools": {"Bash": "work_search", "Grep": "sing"},
                         "events": {"prompt": "jump"},
                         "raw_events": {"PostToolUse": "celebrate"}})
        cfg = petconfig.load_config(p)
        assert cfg["tool_states"] == {"Bash": "work_search", "Grep": "sing"}
        assert cfg["event_states"] == {"prompt": "jump"}
        assert cfg["raw_events"] == {"PostToolUse": "celebrate"}


def test_invalid_values_and_keys_dropped():
    with tempfile.TemporaryDirectory() as tmp:
        p = _write(tmp, {"tools": {"Bash": "not_a_state", "Grep": "sing"},
                         "events": {"prompt": "jump", "bogus_slot": "idle",
                                    "done": "not_a_state"},
                         "raw_events": {"PostToolUse": "wave", "X": "not_a_state"}})
        cfg = petconfig.load_config(p)
        assert cfg["tool_states"] == {"Grep": "sing"}     # bad value dropped
        assert cfg["event_states"] == {"prompt": "jump"}  # bad slot/value dropped
        assert cfg["raw_events"] == {"PostToolUse": "wave"}  # bad value dropped


def test_missing_or_broken_file_yields_empty():
    assert petconfig.load_config("/no/such/file.json") == EMPTY
    with tempfile.TemporaryDirectory() as tmp:
        p = os.path.join(tmp, "config.json")
        with open(p, "w") as f:
            f.write("{ this is not json ")
        assert petconfig.load_config(p) == EMPTY


def test_non_dict_json_yields_empty():
    with tempfile.TemporaryDirectory() as tmp:
        p = _write(tmp, ["not", "a", "dict"])
        assert petconfig.load_config(p) == EMPTY


@pytest.mark.real_config_path
def test_config_path_respects_xdg(monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", "/tmp/xdgtest")
    assert petconfig.config_path() == os.path.join("/tmp/xdgtest", "claudlet", "config.json")


def test_lang_parsed_and_defaulted(tmp_path):
    p = _write(str(tmp_path), {"lang": "en"})
    assert petconfig.load_config(p)["lang"] == "en"
    p2 = _write(str(tmp_path), {"lang": "nonsense"})
    assert petconfig.load_config(p2)["lang"] == "auto"   # bad value -> auto
    p3 = _write(str(tmp_path), {})
    assert petconfig.load_config(p3)["lang"] == "auto"    # absent -> auto


def test_resolve_lang(monkeypatch):
    assert petconfig.resolve_lang("ko") == "ko"
    assert petconfig.resolve_lang("en") == "en"
    monkeypatch.setenv("LANG", "ko_KR.UTF-8")
    monkeypatch.delenv("LC_ALL", raising=False)
    monkeypatch.delenv("LC_MESSAGES", raising=False)
    assert petconfig.resolve_lang("auto") == "ko"
    monkeypatch.setenv("LANG", "en_US.UTF-8")
    assert petconfig.resolve_lang("auto") == "en"


def test_roam_area_parsed():
    with tempfile.TemporaryDirectory() as tmp:
        cfg = petconfig.load_config(_write(tmp, {"roam_area": {"x": 0, "y": 0, "w": 800, "h": 600}}))
        assert cfg["roam_area"] == {"x": 0.0, "y": 0.0, "w": 800.0, "h": 600.0}


def test_roam_area_invalid_dropped():
    with tempfile.TemporaryDirectory() as tmp:
        cfg = petconfig.load_config(_write(tmp, {"roam_area": {"x": 0, "y": 0, "w": -5, "h": 600}}))
        assert cfg["roam_area"] is None


def test_no_go_filters_invalid():
    with tempfile.TemporaryDirectory() as tmp:
        cfg = petconfig.load_config(_write(tmp, {"no_go": [
            {"x": 1, "y": 2, "w": 3, "h": 4},
            {"x": 1, "y": 2, "w": 0, "h": 4},      # w<=0 dropped
            "nonsense",                             # non-dict dropped
        ]}))
        assert cfg["no_go"] == [{"x": 1.0, "y": 2.0, "w": 3.0, "h": 4.0}]


def test_roam_keys_default_absent():
    with tempfile.TemporaryDirectory() as tmp:
        cfg = petconfig.load_config(_write(tmp, {}))
        assert cfg["roam_area"] is None and cfg["no_go"] == []


def test_resolve_palette_auto_shiny_on_low_roll():
    assert petconfig.resolve_palette("auto", roll=0.001, pick=0.0) in petconfig.SHINY_PALETTES


def test_resolve_palette_auto_default_on_high_roll():
    assert petconfig.resolve_palette("auto", roll=0.9, pick=0.0) == "default"


def test_resolve_palette_forced_name():
    assert petconfig.resolve_palette("shiny_violet", roll=0.9) == "shiny_violet"


def test_resolve_palette_unknown_is_default():
    assert petconfig.resolve_palette("banana", roll=0.001) == "default"


def test_palette_config_key():
    with tempfile.TemporaryDirectory() as tmp:
        assert petconfig.load_config(_write(tmp, {"palette": "shiny_teal"}))["palette"] == "shiny_teal"
        assert petconfig.load_config(_write(tmp, {}))["palette"] == "auto"


def test_dock_defaults_to_bottom_right_and_enabled():
    with tempfile.TemporaryDirectory() as tmp:
        d = petconfig.load_config(_write(tmp, {}))["dock"]
        assert d["enabled"] is True and d["anchor"] == "bottom-right"
        assert d["offset"] == {"x": 0.0, "y": 0.0} and d["screen"] == "primary"


def test_dock_overrides_parsed():
    with tempfile.TemporaryDirectory() as tmp:
        d = petconfig.load_config(_write(tmp, {"dock": {
            "enabled": False, "anchor": "top-left", "gap": 12,
            "screen": 1, "offset": {"x": -40, "y": -8}}}))["dock"]
        assert d == {"enabled": False, "anchor": "top-left", "gap": 12,
                     "screen": 1, "offset": {"x": -40.0, "y": -8.0}}


def test_dock_bad_values_fall_back_to_defaults():
    with tempfile.TemporaryDirectory() as tmp:
        d = petconfig.load_config(_write(tmp, {"dock": {
            "enabled": "yes", "anchor": "sideways", "gap": "wide",
            "screen": True, "offset": "nope"}}))["dock"]
        assert d == petconfig.default_dock()      # screen=true는 0번 모니터가 아니다


def test_dock_section_that_is_not_an_object_is_ignored():
    with tempfile.TemporaryDirectory() as tmp:
        assert petconfig.load_config(_write(tmp, {"dock": 3}))["dock"] \
            == petconfig.default_dock()


def test_default_dock_is_a_fresh_copy():
    d = petconfig.default_dock()
    d["offset"]["x"] = 99.0
    assert petconfig.default_dock()["offset"]["x"] == 0.0


def test_save_dock_merges_and_keeps_the_rest_of_the_config():
    with tempfile.TemporaryDirectory() as tmp:
        p = _write(tmp, {"lang": "ko", "tools": {"Bash": "sing"},
                         "dock": {"anchor": "top-left"}})
        saved = petconfig.save_dock({"offset": {"x": -12, "y": -4}}, p)
        assert saved["anchor"] == "top-left"          # 기존 dock 키는 살아남고
        assert saved["offset"] == {"x": -12.0, "y": -4.0}
        cfg = petconfig.load_config(p)
        assert cfg["lang"] == "ko"                    # dock 밖의 설정도 그대로
        assert cfg["tool_states"] == {"Bash": "sing"}
        assert cfg["dock"]["offset"] == {"x": -12.0, "y": -4.0}


def test_save_dock_creates_a_config_when_there_is_none():
    with tempfile.TemporaryDirectory() as tmp:
        p = os.path.join(tmp, "nested", "config.json")
        petconfig.save_dock({"enabled": False}, p)
        assert petconfig.load_config(p)["dock"]["enabled"] is False


def test_save_dock_does_not_blow_up_on_a_broken_config():
    with tempfile.TemporaryDirectory() as tmp:
        p = os.path.join(tmp, "config.json")
        with open(p, "w") as f:
            f.write("{ broken ")
        assert petconfig.save_dock({"enabled": False}, p)["enabled"] is False


class _Slime:
    palette = "#3FBF6F"


def test_pre_per_creature_config_belongs_to_the_builtin():
    # a 1.7.x config has palette/scale at the top level, written when the
    # built-in was the only creature there was
    cfg = petconfig._clean({"palette": "#4A90D9", "scale": 8})
    assert petconfig.for_creature(cfg, "claudlet")["palette"] == "#4A90D9"
    assert petconfig.for_creature(cfg, "claudlet")["scale"] == 8


def test_a_legacy_colour_is_not_spread_over_every_creature():
    # carrying it forward to all of them painted the built-in in a colour that
    # had been picked for something else
    cfg = petconfig._clean({"palette": "#4A90D9", "scale": 8})
    slime = petconfig.for_creature(cfg, "slime", _Slime)
    assert slime["palette"] == "#3FBF6F"         # its own default, not the legacy one
    assert slime["scale"] == petconfig.DEFAULT_SCALE


def test_once_the_new_settings_are_used_the_legacy_keys_stop_applying():
    cfg = petconfig._clean({"palette": "#12A543", "creatures": {"claudlet": {}}})
    assert petconfig.for_creature(cfg, "claudlet")["palette"] == "auto"


def test_a_creature_setting_always_wins():
    cfg = petconfig._clean({"palette": "#4A90D9",
                            "creatures": {"slime": {"palette": "#FF0000"}}})
    assert petconfig.for_creature(cfg, "slime", _Slime)["palette"] == "#FF0000"
