import json
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
