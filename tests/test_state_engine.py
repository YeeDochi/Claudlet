import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
from claudlet.state_engine import tool_to_state, StateEngine


def test_tool_states_override():
    e = StateEngine(tool_states={"Bash": "work_search", "Grep": "sing", "*": "thinking"})
    e.handle({"event": "PreToolUse", "session": "a", "tool_name": "Bash"}, 0.0)
    assert e.display_state(0.0) == "work_search"           # remapped tool
    e2 = StateEngine(tool_states={"Grep": "sing"})
    e2.handle({"event": "PreToolUse", "session": "a", "tool_name": "Grep"}, 0.0)
    assert e2.display_state(0.0) == "sing"                 # mapped to a fun motion
    e3 = StateEngine(tool_states={"*": "thinking"})
    e3.handle({"event": "PreToolUse", "session": "a", "tool_name": "Unheard"}, 0.0)
    assert e3.display_state(0.0) == "thinking"             # "*" fallback


def test_event_states_override():
    e = StateEngine(event_states={"prompt": "juggle"})
    e.handle({"event": "UserPromptSubmit", "session": "a"}, 0.0)
    assert e.display_state(0.0) == "juggle"


def test_raw_event_mapping_for_unhandled_events():
    # an event without a dedicated slot (PostToolUse) is mappable by raw name
    e = StateEngine(raw_events={"PostToolUse": "wave"})
    e.handle({"event": "PostToolUse", "session": "a", "tool_name": "Edit"}, 0.0)
    assert e.display_state(0.0) == "wave"


def test_raw_event_does_not_override_handled_slots():
    # a handled event (UserPromptSubmit) keeps its slot behaviour even if also
    # named in raw_events — the specific branch wins
    e = StateEngine(raw_events={"UserPromptSubmit": "sing"})
    e.handle({"event": "UserPromptSubmit", "session": "a"}, 0.0)
    assert e.display_state(0.0) == "thinking"


def test_custom_target_gets_work_priority_and_decays():
    # a custom tool state must win over idle (priority) and still time out so it
    # doesn't stick forever with no further events
    e = StateEngine(tool_states={"Grep": "sing"})
    e.handle({"event": "PreToolUse", "session": "a", "tool_name": "Grep"}, 0.0)
    assert e.display_state(1.0) == "sing"
    # WORK_TIMEOUT decay (then straight to sleeping, since it's also past SLEEP)
    assert e.display_state(1000.0) in ("idle", "sleeping")


def test_tool_to_state_known_and_fallback():
    assert tool_to_state("Edit") == "work_computer"
    assert tool_to_state("Bash") == "work_computer"
    assert tool_to_state("Read") == "work_search"
    assert tool_to_state("Grep") == "work_search"
    assert tool_to_state("WebFetch") == "work_web"
    assert tool_to_state("Skill") == "work_skill"
    assert tool_to_state("mcp__gitlab__get_project") == "work_web"
    assert tool_to_state("SomethingNew") == "work_computer"   # fallback


def test_pretooluse_sets_work_state():
    e = StateEngine()
    e.handle({"event": "PreToolUse", "session": "a", "tool_name": "Edit"}, now=0.0)
    assert e.display_state(now=0.0) == "work_computer"


def test_agent_dispatch_does_not_change_main_state():
    # subagent dispatch (PreToolUse tool_name "Agent") is companion-only: it must
    # NOT turn the main creature into an agent state — it just opens the counter,
    # leaving the main state as-is (here: still idle) so the main pet keeps
    # reflecting the parent's own activity.
    e = StateEngine()
    e.handle({"event": "PreToolUse", "session": "a", "tool_name": "Agent"}, now=0.0)
    assert e.display_state(now=0.0) == "idle"
    assert e.agents_active() == 1


def _ev(name, sid="a", **kw):
    d = {"event": name, "session": sid}
    d.update(kw)
    return d


def test_agents_active_counts_open_window():
    e = StateEngine()
    assert e.agents_active() == 0
    e.handle(_ev("PreToolUse", tool_name="Agent"), now=0.0)
    assert e.agents_active() == 1
    e.handle(_ev("SubagentStop"), now=1.0)
    assert e.agents_active() == 0


def test_agents_active_persists_across_other_motions():
    # THE point: a companion must stay up while the main creature shows other
    # work (background/parallel agent) — agents_active independent of display.
    e = StateEngine()
    e.handle(_ev("PreToolUse", tool_name="Agent"), now=0.0)
    e.handle(_ev("PreToolUse", tool_name="Read"), now=1.0)   # parent keeps working
    assert e.display_state(now=1.0) == "work_search"         # main moved on
    assert e.agents_active() == 1                            # companion stays


def test_agents_active_parallel_and_floor():
    e = StateEngine()
    e.handle(_ev("PreToolUse", tool_name="Agent"), now=0.0)
    e.handle(_ev("PreToolUse", tool_name="Task"), now=0.1)   # alias also counts
    assert e.agents_active() == 2
    e.handle(_ev("SubagentStop"), now=1.0)
    assert e.agents_active() == 1
    e.handle(_ev("SubagentStop"), now=1.1)
    assert e.agents_active() == 0
    e.handle(_ev("SubagentStop"), now=1.2)                   # extra -> floor at 0
    assert e.agents_active() == 0


def test_agents_survive_turn_boundaries():
    # BACKGROUND subagents outlive the turn: the user chats (UserPromptSubmit)
    # and the main turn ends (Stop) while they still run — the companion must
    # NOT vanish then. Only their real SubagentStop closes the window.
    e = StateEngine()
    e.handle(_ev("PreToolUse", tool_name="Agent"), now=0.0)
    e.handle(_ev("Stop"), now=1.0)
    assert e.agents_active() == 1
    e.handle(_ev("UserPromptSubmit"), now=2.0)
    assert e.agents_active() == 1
    e.handle(_ev("SubagentStop"), now=3.0)
    assert e.agents_active() == 0


def test_agents_reset_on_session_boundaries():
    e = StateEngine()
    e.handle(_ev("PreToolUse", tool_name="Agent"), now=0.0)
    e.handle(_ev("SessionStart"), now=1.0)     # fresh session -> nothing carried
    assert e.agents_active() == 0


def test_agent_state_mirrors_subagent_tools_during_window():
    # the subagent's own tool events arrive on this session between PreToolUse
    # (Agent) and SubagentStop; the companion mirrors them via agent_state.
    e = StateEngine()
    e.handle(_ev("PreToolUse", tool_name="Agent"), now=0.0)
    assert e.agent_state() == "thinking"          # spinning up
    e.handle(_ev("PreToolUse", tool_name="Bash"), now=0.1)
    assert e.agent_state() == "work_computer"     # subagent is coding
    e.handle(_ev("PreToolUse", tool_name="Read"), now=0.2)
    assert e.agent_state() == "work_search"       # ...now reading
    e.handle(_ev("SubagentStop"), now=0.3)
    assert e.agent_state() is None                # window closed


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


def test_stop_focused_goes_idle_not_celebrate():
    e = StateEngine(is_focused=lambda: True)
    e.handle({"event": "Stop", "session": "a"}, now=0.0)
    assert e.display_state(now=0.0) == "idle"


def test_stop_unfocused_celebrates_then_decays_to_idle():
    e = StateEngine(is_focused=lambda: False)
    e.handle({"event": "Stop", "session": "a"}, now=0.0)
    assert e.display_state(now=0.5) == "celebrate"
    assert e.display_state(now=1.7) == "idle"      # after CELEBRATE_DUR (1.6s)


def test_idle_sleeps_after_timeout():
    e = StateEngine(is_focused=lambda: True)
    e.handle({"event": "Stop", "session": "a"}, now=0.0)      # -> idle
    assert e.display_state(now=10.0) == "idle"
    assert e.display_state(now=61.0) == "sleeping"            # 60s quiet


def test_idle_prompt_sleeps_immediately():
    e = StateEngine()
    e.handle({"event": "Notification", "session": "a",
              "notification_type": "idle_prompt"}, now=0.0)
    assert e.display_state(now=0.1) == "sleeping"


def test_stopfailure_errors_then_decays():
    e = StateEngine()
    e.handle({"event": "StopFailure", "session": "a"}, now=0.0)
    assert e.display_state(now=1.0) == "error"
    assert e.display_state(now=2.1) == "idle"                 # after ERROR_DUR (2.0s)


def test_userpromptsubmit_thinks_then_works():
    e = StateEngine()
    e.handle({"event": "UserPromptSubmit", "session": "a"}, now=0.0)
    assert e.display_state(now=0.0) == "thinking"
    e.handle({"event": "PreToolUse", "session": "a", "tool_name": "Read"}, now=0.5)
    assert e.display_state(now=0.5) == "work_search"


def test_sessionend_drops_session():
    e = StateEngine()
    e.handle({"event": "PreToolUse", "session": "a", "tool_name": "Edit"}, now=0.0)
    e.handle({"event": "SessionEnd", "session": "a"}, now=0.1)
    assert e.display_state(now=0.1) == "sleeping"


def test_work_state_times_out_when_no_stop_fires():
    # user interrupts (ESC) mid-Bash: no Stop, no further events
    e = StateEngine()
    e.handle({"event": "PreToolUse", "session": "a", "tool_name": "Bash"}, now=0.0)
    assert e.display_state(now=10.0) == "work_computer"
    # after WORK_TIMEOUT of silence it falls back and (being long-quiet) sleeps
    assert e.display_state(now=121.0) == "sleeping"


def test_thinking_times_out_when_no_stop_fires():
    e = StateEngine()
    e.handle({"event": "UserPromptSubmit", "session": "a"}, now=0.0)
    assert e.display_state(now=10.0) == "thinking"
    assert e.display_state(now=121.0) == "sleeping"
