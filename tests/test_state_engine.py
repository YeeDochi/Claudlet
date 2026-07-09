import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
from state_engine import tool_to_state, StateEngine


def test_tool_to_state_known_and_fallback():
    assert tool_to_state("Edit") == "work_computer"
    assert tool_to_state("Bash") == "work_computer"
    assert tool_to_state("Read") == "work_search"
    assert tool_to_state("Grep") == "work_search"
    assert tool_to_state("WebFetch") == "work_web"
    assert tool_to_state("Task") == "work_agent"
    assert tool_to_state("Skill") == "work_skill"
    assert tool_to_state("mcp__gitlab__get_project") == "work_web"
    assert tool_to_state("SomethingNew") == "work_computer"   # fallback


def test_pretooluse_sets_work_state():
    e = StateEngine()
    e.handle({"event": "PreToolUse", "session": "a", "tool_name": "Edit"}, now=0.0)
    assert e.display_state(now=0.0) == "work_computer"


def test_no_sessions_is_sleeping():
    e = StateEngine()
    assert e.display_state(now=0.0) == "sleeping"


def test_priority_picks_attention_over_work():
    e = StateEngine()
    e.handle({"event": "PreToolUse", "session": "a", "tool_name": "Edit"}, now=0.0)
    e.handle({"event": "Notification", "session": "b",
              "notification_type": "permission_prompt"}, now=0.0)
    assert e.display_state(now=0.0) == "attention"


def test_debounce_holds_fast_tool_switch():
    e = StateEngine()
    # a fast Read then an immediate Edit within the debounce window
    e.handle({"event": "PreToolUse", "session": "a", "tool_name": "Read"}, now=0.0)
    e.handle({"event": "PreToolUse", "session": "a", "tool_name": "Edit"}, now=0.2)
    # still inside 0.8s hold -> the search motion is still what shows
    assert e.display_state(now=0.3) == "work_search"
    # after the hold expires, the pending Edit is promoted
    assert e.display_state(now=0.9) == "work_computer"


def test_same_tool_repeats_do_not_reset_forever():
    e = StateEngine()
    e.handle({"event": "PreToolUse", "session": "a", "tool_name": "Read"}, now=0.0)
    e.handle({"event": "PreToolUse", "session": "a", "tool_name": "Grep"}, now=0.1)
    # Grep is also work_search — no visible change, no pending needed
    assert e.display_state(now=0.2) == "work_search"
    assert e.display_state(now=1.0) == "work_search"
