import json
import os
import pytest
from claudlet.cli import install_hooks as ih


def _settings_with_our_hook(path):
    path.write_text(json.dumps({"hooks": {
        "Stop": [{"hooks": [{"type": "command", "command": "claudlet-hook Stop"}]}]
    }}))


def test_main_accepts_argv_remove(tmp_path):
    # main() must honor an explicit argv (so uninstall can call
    # main(["--remove"])) instead of only ever reading sys.argv — under pytest
    # sys.argv has no "--remove", so a sys.argv-only main would re-INSTALL here.
    home = tmp_path
    os.makedirs(home / ".claude", exist_ok=True)
    _settings_with_our_hook(home / ".claude" / "settings.json")

    ih.main(["--remove"], home=str(home))

    data = json.loads((home / ".claude" / "settings.json").read_text())
    assert "hooks" not in data          # our only hook group was removed


def test_main_argv_none_defaults_to_sys_argv(tmp_path, monkeypatch):
    # back-compat: no argv -> read sys.argv (install path, no --remove present)
    home = tmp_path
    os.makedirs(home / ".claude", exist_ok=True)
    monkeypatch.setattr(ih.sys, "argv", ["claudlet-install-hooks"])

    ih.main(home=str(home))

    data = json.loads((home / ".claude" / "settings.json").read_text())
    assert "hooks" in data and "Stop" in data["hooks"]


def test_save_preserves_original_when_write_fails(tmp_path):
    # If serialization dies mid-save, the live settings.json must still be the
    # ORIGINAL, not gone (the old rename-then-write left nothing behind).
    settings = tmp_path / "settings.json"
    settings.write_text(json.dumps({"keep": "me"}))

    class Unserializable:
        pass

    with pytest.raises(TypeError):
        ih.save(str(settings), {"bad": Unserializable()})       # json.dump raises

    assert json.loads(settings.read_text()) == {"keep": "me"}   # intact
    # and no leftover temp file in the directory
    assert not [p for p in tmp_path.iterdir() if p.name.startswith(".settings.")]


def test_save_keeps_single_rolling_backup(tmp_path):
    settings = tmp_path / "settings.json"
    settings.write_text(json.dumps({"v": 1}))

    ih.save(str(settings), {"v": 2})
    ih.save(str(settings), {"v": 3})

    baks = [p.name for p in tmp_path.iterdir() if ".bak" in p.name]
    assert baks == ["settings.json.bak"]         # exactly one, not timestamped
    assert json.loads(settings.read_text()) == {"v": 3}
    assert json.loads((tmp_path / "settings.json.bak").read_text()) == {"v": 2}


def test_load_bails_on_corrupt_settings(tmp_path):
    settings = tmp_path / "settings.json"
    settings.write_text("{ this is not json")

    with pytest.raises(SystemExit):
        ih.load(str(settings))

    # the corrupt file is left untouched for the user to recover
    assert settings.read_text() == "{ this is not json"


def _home_with(tmp_path, *agents_):
    for a in agents_:
        os.makedirs(tmp_path / ("." + a), exist_ok=True)
    return str(tmp_path)


def test_targets_defaults_to_every_detected_agent(tmp_path):
    home = _home_with(tmp_path, "claude", "codex")
    assert ih.targets([], home=home) == ["claude", "codex"]


def test_targets_honours_explicit_agent_flag(tmp_path):
    home = _home_with(tmp_path, "claude", "codex")
    assert ih.targets(["--agent", "codex"], home=home) == ["codex"]
    assert ih.targets(["--agent", "claude,codex"], home=home) == ["claude", "codex"]
    # an explicit agent is installed even if the marker dir is absent: the user
    # asked for it by name
    assert ih.targets(["--agent", "codex"], home=str(tmp_path / "empty")) == ["codex"]


def test_targets_drops_unknown_names(tmp_path):
    home = _home_with(tmp_path, "claude")
    assert ih.targets(["--agent", "gemini"], home=home) == []


def test_install_writes_each_agents_own_events(tmp_path):
    home = _home_with(tmp_path, "claude", "codex")
    ih.main([], home=home)

    claude = json.loads((tmp_path / ".claude" / "settings.json").read_text())
    codex = json.loads((tmp_path / ".codex" / "hooks.json").read_text())
    # each agent gets ITS OWN event vocabulary, not one shared list: Claude
    # Code has Notification/StopFailure, Codex has PermissionRequest instead.
    assert "Notification" in claude["hooks"]
    assert "PermissionRequest" not in claude["hooks"]
    assert "Notification" not in codex["hooks"]
    assert "PermissionRequest" in codex["hooks"]
    # the agent travels in the command so the hook knows who it serves
    cmd = codex["hooks"]["Stop"][0]["hooks"][0]["command"]
    assert cmd.endswith("Stop --agent codex")
    assert codex["hooks"]["PreToolUse"][0]["matcher"] == "*"


def test_install_is_idempotent_and_preserves_other_apps_hooks(tmp_path):
    home = _home_with(tmp_path, "codex")
    hooks = tmp_path / ".codex" / "hooks.json"
    theirs = {"type": "command", "command": "/usr/local/bin/node /opt/other/hook.js"}
    hooks.write_text(json.dumps({"hooks": {"Stop": [{"hooks": [theirs]}]}}))

    ih.main([], home=home)
    ih.main([], home=home)                      # twice: must not double-register

    groups = json.loads(hooks.read_text())["hooks"]["Stop"]
    assert sum(1 for g in groups if ih.is_ours(g)) == 1
    assert any(g["hooks"][0]["command"].endswith("other/hook.js") for g in groups)


def test_remove_only_touches_the_named_agent(tmp_path):
    home = _home_with(tmp_path, "claude", "codex")
    ih.main([], home=home)
    ih.main(["--remove", "--agent", "codex"], home=home)

    claude = json.loads((tmp_path / ".claude" / "settings.json").read_text())
    codex = json.loads((tmp_path / ".codex" / "hooks.json").read_text())
    assert "hooks" in claude
    assert "hooks" not in codex


def test_install_with_nothing_detected_writes_nothing(tmp_path, capsys):
    home = str(tmp_path)
    ih.main([], home=home)
    assert not list(tmp_path.iterdir())
    assert "no agent" in capsys.readouterr().out.lower()
