import sys, os, json, types

HOOK = os.path.join(os.path.dirname(__file__), "..", "bin", "claude-pet-hook")
mod = types.ModuleType("claude_pet_hook")
mod.__file__ = HOOK
with open(HOOK) as f:
    exec(compile(f.read(), HOOK, "exec"), mod.__dict__)


def test_pretooluse_forwards_tool_name():
    msg = json.loads(mod.build_message(
        ["claude-pet-hook", "PreToolUse"],
        {"session_id": "s1", "tool_name": "Edit", "tool_input": {}}))
    assert msg["event"] == "PreToolUse"
    assert msg["session"] == "s1"
    assert msg["tool_name"] == "Edit"


def test_forwards_permission_mode():
    msg = json.loads(mod.build_message(
        ["claude-pet-hook", "PreToolUse"],
        {"session_id": "s1", "tool_name": "Edit", "permission_mode": "auto"}))
    assert msg["permission_mode"] == "auto"


def test_notification_forwards_type():
    msg = json.loads(mod.build_message(
        ["claude-pet-hook", "Notification"],
        {"session_id": "s1", "notification_type": "permission_prompt"}))
    assert msg["notification_type"] == "permission_prompt"


def test_missing_fields_omitted():
    msg = json.loads(mod.build_message(["claude-pet-hook", "Stop"], {"session_id": "s1"}))
    assert msg["event"] == "Stop"
    assert "tool_name" not in msg


def test_sock_for_uses_session(monkeypatch):
    monkeypatch.setenv("XDG_RUNTIME_DIR", "/run/user/1000")
    assert mod.sock_for({"session_id": "xyz"}) == "/run/user/1000/claude-pet-xyz.sock"
    assert mod.sock_for({}) == "/run/user/1000/claude-pet-default.sock"
