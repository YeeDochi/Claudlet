import sys, os, json, types

HOOK = os.path.join(os.path.dirname(__file__), "..", "bin", "claude-pet-hook")

# Load the script without .py extension using exec
with open(HOOK) as f:
    code = f.read()
mod = types.ModuleType("claude_pet_hook")
exec(code, mod.__dict__)


def test_pretooluse_forwards_tool_name():
    msg = json.loads(mod.build_message(
        ["claude-pet-hook", "PreToolUse"],
        {"session_id": "s1", "tool_name": "Edit", "tool_input": {}}))
    assert msg["event"] == "PreToolUse"
    assert msg["session"] == "s1"
    assert msg["tool_name"] == "Edit"


def test_notification_forwards_type():
    msg = json.loads(mod.build_message(
        ["claude-pet-hook", "Notification"],
        {"session_id": "s1", "notification_type": "permission_prompt"}))
    assert msg["notification_type"] == "permission_prompt"


def test_missing_fields_omitted():
    msg = json.loads(mod.build_message(["claude-pet-hook", "Stop"],
                                       {"session_id": "s1"}))
    assert msg["event"] == "Stop"
    assert "tool_name" not in msg
