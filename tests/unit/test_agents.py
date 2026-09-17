import os
from claudlet.core import agents


def test_get_falls_back_to_claude():
    assert agents.get("nope") is agents.AGENTS["claude"]
    assert agents.get(None) is agents.AGENTS["claude"]
    assert agents.get("codex") is agents.AGENTS["codex"]


def test_detected_follows_marker_dirs(tmp_path):
    os.mkdir(tmp_path / ".codex")
    assert agents.detected(home=str(tmp_path)) == ["codex"]
    os.mkdir(tmp_path / ".claude")
    # registry order, not filesystem order
    assert agents.detected(home=str(tmp_path)) == ["claude", "codex"]


def test_detected_empty_when_nothing_installed(tmp_path):
    assert agents.detected(home=str(tmp_path)) == []


def test_settings_path_is_under_home(tmp_path):
    p = agents.settings_path("codex", home=str(tmp_path))
    assert p == os.path.join(str(tmp_path), ".codex", "hooks.json")


def test_every_agent_declares_the_full_shape():
    keys = {"label", "marker", "settings", "proc", "events", "tool_events",
            "avatar", "tools", "raw_events"}
    for name, a in agents.AGENTS.items():
        assert keys <= set(a), name
        assert a["events"], name
        # tool_events must be a subset of the events we actually register
        assert set(a["tool_events"]) <= set(a["events"]), name


def test_codex_event_set_matches_what_codex_supports():
    ev = agents.AGENTS["codex"]["events"]
    assert "PermissionRequest" in ev
    # Codex has no SessionEnd / Notification / SubagentStop
    for missing in ("SessionEnd", "Notification", "SubagentStop"):
        assert missing not in ev
    assert agents.AGENTS["codex"]["raw_events"]["PermissionRequest"] == "attention"
