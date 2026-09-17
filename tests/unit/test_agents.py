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


def test_skills_path_is_under_home(tmp_path):
    assert agents.skills_path("claude", home=str(tmp_path)) == \
        os.path.join(str(tmp_path), ".claude", "skills")
    assert agents.skills_path("codex", home=str(tmp_path)) == \
        os.path.join(str(tmp_path), ".codex", "skills")


def test_every_agent_declares_the_full_shape():
    keys = {"label", "marker", "settings", "skills", "proc", "events",
            "tool_events", "avatar", "tools", "raw_events"}
    for name, a in agents.AGENTS.items():
        assert keys <= set(a), name
        assert a["events"], name
        # tool_events must be a subset of the events we actually register
        assert set(a["tool_events"]) <= set(a["events"]), name


def test_codex_event_set_matches_what_codex_supports():
    # Measured from the codex 0.147.0 binary + its own hooks.json plugin
    # (SessionEnd is registered there). No Notification, no StopFailure.
    ev = agents.AGENTS["codex"]["events"]
    for present in ("SessionStart", "SessionEnd", "UserPromptSubmit",
                    "PreToolUse", "PostToolUse", "PermissionRequest",
                    "Stop", "SubagentStop"):
        assert present in ev, present
    # SubagentStart and PreCompact are deliberately left out: neither reaches
    # any branch in state_engine.handle, so registering them would only spawn
    # a Python process per event for nothing.
    for missing in ("Notification", "StopFailure", "SubagentStart", "PreCompact"):
        assert missing not in ev, missing
    assert agents.AGENTS["codex"]["raw_events"]["PermissionRequest"] == "attention"
