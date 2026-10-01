from claudlet.core import brain


def _user(t):
    return {"kind": "user", "text": t}


def _agent(t):
    return {"kind": "agent", "text": t}


# --- recent_context -----------------------------------------------------------

def test_recent_context_keeps_newest_within_budget_in_order():
    entries = [_user("old " * 50), _agent("middle"), _user("newest")]
    out = brain.recent_context(entries, budget=40)
    assert "newest" in out and "middle" in out
    assert "old" not in out                       # 예산을 넘는 오래된 것은 빠진다
    assert out.index("middle") < out.index("newest")   # 오래된 것부터 읽힌다


def test_recent_context_clips_each_entry():
    out = brain.recent_context([_agent("x" * 1000)], per=50)
    assert out.count("x") <= 50


def test_recent_context_redacts_secrets():
    out = brain.recent_context([_user("export API_KEY=sk-abcdefghijklmnop")])
    assert "sk-abcdefghijklmnop" not in out


def test_recent_context_renders_tools_and_todos():
    out = brain.recent_context([
        {"kind": "tool", "name": "Bash", "detail": "pytest -q"},
        {"kind": "todo", "items": [{"text": "fix login", "status": "in_progress"}]},
    ])
    assert "Bash" in out and "pytest -q" in out
    assert "fix login" in out


def test_recent_context_empty():
    assert brain.recent_context([]) == ""


# --- build_prompt -------------------------------------------------------------

def test_build_prompt_carries_voice_name_history_and_words():
    history = [  # newest first, as history.load returns
        {"question": "두번째", "answer": "응 두번째"},
        {"question": "첫번째", "answer": "응 첫번째"},
    ]
    system, user = brain.build_prompt("느릿느릿 물컹하게", "모찌", history,
                                      "[user] 테스트 고쳐줘", "지금 뭐 해?")
    assert "느릿느릿 물컹하게" in system and "모찌" in system
    assert "SAY:" in system and "RELAY:" in system
    assert "테스트 고쳐줘" in user and "지금 뭐 해?" in user
    assert user.index("첫번째") < user.index("두번째")    # 대화는 오래된 것부터


def test_build_prompt_includes_pointed_text():
    _, user = brain.build_prompt("", "", [], "", "이거 뭐야?", pointed="NullPointerException at Foo")
    assert "NullPointerException" in user


def test_a_captured_screen_tells_the_creature_to_hand_over_what_it_cannot_read():
    _, user = brain.build_prompt("", "", [], "", "이거 뭐야?", pointed="Chrome", shot=True)
    assert "cannot see pictures" in user and "RELAY" in user
    assert "cannot see pictures" not in brain.build_prompt("", "", [], "", "이거 뭐야?",
                                                         pointed="Chrome")[1]


def test_build_prompt_skips_unanswered_history():
    _, user = brain.build_prompt("", "", [{"question": "아직", "answer": None}], "", "hi")
    assert "아직" not in user


# --- parse_reply --------------------------------------------------------------

def test_parse_say_only():
    assert brain.parse_reply("SAY: 응 지금 테스트 돌리는 중~") == {
        "says": ["응 지금 테스트 돌리는 중~"], "relay": None}


def test_parse_say_and_relay():
    r = brain.parse_reply("SAY: 알았어 전할게\nRELAY: 로그인 테스트 실패 원인을 고쳐줘")
    assert r == {"says": ["알았어 전할게"], "relay": "로그인 테스트 실패 원인을 고쳐줘"}


def test_parse_several_says_are_kept_in_order_up_to_three():
    r = brain.parse_reply("SAY: 하나\nSAY: 둘\nSAY: 셋\nSAY: 넷")
    assert r["says"] == ["하나", "둘", "셋"]


def test_parse_ignores_format_violation_first_line_is_say():
    r = brain.parse_reply("그냥 막 대답함\n두번째 줄")
    assert r == {"says": ["그냥 막 대답함"], "relay": None}


def test_parse_relay_without_say_still_says_something():
    r = brain.parse_reply("RELAY: 빌드 돌려줘")
    assert r["relay"] == "빌드 돌려줘" and r["says"]


def test_parse_empty_and_skip_are_none():
    assert brain.parse_reply("") is None
    assert brain.parse_reply("   \n ") is None
    assert brain.parse_reply("SKIP") is None
    assert brain.parse_reply("skip.") is None


def test_parse_lowercase_and_markdown_labels():
    r = brain.parse_reply("**say:** 안녕\nrelay: 없음 아님")
    assert r["says"] == ["안녕"]


# --- 띄워 둔 머리 ---------------------------------------------------------------

def test_new_entries_returns_only_what_came_after():
    entries = [{"kind": "user", "ts": "2026-10-01T10:00:00Z", "text": "a"},
               {"kind": "agent", "ts": "2026-10-01T10:00:05Z", "text": "b"}]
    fresh, last = brain.new_entries(entries, None)
    assert len(fresh) == 2 and last == "2026-10-01T10:00:05Z"
    fresh, last2 = brain.new_entries(entries, last)
    assert fresh == [] and last2 == last
    entries.append({"kind": "tool", "ts": "2026-10-01T10:01:00Z", "name": "Bash"})
    fresh, _ = brain.new_entries(entries, last)
    assert [e["kind"] for e in fresh] == ["tool"]


def test_stream_roundtrip():
    import json
    msg = json.loads(brain.stream_message("안녕"))
    assert msg["message"]["content"] == "안녕"
    assert brain.stream_result('{"type":"result","subtype":"success","result":"SAY: 응"}') == (True, "SAY: 응")
    assert brain.stream_result('{"type":"result","is_error":true,"result":"x"}')[0] is False
    assert brain.stream_result('{"type":"assistant"}') is None
    assert brain.stream_result("not json") is None


def test_stream_command_is_the_hookless_command_plus_streaming():
    argv = brain.stream_command("/usr/bin/claude")
    assert '{"disableAllHooks":true}' in argv and "stream-json" in argv


def test_event_prompt_allows_skip():
    assert "SKIP" in brain.event_prompt("just finished a turn")


# --- command ------------------------------------------------------------------

def test_command_claude_has_no_hooks_no_tools_no_persistence():
    argv = brain.command("/usr/bin/claude")
    assert argv[0] == "/usr/bin/claude" and "-p" in argv
    assert argv[argv.index("--settings") + 1] == '{"disableAllHooks":true}'
    assert argv[argv.index("--tools") + 1] == ""
    assert "--no-session-persistence" in argv and "--strict-mcp-config" in argv


def test_command_args_never_carry_the_persona():
    # 윈도우의 claude.cmd 는 cmd.exe 가 인자를 다시 읽는다 — 남이 만든 크리처의
    # 말투가 인자에 실리면 명령이 될 수 있다. 인자는 고정 문자열뿐이어야 한다.
    system, _ = brain.build_prompt("멍멍 & del /q *", "강아지", [], "", "hi")
    for argv in (brain.stream_command("/x/claude"), brain.codex_server_command("/x/codex")):
        joined = " ".join(argv)
        assert "멍멍" not in joined and "\n" not in joined
    assert "멍멍" in brain.stdin_for(system, "hi")


def test_stdin_carries_system_prompt_then_message():
    out = brain.stdin_for("SYS", "hi")
    assert out.index("SYS") < out.index("hi")


def test_parse_blank_say_without_relay_is_a_failure():
    assert brain.parse_reply("SAY:") is None
    assert brain.parse_reply("SAY:  \nRELAY: none") is None


def test_history_is_redacted():
    _, user = brain.build_prompt("", "", [{"question": "키 뭐였지",
                                            "answer": "token: abc123secret"}], "", "hi")
    assert "abc123secret" not in user


def test_a_standalone_pet_is_told_it_cannot_relay():
    system, _ = brain.build_prompt("", "", [], "", "고쳐줘", alone=True)
    assert "standalone" in system
    assert "standalone" not in brain.build_prompt("", "", [], "", "고쳐줘")[0]


def test_background_goes_to_the_creature_only():
    system, user = brain.build_prompt("짧게", "루시엘", [], "", "안녕",
                                      background="하얀 털의 설표.\n더위를 싫어한다.")
    assert "하얀 털의 설표" in system and "더위를 싫어한다" in system
    assert "설표" not in user


def test_every_built_in_creature_brings_a_background():
    # 레지스트리(avatars.get)를 거치지 않는다 — 사용자 폴더의 같은 이름 크리처가 가린다
    from claudlet.core import petconfig
    from claudlet.core.avatars import builtin, slime, astronaut, codex
    for av in (builtin.Claudlet, slime.Slime, astronaut.Astronaut, codex.Codex):
        bg = petconfig.for_creature({}, av.name, av)["background"]
        assert bg and len(bg) <= petconfig.BACKGROUND_MAX, av.name


# --- codex app-server ----------------------------------------------------------

def test_codex_server_has_no_hooks_tools_or_mcp():
    argv = brain.codex_server_command("/usr/bin/codex")
    assert argv[:2] == ["/usr/bin/codex", "app-server"]
    assert "mcp_servers={}" in argv
    for f in ("hooks", "shell_tool", "unified_exec", "computer_use"):
        assert "features.%s=false" % f in argv


def test_codex_thread_is_ephemeral_and_read_only():
    assert brain.CODEX_THREAD["ephemeral"] is True
    assert brain.CODEX_THREAD["sandbox"] == "read-only"


def test_codex_event_reading():
    import json
    assert brain.codex_event('{"id":2,"result":{"thread":{"id":"t"}}}') == (
        "reply", 2, {"thread": {"id": "t"}}, None)
    assert brain.codex_event(json.dumps({"method": "item/completed", "params": {
        "item": {"type": "agentMessage", "text": "SAY: 응"}}})) == ("text", "SAY: 응")
    assert brain.codex_event('{"method":"turn/completed","params":{"turn":{"status":"completed"}}}') == ("done", True)
    assert brain.codex_event('{"method":"turn/completed","params":{"turn":{"status":"failed"}}}') == ("done", False)
    assert brain.codex_event('{"method":"item/agentMessage/delta","params":{}}') is None
    assert brain.codex_event("garbage") is None


def test_rpc_lines():
    import json
    assert json.loads(brain.rpc(1, "initialize", {"a": 1})) == {
        "jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"a": 1}}
    assert "id" not in json.loads(brain.rpc(None, "initialized"))


# --- needs_eyes ---------------------------------------------------------------

def test_a_shot_of_an_unreadable_window_needs_the_session():
    assert brain.needs_eyes({"image": "/x.png", "note": "text unavailable", "lines": 0})
    assert brain.needs_eyes({"image": "/x.png", "note": None, "lines": 2})


def test_readable_text_or_no_shot_lets_the_creature_try():
    assert not brain.needs_eyes({"image": "/x.png", "note": None, "lines": 5})
    assert not brain.needs_eyes({"image": None, "note": "text unavailable", "lines": 0})


def test_an_editor_never_needs_the_picture():
    assert not brain.needs_eyes({"image": "/x.png", "note": None, "lines": 0,
                                 "open": {"project": "p", "file": "f"}})
