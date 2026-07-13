import sys, os, io, json
from claudlet import hook as mod


def test_pretooluse_forwards_tool_name():
    msg = json.loads(mod.build_message(
        ["claudlet-hook", "PreToolUse"],
        {"session_id": "s1", "tool_name": "Edit", "tool_input": {}}))
    assert msg["event"] == "PreToolUse"
    assert msg["session"] == "s1"
    assert msg["tool_name"] == "Edit"


def test_forwards_permission_mode():
    msg = json.loads(mod.build_message(
        ["claudlet-hook", "PreToolUse"],
        {"session_id": "s1", "tool_name": "Edit", "permission_mode": "auto"}))
    assert msg["permission_mode"] == "auto"


def test_notification_forwards_type():
    msg = json.loads(mod.build_message(
        ["claudlet-hook", "Notification"],
        {"session_id": "s1", "notification_type": "permission_prompt"}))
    assert msg["notification_type"] == "permission_prompt"


def test_missing_fields_omitted():
    msg = json.loads(mod.build_message(["claudlet-hook", "Stop"], {"session_id": "s1"}))
    assert msg["event"] == "Stop"
    assert "tool_name" not in msg


def test_sock_for_uses_session(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path))
    assert mod.sock_for({"session_id": "xyz"}) is None       # no pet running yet
    (tmp_path / "claudlet-xyz.port").write_text("54321")
    assert mod.sock_for({"session_id": "xyz"}) == 54321
    assert mod.sock_for({}) is None


def _run_main(monkeypatch, session_id, pet_alive_result, launch_calls, sent):
    monkeypatch.setattr(mod.hostinfo, "pet_alive", lambda sid: pet_alive_result)
    monkeypatch.setattr(mod, "_launch_pet",
                         lambda *a, **k: launch_calls.append((a, k)))
    monkeypatch.setattr(mod, "_send",
                         lambda port, payload: sent.append((port, payload)))
    monkeypatch.setattr(mod.sys, "argv", ["claudlet-hook", "SessionStart"])
    monkeypatch.setattr(mod.sys, "stdin", io.StringIO(json.dumps(
        {"session_id": session_id, "hook_event_name": "SessionStart"})))
    mod.main()


def test_session_start_still_sends_when_resumed_pet_times_out(tmp_path, monkeypatch):
    # A resumed session (its .port file already exists) where pet_alive()
    # returns False from a transient timeout -- not a proven-dead port --
    # must NOT have the triggering SessionStart event dropped: it might be
    # our own pet, alive, just briefly slow to answer the liveness ping.
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path))
    (tmp_path / "claudlet-resumed.port").write_text("54321")
    launch_calls, sent = [], []
    _run_main(monkeypatch, "resumed", False, launch_calls, sent)
    assert len(launch_calls) == 1          # still attempts a launch (harmless if live)
    assert len(sent) == 1                  # but the event is NOT dropped
    assert sent[0][0] == 54321


def test_session_start_skips_send_for_brand_new_session(tmp_path, monkeypatch):
    # No port file ever existed for this session_id -- there is provably
    # nothing to send to yet, so skipping the send here is still correct.
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path))
    launch_calls, sent = [], []
    _run_main(monkeypatch, "brandnew", False, launch_calls, sent)
    assert len(launch_calls) == 1
    assert sent == []


def test_session_start_sends_when_pet_confirmed_alive(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path))
    (tmp_path / "claudlet-live.port").write_text("54321")
    launch_calls, sent = [], []
    _run_main(monkeypatch, "live", True, launch_calls, sent)
    assert launch_calls == []
    assert len(sent) == 1


class _RefusingSocket:
    """Deterministic stand-in for a genuinely dead pet's port -- see
    tests/test_hostinfo.py's identical fake for why this is used instead of
    a real bind-then-close socket (Windows loopback refusal timing)."""
    def settimeout(self, t): pass
    def connect(self, addr): raise ConnectionRefusedError()
    def close(self): pass


def test_session_start_dead_pet_still_drops_this_event(tmp_path, monkeypatch):
    # Documents a known, accepted limitation (not a regression): for a
    # GENUINELY dead pet, the REAL hostinfo.pet_alive() unlinks the stale
    # port file as a side effect of the refused connect. had_port was
    # captured as True before that happened, so launched_fresh stays False
    # and the hook still attempts the send below -- but read_session_port()
    # now reads the just-deleted file and returns None. There's no live pet
    # to deliver to at this instant regardless of how the flag is
    # structured (the replacement pet hasn't started listening yet), so this
    # one event is unavoidably dropped; the next hook event reaches the new
    # pet fine. This test uses the real, side-effecting pet_alive (not a
    # mock) so a future refactor that changes this ordering doesn't silently
    # change behavior.
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path))
    port_path = tmp_path / "claudlet-dead.port"
    port_path.write_text("54321")
    monkeypatch.setattr(mod.hostinfo.socket, "socket", lambda *a, **k: _RefusingSocket())
    launch_calls, sent = [], []
    monkeypatch.setattr(mod, "_launch_pet", lambda *a, **k: launch_calls.append((a, k)))
    monkeypatch.setattr(mod, "_send", lambda port, payload: sent.append((port, payload)))
    monkeypatch.setattr(mod.sys, "argv", ["claudlet-hook", "SessionStart"])
    monkeypatch.setattr(mod.sys, "stdin", io.StringIO(json.dumps(
        {"session_id": "dead", "hook_event_name": "SessionStart"})))
    mod.main()
    assert len(launch_calls) == 1          # replacement launch still attempted
    assert not port_path.exists()          # stale file cleaned up by pet_alive
    assert sent and sent[0][0] is None      # send attempted, but nothing to send to


def test_build_message_forwards_background_task_counts():
    # Forward counts of RUNNING background tasks, excluding the stopping
    # agent's own entry (it lists itself as running even at its final stop).
    bt = [
        {"id": "self", "type": "subagent", "status": "running"},
        {"id": "shell1", "type": "shell", "status": "running"},
        {"id": "other", "type": "subagent", "status": "running"},
        {"id": "doneshell", "type": "shell", "status": "completed"},
    ]
    msg = json.loads(mod.build_message(
        ["claudlet-hook", "SubagentStop"],
        {"session_id": "s1", "agent_id": "self", "background_tasks": bt}))
    assert msg["bg_agents"] == 1      # other (self excluded)
    assert msg["bg_tasks"] == 2       # shell1 + other (self excluded, done not running)


def test_build_message_excludes_the_stopping_agent_itself():
    # At an agent's OWN final SubagentStop it still lists itself as running.
    # If that stop is the session's last hook event (background agent finishing
    # while the user is away), counting self would leave the companion up
    # forever -- so self is excluded, and the engine's depart grace (not
    # instant departure) is what keeps the companion trailing the UI.
    bt = [{"id": "me", "type": "subagent", "status": "running"}]
    msg = json.loads(mod.build_message(
        ["claudlet-hook", "SubagentStop"],
        {"session_id": "s1", "agent_id": "me", "background_tasks": bt}))
    assert msg["bg_agents"] == 0
    assert msg["bg_tasks"] == 0


def test_build_message_omits_bg_counts_when_no_background_tasks():
    msg = json.loads(mod.build_message(
        ["claudlet-hook", "PreToolUse"],
        {"session_id": "s1", "tool_name": "Agent", "tool_input": {}}))
    assert "bg_agents" not in msg
    assert "bg_tasks" not in msg


def test_build_message_counts_only_known_task_types():
    # Only shell/subagent entries are real per-run work. An unknown persistent
    # entry type (whatever Claude Code may list as always-running) must not
    # keep bg_tasks pinned above zero -- that held the companion up forever.
    bt = [
        {"id": "w1", "type": "watcher", "status": "running"},
        {"id": "c1", "type": "cron", "status": "running"},
    ]
    msg = json.loads(mod.build_message(
        ["claudlet-hook", "Stop"], {"session_id": "s1", "background_tasks": bt}))
    assert msg["bg_tasks"] == 0
    assert msg["bg_agents"] == 0
