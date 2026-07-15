import json
import pytest
from claudlet.cli import install_hooks as ih


def _settings_with_our_hook(path):
    path.write_text(json.dumps({"hooks": {
        "Stop": [{"hooks": [{"type": "command", "command": "claudlet-hook Stop"}]}]
    }}))


def test_main_accepts_argv_remove(tmp_path, monkeypatch):
    # main() must honor an explicit argv (so uninstall can call
    # main(["--remove"])) instead of only ever reading sys.argv — under pytest
    # sys.argv has no "--remove", so a sys.argv-only main would re-INSTALL here.
    settings = tmp_path / "settings.json"
    _settings_with_our_hook(settings)
    monkeypatch.setattr(ih, "SETTINGS", str(settings))

    ih.main(["--remove"])

    data = json.loads(settings.read_text())
    assert "hooks" not in data          # our only hook group was removed


def test_main_argv_none_defaults_to_sys_argv(tmp_path, monkeypatch):
    # back-compat: no argv -> read sys.argv (install path, no --remove present)
    settings = tmp_path / "settings.json"
    monkeypatch.setattr(ih, "SETTINGS", str(settings))
    monkeypatch.setattr(ih.sys, "argv", ["claudlet-install-hooks"])

    ih.main()

    data = json.loads(settings.read_text())
    assert "hooks" in data and "Stop" in data["hooks"]


def test_save_preserves_original_when_write_fails(tmp_path, monkeypatch):
    # If serialization dies mid-save, the live settings.json must still be the
    # ORIGINAL, not gone (the old rename-then-write left nothing behind).
    settings = tmp_path / "settings.json"
    settings.write_text(json.dumps({"keep": "me"}))
    monkeypatch.setattr(ih, "SETTINGS", str(settings))

    class Unserializable:
        pass

    with pytest.raises(TypeError):
        ih.save({"bad": Unserializable()})       # json.dump raises

    assert json.loads(settings.read_text()) == {"keep": "me"}   # intact
    # and no leftover temp file in the directory
    assert not [p for p in tmp_path.iterdir() if p.name.startswith(".settings.")]


def test_save_keeps_single_rolling_backup(tmp_path, monkeypatch):
    settings = tmp_path / "settings.json"
    settings.write_text(json.dumps({"v": 1}))
    monkeypatch.setattr(ih, "SETTINGS", str(settings))

    ih.save({"v": 2})
    ih.save({"v": 3})

    baks = [p.name for p in tmp_path.iterdir() if ".bak" in p.name]
    assert baks == ["settings.json.bak"]         # exactly one, not timestamped
    assert json.loads(settings.read_text()) == {"v": 3}
    assert json.loads((tmp_path / "settings.json.bak").read_text()) == {"v": 2}


def test_load_bails_on_corrupt_settings(tmp_path, monkeypatch):
    settings = tmp_path / "settings.json"
    settings.write_text("{ this is not json")
    monkeypatch.setattr(ih, "SETTINGS", str(settings))

    with pytest.raises(SystemExit):
        ih.load()

    # the corrupt file is left untouched for the user to recover
    assert settings.read_text() == "{ this is not json"
