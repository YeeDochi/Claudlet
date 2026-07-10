import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
from state_engine import StateEngine


def _pre(tool, pm=None):
    ev = {"event": "PreToolUse", "session": "a", "tool_name": tool}
    if pm is not None:
        ev["permission_mode"] = pm
    return ev


def test_auto_mode_shows_autopilot():
    e = StateEngine()
    e.handle(_pre("Edit", pm="auto"), 0.0)
    assert e.display_state(0.0) == "autopilot"


def test_bypass_permissions_shows_autopilot():
    e = StateEngine()
    e.handle(_pre("Bash", pm="bypassPermissions"), 0.0)
    assert e.display_state(0.0) == "autopilot"


def test_default_mode_shows_normal_work():
    e = StateEngine()
    e.handle(_pre("Edit", pm="default"), 0.0)
    assert e.display_state(0.0) == "work_computer"


def test_missing_permission_mode_is_normal_work():
    # older sessions / hook without the field must behave exactly as before
    e = StateEngine()
    e.handle(_pre("Read"), 0.0)
    assert e.display_state(0.0) == "work_search"


def test_auto_mode_keeps_subagent_distinct():
    # spawning a subagent is a milestone worth showing even while autonomous
    e = StateEngine()
    e.handle(_pre("Task", pm="auto"), 0.0)
    assert e.display_state(0.0) == "work_agent"


def test_auto_mode_keeps_skill_distinct():
    e = StateEngine()
    e.handle(_pre("Skill", pm="bypassPermissions"), 0.0)
    assert e.display_state(0.0) == "work_skill"


def test_auto_mode_collapses_routine_tools():
    # routine edit/search/web still collapse to the single autopilot cruise
    e = StateEngine()
    e.handle(_pre("Read", pm="auto"), 0.0)
    assert e.display_state(0.0) == "autopilot"


def test_plan_mode_is_not_autopilot():
    # plan mode is read-only planning, not autonomous grinding
    e = StateEngine()
    e.handle(_pre("Read", pm="plan"), 0.0)
    assert e.display_state(0.0) == "work_search"


def test_autopilot_decays_when_quiet():
    e = StateEngine()
    e.handle(_pre("Edit", pm="auto"), 0.0)
    assert e.display_state(1.0) == "autopilot"
    assert e.display_state(1000.0) in ("idle", "sleeping")


def test_autopilot_is_overridable():
    e = StateEngine(event_states={"autopilot": "sing"})
    e.handle(_pre("Edit", pm="auto"), 0.0)
    assert e.display_state(0.0) == "sing"
