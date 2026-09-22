"""`claudlet-config pointer ...`"""
import io
import json
import os
import contextlib

import pytest

from claudlet.cli import configcli as C
from claudlet.core import petconfig as P


@pytest.fixture(autouse=True)
def _cfg(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    os.makedirs(str(tmp_path / "claudlet"), exist_ok=True)
    return tmp_path


def _run(*argv):
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        code = C.main(["pointer"] + list(argv))
    return code, buf.getvalue()


def _saved():
    return P.load_config()["pointer"]


def test_show_prints_the_defaults():
    code, text = _run()
    assert code == 0
    assert "(inherit)" in text and P.DEFAULT_POINTER_CURSOR in text


def test_setting_the_config_dir_saves_it():
    code, _ = _run("config-dir", "/profiles/dev")
    assert code == 0
    assert _saved()["claude_config_dir"] == "/profiles/dev"


def test_a_tilde_config_dir_is_expanded_on_save():
    _run("config-dir", "~/profiles/dev")
    assert _saved()["claude_config_dir"].startswith(os.path.expanduser("~"))


def test_a_missing_config_dir_is_saved_but_flagged():
    code, text = _run("config-dir", "/definitely/not/here")
    assert code == 0
    assert "does not exist" in text
    assert _saved()["claude_config_dir"] == "/definitely/not/here"


def test_the_config_dir_can_be_cleared():
    _run("config-dir", "/profiles/dev")
    code, text = _run("config-dir", "-")
    assert code == 0 and "cleared" in text
    assert _saved()["claude_config_dir"] is None


def test_setting_a_cursor_saves_it():
    assert _run("cursor", "pointing")[0] == 0
    assert _saved()["cursor"] == "pointing"


def test_an_unknown_cursor_is_refused_with_usage():
    code, text = _run("cursor", "wobble")
    assert code == 2 and "usage" in text


def test_a_cursor_with_no_value_is_refused():
    assert _run("cursor")[0] == 2


def test_setting_an_image_saves_an_absolute_path(_cfg):
    img = _cfg / "cur.png"
    img.write_bytes(b"\x89PNG\r\n\x1a\n")
    assert _run("image", str(img))[0] == 0
    assert _saved()["image"] == os.path.abspath(str(img))


def test_a_hotspot_can_be_given_with_the_image(_cfg):
    img = _cfg / "cur.png"
    img.write_bytes(b"x")
    _run("image", str(img), "--hotspot", "3,4")
    assert _saved()["hotspot"] == [3, 4]


def test_a_malformed_hotspot_is_refused(_cfg):
    img = _cfg / "cur.png"
    img.write_bytes(b"x")
    code, text = _run("image", str(img), "--hotspot", "nonsense")
    assert code == 2 and "X,Y" in text


def test_a_missing_image_file_is_refused():
    code, text = _run("image", "/no/such/file.png")
    assert code == 2 and "no such file" in text


def test_an_unsupported_image_type_is_refused(_cfg):
    bad = _cfg / "cur.exe"
    bad.write_bytes(b"x")
    code, text = _run("image", str(bad))
    assert code == 2 and "unsupported" in text


def test_clearing_the_image_also_clears_the_hotspot(_cfg):
    img = _cfg / "cur.png"
    img.write_bytes(b"x")
    _run("image", str(img), "--hotspot", "1,2")
    _run("image", "-")
    assert _saved()["image"] is None
    assert _saved()["hotspot"] is None


def test_show_warns_when_the_image_went_missing(_cfg):
    img = _cfg / "cur.png"
    img.write_bytes(b"x")
    _run("image", str(img))
    os.unlink(str(img))
    _, text = _run("show")
    assert "not found" in text


def test_settings_do_not_clobber_each_other(_cfg):
    _run("config-dir", "/profiles/dev")
    _run("cursor", "arrow")
    saved = _saved()
    assert saved["claude_config_dir"] == "/profiles/dev"
    assert saved["cursor"] == "arrow"


def test_pointer_settings_leave_other_config_alone():
    P.save_keys({"scale": 7})
    _run("cursor", "arrow")
    assert P.load_config()["scale"] == 7


def test_an_unknown_subcommand_shows_usage():
    code, text = _run("wobble")
    assert code == 2 and "usage" in text


def test_help_exits_cleanly():
    code, text = _run("--help")
    assert code == 0 and "usage" in text
