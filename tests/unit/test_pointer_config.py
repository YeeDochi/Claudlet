"""Pointer settings: CLAUDE_CONFIG_DIR and the cursor image."""
import json
import os

import pytest

from claudlet.core import petconfig as P
from claudlet.core import session_launch as S


@pytest.fixture(autouse=True)
def _cfg(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    os.makedirs(str(tmp_path / "claudlet"), exist_ok=True)
    return tmp_path


def _write(pointer):
    with open(P.config_path(), "w", encoding="utf-8") as f:
        json.dump({"pointer": pointer}, f)


# ---- validation ----

def test_defaults_apply_with_no_config():
    assert P.load_config()["pointer"]["cursor"] == P.DEFAULT_POINTER_CURSOR


def test_defaults_apply_with_no_pointer_section():
    with open(P.config_path(), "w", encoding="utf-8") as f:
        json.dump({"scale": 5}, f)
    assert P.load_config()["pointer"] == P._clean_pointer(None)


def test_a_config_dir_is_kept():
    _write({"claude_config_dir": "/profiles/dev"})
    assert P.load_config()["pointer"]["claude_config_dir"] == "/profiles/dev"


def test_a_tilde_in_the_config_dir_is_expanded():
    _write({"claude_config_dir": "~/profiles/dev"})
    got = P.load_config()["pointer"]["claude_config_dir"]
    assert got.startswith(os.path.expanduser("~"))


def test_a_config_dir_that_does_not_exist_is_still_kept():
    """They may be pointing at a profile they are about to create."""
    _write({"claude_config_dir": "/definitely/not/here"})
    assert P.load_config()["pointer"]["claude_config_dir"] == "/definitely/not/here"


def test_a_blank_config_dir_is_dropped():
    _write({"claude_config_dir": "   "})
    assert P.load_config()["pointer"]["claude_config_dir"] is None


@pytest.mark.parametrize("name", P.POINTER_CURSORS)
def test_every_offered_cursor_is_accepted(name):
    _write({"cursor": name})
    assert P.load_config()["pointer"]["cursor"] == name


def test_an_unknown_cursor_falls_back():
    _write({"cursor": "wobble"})
    assert P.load_config()["pointer"]["cursor"] == P.DEFAULT_POINTER_CURSOR


def test_an_image_path_is_kept():
    _write({"image": "/tmp/cur.png"})
    assert P.load_config()["pointer"]["image"] == "/tmp/cur.png"


def test_an_unsupported_image_type_is_dropped():
    _write({"image": "/tmp/cur.exe"})
    assert P.load_config()["pointer"]["image"] is None


def test_a_hotspot_is_kept():
    _write({"hotspot": [3, 4]})
    assert P.load_config()["pointer"]["hotspot"] == [3, 4]


def test_a_malformed_hotspot_is_dropped():
    _write({"hotspot": ["a", "b"]})
    assert P.load_config()["pointer"]["hotspot"] is None


def test_a_short_hotspot_is_dropped():
    _write({"hotspot": [3]})
    assert P.load_config()["pointer"]["hotspot"] is None


def test_a_junk_pointer_section_does_not_break_the_config():
    _write("not a dict")
    assert P.load_config()["pointer"] == P._clean_pointer(None)


# ---- the config dir reaches the launched session ----

def test_the_config_dir_is_prefixed_to_the_command():
    cmd = S.build_command("sid", "/tmp", config_dir="/profiles/dev")
    assert "CLAUDE_CONFIG_DIR='/profiles/dev'" in cmd


def test_the_config_dir_comes_before_the_binary():
    """An env prefix after the command name would be an argument, not a setting."""
    cmd = S.build_command("sid", "/tmp", config_dir="/profiles/dev")
    assert cmd.index("CLAUDE_CONFIG_DIR") < cmd.index("'claude'")


def test_no_prefix_without_a_config_dir():
    assert "CLAUDE_CONFIG_DIR" not in S.build_command("sid", "/tmp")


def test_a_config_dir_with_spaces_stays_one_value():
    cmd = S.build_command("sid", None, config_dir="/my profiles/dev")
    assert "CLAUDE_CONFIG_DIR='/my profiles/dev'" in cmd


def test_the_helper_reads_it_from_config():
    _write({"claude_config_dir": "/profiles/dev"})
    assert P.pointer_config_dir() == "/profiles/dev"


def test_the_helper_is_none_when_unset():
    assert P.pointer_config_dir() is None
