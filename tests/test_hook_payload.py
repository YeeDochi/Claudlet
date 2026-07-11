import sys, os, io, json, types

HOOK = os.path.join(os.path.dirname(__file__), "..", "bin", "claude-pet-hook")
mod = types.ModuleType("claude_pet_hook")
mod.__file__ = HOOK
with open(HOOK, encoding="utf-8") as f:
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


def test_sock_for_uses_session(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path))
    assert mod.sock_for({"session_id": "xyz"}) is None       # no pet running yet
    (tmp_path / "claude-pet-xyz.port").write_text("54321")
    assert mod.sock_for({"session_id": "xyz"}) == 54321
    assert mod.sock_for({}) is None


def _run_main(monkeypatch, session_id, pet_alive_result, launch_calls, sent):
    monkeypatch.setattr(mod.hostinfo, "pet_alive", lambda sid: pet_alive_result)
    monkeypatch.setattr(mod, "_launch_pet",
                         lambda *a, **k: launch_calls.append((a, k)))
    monkeypatch.setattr(mod, "_send",
                         lambda port, payload: sent.append((port, payload)))
    monkeypatch.setattr(mod.sys, "argv", ["claude-pet-hook", "SessionStart"])
    monkeypatch.setattr(mod.sys, "stdin", io.StringIO(json.dumps(
        {"session_id": session_id, "hook_event_name": "SessionStart"})))
    mod.main()


def test_session_start_still_sends_when_resumed_pet_times_out(tmp_path, monkeypatch):
    # A resumed session (its .port file already exists) where pet_alive()
    # returns False from a transient timeout -- not a proven-dead port --
    # must NOT have the triggering SessionStart event dropped: it might be
    # our own pet, alive, just briefly slow to answer the liveness ping.
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path))
    (tmp_path / "claude-pet-resumed.port").write_text("54321")
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
    (tmp_path / "claude-pet-live.port").write_text("54321")
    launch_calls, sent = [], []
    _run_main(monkeypatch, "live", True, launch_calls, sent)
    assert launch_calls == []
    assert len(sent) == 1
