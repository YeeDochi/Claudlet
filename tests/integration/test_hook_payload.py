import sys, os, io, json
from claudlet.cli import hook as mod
from claudlet.core import outbox


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


def _run_main(monkeypatch, session_id, pet_alive_result, launch_calls, sent,
              agent="claude", transcript_path=None):
    monkeypatch.setattr(mod.hostinfo, "pet_alive", lambda sid: pet_alive_result)
    monkeypatch.setattr(mod, "_launch_pet",
                         lambda *a, **k: launch_calls.append((a, k)))
    monkeypatch.setattr(mod, "_send",
                         lambda port, payload: sent.append((port, payload)))
    argv = ["claudlet-hook", "SessionStart"]
    if agent != "claude":
        argv += ["--agent", agent]
    data = {"session_id": session_id, "hook_event_name": "SessionStart"}
    if transcript_path is not None:
        data["transcript_path"] = str(transcript_path)
    monkeypatch.setattr(mod.sys, "argv", argv)
    monkeypatch.setattr(mod.sys, "stdin", io.StringIO(json.dumps(data)))
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


def test_codex_session_start_ignores_missing_rollout(tmp_path, monkeypatch):
    """Codex tool workers announce short-lived sessions without creating the
    rollout they name; those internal sessions must not get their own pet."""
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path))
    launch_calls, sent = [], []
    missing = tmp_path / "rollout-2026-09-17T14-47-05-01a0ade7-7ee0.jsonl"
    _run_main(monkeypatch, "01a0ade7-7ee0", False, launch_calls, sent,
              agent="codex", transcript_path=missing)

    assert launch_calls == []
    assert sent == []


def test_codex_session_start_launches_for_a_real_rollout(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path))
    rollout = tmp_path / "rollout-2026-09-17T14-46-53-01a0ade7-518a.jsonl"
    rollout.write_text("", encoding="utf-8")
    launch_calls, sent = [], []
    _run_main(monkeypatch, "01a0ade7-518a", False, launch_calls, sent,
              agent="codex", transcript_path=rollout)

    assert len(launch_calls) == 1


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


# --- terminal tab title: the only thing that tells two sessions in one
# --- Windows Terminal apart (see platform/winterm.py)

def _tree(edges):
    """proc_info from a {pid: (comm, ppid)} map."""
    return lambda pid: edges.get(pid)


TREE = {  # hook -> shell -> claude -> pwsh -> WindowsTerminal -> explorer
    101: ("claudlet-hook.exe", 90), 90: ("bash.exe", 80),
    80: ("claude.exe", 70), 70: ("pwsh.exe", 60),
    60: ("windowsterminal.exe", 50), 50: ("explorer.exe", 1),
}


def test_ancestor_chain_is_nearest_first_and_excludes_self():
    assert mod.ancestor_chain(101, _tree(TREE)) == [90, 80, 70, 60, 50]


def test_ancestor_chain_stops_at_a_dead_parent():
    assert mod.ancestor_chain(101, _tree({101: ("hook", 90)})) == [90]


def test_ancestor_chain_survives_a_parent_cycle():
    cyclic = {1001: ("a", 1002), 1002: ("b", 1001)}
    assert mod.ancestor_chain(1001, _tree(cyclic)) == [1002]


def test_console_title_takes_the_first_attachable_console():
    # Claude Code gives each child a FRESH console titled with its exe path, so
    # the caller walks the chain top-down: the processes above the pane's shell
    # own no console and fail to attach, and the first success is the pane.
    titles = {70: "✳ my-session"}          # only pwsh has a console
    attached = []

    def attach(pid):
        attached.append(pid)
        return pid in titles

    def read():
        return titles[attached[-1]]

    assert mod.console_title([50, 60, 70, 80], attach, read) == "✳ my-session"
    assert attached == [50, 60, 70]        # stopped as soon as one attached


def test_console_title_none_when_nothing_attaches():
    assert mod.console_title([50, 60], lambda _p: False,
                             lambda: "never") is None


def test_console_title_skips_an_attached_but_empty_console():
    titles = {60: "", 70: "✳ real"}

    def attach(pid):
        return pid in titles
    seq = iter(["", "✳ real"])
    assert mod.console_title([60, 70], attach, lambda: next(seq)) == "✳ real"


def test_console_title_survives_a_win32_error():
    def attach(_pid):
        raise OSError("AttachConsole blew up")
    assert mod.console_title([70], attach, lambda: "x") is None


def test_console_title_empty_chain():
    assert mod.console_title([], lambda _p: True, lambda: "x") is None


def test_build_message_forwards_the_tab_title():
    msg = json.loads(mod.build_message(
        ["claudlet-hook", "Notification"], {"session_id": "s1"}, "✳ my-session"))
    assert msg["title"] == "✳ my-session"


def test_build_message_omits_the_title_when_unavailable():
    for absent in (None, ""):
        msg = json.loads(mod.build_message(
            ["claudlet-hook", "Stop"], {"session_id": "s1"}, absent))
        assert "title" not in msg


def test_win_console_title_is_none_off_windows(monkeypatch):
    monkeypatch.setattr(mod.os, "name", "posix")
    assert mod._win_console_title(101) is None


def test_agent_arg_defaults_to_claude():
    assert mod.agent_arg(["claudlet-hook", "Stop"]) == "claude"
    assert mod.agent_arg(["claudlet-hook", "Stop", "--agent", "codex"]) == "codex"
    assert mod.agent_arg(["claudlet-hook", "Stop", "--agent=codex"]) == "codex"
    # an unknown agent must not crash a hook; it degrades to the default
    assert mod.agent_arg(["claudlet-hook", "Stop", "--agent", "wat"]) == "claude"


def test_session_of_falls_back_to_the_transcript_uuid():
    uuid = "01a0acb1-0899-7763-8512-b9d0b28c1f02"
    data = {"transcript_path":
            "/home/u/.codex/sessions/2026/09/17/rollout-2026-09-17T09-07-58-%s.jsonl" % uuid}
    assert mod.session_of(data) == uuid
    assert mod.session_of({"session_id": "abc", "transcript_path": "x"}) == "abc"
    assert mod.session_of({}) == "default"


def test_build_message_still_carries_event_and_session():
    line = mod.build_message(["claudlet-hook", "PreToolUse", "--agent", "codex"],
                              {"session_id": "s1", "tool_name": "shell"})
    msg = json.loads(line)
    assert msg["event"] == "PreToolUse" and msg["session"] == "s1"
    assert msg["tool_name"] == "shell"


def test_build_message_uses_session_of_for_a_codex_payload_with_no_session_id():
    # main() keys the port file with session_of(data) (which falls back to the
    # transcript's rollout UUID for Codex, which sends no session_id). If
    # build_message used data.get("session_id") or "default" instead, the pet
    # would be found by its real uuid while every message told the engine the
    # session was "default" -- two different rules for "which session is this".
    uuid = "01a0acb1-0899-7763-8512-b9d0b28c1f02"
    data = {"transcript_path":
            "/home/u/.codex/sessions/2026/09/17/rollout-2026-09-17T09-07-58-%s.jsonl" % uuid,
            "tool_name": "exec"}
    msg = json.loads(mod.build_message(
        ["claudlet-hook", "PreToolUse", "--agent", "codex"], data))
    assert msg["session"] == uuid
    assert msg["session"] == mod.session_of(data)


# ---------- 아웃박스: 펫이 쌓아둔 쪽지가 에이전트에게 실려 간다 ----------

def _run_event(monkeypatch, event, session_id="s1", data=None):
    """훅을 이벤트 하나로 돌리고 stdout 을 돌려준다 — 에이전트가 보는 전부."""
    monkeypatch.setattr(mod.hostinfo, "pet_alive", lambda sid: True)
    monkeypatch.setattr(mod, "_launch_pet", lambda *a, **k: None)
    monkeypatch.setattr(mod, "_send", lambda port, payload: None)
    payload = {"session_id": session_id, "hook_event_name": event}
    payload.update(data or {})
    monkeypatch.setattr(mod.sys, "argv", ["claudlet-hook", event])
    monkeypatch.setattr(mod.sys, "stdin", io.StringIO(json.dumps(payload)))
    out = io.StringIO()
    monkeypatch.setattr(mod.sys, "stdout", out)
    mod.main()
    return out.getvalue()


def test_a_waiting_note_is_delivered_on_the_next_prompt(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path))
    outbox.append("s1", "이거 왜 느려?")
    out = json.loads(_run_event(monkeypatch, "UserPromptSubmit"))
    assert out["hookSpecificOutput"]["hookEventName"] == "UserPromptSubmit"
    assert "이거 왜 느려?" in out["hookSpecificOutput"]["additionalContext"]


def test_a_waiting_note_also_lands_mid_turn_at_the_next_tool_call(tmp_path, monkeypatch):
    # 에이전트가 일하는 중이면 다음 프롬프트까지 기다릴 이유가 없다.
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path))
    outbox.append("s1", "아 잠깐, 그거 말고")
    out = json.loads(_run_event(monkeypatch, "PostToolUse", data={"tool_name": "Edit"}))
    assert out["hookSpecificOutput"]["hookEventName"] == "PostToolUse"
    assert "그거 말고" in out["hookSpecificOutput"]["additionalContext"]


def test_a_note_is_delivered_once_not_at_every_boundary(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path))
    outbox.append("s1", "한 번만")
    _run_event(monkeypatch, "PostToolUse", data={"tool_name": "Edit"})
    assert _run_event(monkeypatch, "UserPromptSubmit") == ""


def test_an_empty_outbox_writes_nothing_at_all(tmp_path, monkeypatch):
    # 훅의 stdout 은 에이전트가 파싱한다. 전할 것이 없으면 한 글자도 쓰지 않는다.
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path))
    assert _run_event(monkeypatch, "UserPromptSubmit") == ""
    assert _run_event(monkeypatch, "PostToolUse", data={"tool_name": "Edit"}) == ""


def test_other_events_never_carry_the_outbox(tmp_path, monkeypatch):
    # Stop/PreToolUse 는 additionalContext 를 이런 식으로 받지 않는다.
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path))
    outbox.append("s1", "기다리는 쪽지")
    assert _run_event(monkeypatch, "Stop") == ""
    assert outbox.pending("s1") == 1       # 그리고 버려지지도 않는다


def test_another_session_s_notes_are_not_delivered_here(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path))
    outbox.append("other", "남의 쪽지")
    assert _run_event(monkeypatch, "UserPromptSubmit", session_id="s1") == ""


def test_a_broken_outbox_never_fails_the_hook(tmp_path, monkeypatch):
    # 훅은 무슨 일이 있어도 조용히 성공한다.
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path))

    def boom(*a, **k):
        raise RuntimeError("아웃박스가 터졌다")

    monkeypatch.setattr(mod.outbox, "take", boom)
    assert _run_event(monkeypatch, "UserPromptSubmit") == ""


def test_an_unmeasured_agent_gets_no_hook_output_and_keeps_its_note(tmp_path, monkeypatch):
    # 이 stdout 형식은 Claude Code 의 스키마다. 코덱스가 같은 모양을 읽는다는
    # 근거는 아직 없으므로 쓰지 않고, 쪽지는 버리지도 않는다.
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path))
    outbox.append("s1", "기다리는 쪽지")
    monkeypatch.setattr(mod.hostinfo, "pet_alive", lambda sid: True)
    monkeypatch.setattr(mod, "_launch_pet", lambda *a, **k: None)
    monkeypatch.setattr(mod, "_send", lambda port, payload: None)
    monkeypatch.setattr(mod.sys, "argv",
                        ["claudlet-hook", "UserPromptSubmit", "--agent", "codex"])
    monkeypatch.setattr(mod.sys, "stdin", io.StringIO(json.dumps(
        {"session_id": "s1", "hook_event_name": "UserPromptSubmit"})))
    out = io.StringIO()
    monkeypatch.setattr(mod.sys, "stdout", out)
    mod.main()
    assert out.getvalue() == ""
    assert outbox.pending("s1") == 1


def test_the_creature_line_is_sent_to_the_pet_when_the_turn_ends(tmp_path, monkeypatch):
    # 에이전트의 답은 터미널에, 크리처의 한 줄은 말풍선에. 그 분리가 이 훅이다.
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path))
    tr = tmp_path / "t.jsonl"
    tr.write_text(json.dumps({"type": "assistant", "message": {"content": [
        {"type": "text", "text": "고쳤다. <claudlet>느려터졌더라구우…</claudlet>"}]}}),
        encoding="utf-8")
    sent = []
    monkeypatch.setattr(mod.hostinfo, "pet_alive", lambda sid: True)
    monkeypatch.setattr(mod, "_launch_pet", lambda *a, **k: None)
    monkeypatch.setattr(mod, "_send", lambda port, payload: sent.append(payload))
    monkeypatch.setattr(mod.sys, "argv", ["claudlet-hook", "Stop"])
    monkeypatch.setattr(mod.sys, "stdin", io.StringIO(json.dumps(
        {"session_id": "s1", "hook_event_name": "Stop",
         "transcript_path": str(tr)})))
    mod.main()
    says = [json.loads(p.decode()) for p in sent
            if b'"say"' in p]
    assert says and says[0]["text"] == "느려터졌더라구우…"


def test_an_ordinary_turn_says_nothing_to_the_pet(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path))
    tr = tmp_path / "t.jsonl"
    tr.write_text(json.dumps({"type": "assistant", "message": {"content": [
        {"type": "text", "text": "마커 없는 평범한 답"}]}}), encoding="utf-8")
    sent = []
    monkeypatch.setattr(mod.hostinfo, "pet_alive", lambda sid: True)
    monkeypatch.setattr(mod, "_launch_pet", lambda *a, **k: None)
    monkeypatch.setattr(mod, "_send", lambda port, payload: sent.append(payload))
    monkeypatch.setattr(mod.sys, "argv", ["claudlet-hook", "Stop"])
    monkeypatch.setattr(mod.sys, "stdin", io.StringIO(json.dumps(
        {"session_id": "s1", "hook_event_name": "Stop",
         "transcript_path": str(tr)})))
    mod.main()
    assert not [p for p in sent if b'"say"' in p]
