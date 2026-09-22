from claudlet.core.state_engine import StateEngine


def _pre(tool, pm=None):
    ev = {"event": "PreToolUse", "session": "a", "tool_name": tool}
    if pm is not None:
        ev["permission_mode"] = pm
    return ev


# --- running unattended is a FLAG, not a different state ---
#
# Auto mode used to fork every work state into an auto_* twin that differed only
# in wearing a visor. That was the engine deciding how the creature LOOKS, which
# belongs to the creature now: the mode is reported and each creature shows it
# however it likes, or not at all.

def test_auto_mode_does_not_change_the_state():
    for tool, expected in (("Edit", "work_computer"), ("Grep", "work_search"),
                           ("WebFetch", "work_web"), ("Skill", "work_skill")):
        plain, auto = StateEngine(), StateEngine()
        plain.handle(_pre(tool), 0.0)
        auto.handle(_pre(tool, pm="auto"), 0.0)
        assert auto.display_state(0.0) == plain.display_state(0.0) == expected


def test_auto_mode_is_reported_alongside_the_state():
    # what the creature needs in order to show it: the state AND the flag
    e = StateEngine()
    e.handle(_pre("Edit", pm="auto"), 0.0)
    assert e.display_state(0.0) == "work_computer"
    assert e.auto_active() is True


def test_an_unmapped_tool_in_auto_is_ordinary_work():
    # it used to fall back to a generic "autopilot" state; there is no such
    # fork any more, so it is simply the work state it always was
    e = StateEngine()
    e.handle(_pre("SomeUnknownTool", pm="auto"), 0.0)
    assert e.display_state(0.0) == "work_computer"
    assert e.auto_active() is True


def test_work_decays_the_same_whether_or_not_auto():
    e = StateEngine()
    e.handle(_pre("Edit", pm="auto"), 0.0)
    assert e.display_state(1.0) == "work_computer"
    assert e.display_state(2000.0) in ("idle", "sleeping")


def test_agent_dispatch_is_companion_only_even_in_auto():
    # subagent dispatch is represented by the follower companion, not a main
    # state — so even in auto mode it does NOT become auto_agent; the main
    # creature is left as-is (idle here) and only the agent counter opens.
    e = StateEngine()
    e.handle(_pre("Task", pm="auto"), 0.0)
    assert e.display_state(0.0) == "idle"
    assert e.agents_active() == 1


# --- non-auto modes behave exactly as before (no regression) ---

def test_default_mode_shows_normal_work():
    e = StateEngine()
    e.handle(_pre("Edit", pm="default"), 0.0)
    assert e.display_state(0.0) == "work_computer"


def test_missing_permission_mode_is_normal_work():
    e = StateEngine()
    e.handle(_pre("Read"), 0.0)
    assert e.display_state(0.0) == "work_search"


def test_plan_mode_is_not_auto_variant():
    e = StateEngine()
    e.handle(_pre("Read", pm="plan"), 0.0)
    assert e.display_state(0.0) == "work_search"


# --- fallbacks & lifecycle ---

def test_a_custom_mapped_tool_keeps_its_mapping_in_auto():
    # a tool the user pointed at a motion still shows that motion; auto mode no
    # longer overrides it with a state of its own
    e = StateEngine(tool_states={"Grep": "sing"})
    e.handle(_pre("Grep", pm="auto"), 0.0)
    assert e.display_state(0.0) == "sing"
    assert e.auto_active() is True


def test_auto_active_true_in_auto_mode():
    e = StateEngine()
    e.handle(_pre("Edit", pm="auto"), 0.0)
    assert e.auto_active() is True


def test_auto_active_false_in_default_mode():
    e = StateEngine()
    e.handle(_pre("Edit", pm="default"), 0.0)
    assert e.auto_active() is False


def test_auto_active_persists_through_events_without_pm():
    # an idle/Stop tick may omit pm; the remembered mode carries the visor over
    e = StateEngine()
    e.handle(_pre("Edit", pm="auto"), 0.0)
    e.handle({"event": "Stop", "session": "a"}, 1.0)   # no permission_mode
    assert e.auto_active() is True


def test_auto_active_cleared_on_session_end():
    e = StateEngine()
    e.handle(_pre("Edit", pm="auto"), 0.0)
    e.handle({"event": "SessionEnd", "session": "a"}, 1.0)
    assert e.auto_active() is False
