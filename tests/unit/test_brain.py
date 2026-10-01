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


def test_build_prompt_skips_unanswered_history():
    _, user = brain.build_prompt("", "", [{"question": "아직", "answer": None}], "", "hi")
    assert "아직" not in user


# --- parse_reply --------------------------------------------------------------

def test_parse_say_only():
    assert brain.parse_reply("SAY: 응 지금 테스트 돌리는 중~") == {
        "say": "응 지금 테스트 돌리는 중~", "relay": None}


def test_parse_say_and_relay():
    r = brain.parse_reply("SAY: 알았어 전할게\nRELAY: 로그인 테스트 실패 원인을 고쳐줘")
    assert r == {"say": "알았어 전할게", "relay": "로그인 테스트 실패 원인을 고쳐줘"}


def test_parse_ignores_format_violation_first_line_is_say():
    r = brain.parse_reply("그냥 막 대답함\n두번째 줄")
    assert r == {"say": "그냥 막 대답함", "relay": None}


def test_parse_relay_without_say_still_says_something():
    r = brain.parse_reply("RELAY: 빌드 돌려줘")
    assert r["relay"] == "빌드 돌려줘" and r["say"]


def test_parse_empty_is_none():
    assert brain.parse_reply("") is None
    assert brain.parse_reply("   \n ") is None


def test_parse_lowercase_and_markdown_labels():
    r = brain.parse_reply("**say:** 안녕\nrelay: 없음 아님")
    assert r["say"] == "안녕"


# --- command ------------------------------------------------------------------

def test_command_claude_has_no_hooks_no_tools_no_persistence():
    argv = brain.command("claude", "/usr/bin/claude")
    assert argv[0] == "/usr/bin/claude" and "-p" in argv
    assert argv[argv.index("--settings") + 1] == '{"disableAllHooks":true}'
    assert argv[argv.index("--tools") + 1] == ""
    assert "--no-session-persistence" in argv and "--strict-mcp-config" in argv


def test_command_args_never_carry_the_persona():
    # 윈도우의 claude.cmd 는 cmd.exe 가 인자를 다시 읽는다 — 남이 만든 크리처의
    # 말투가 인자에 실리면 명령이 될 수 있다. 인자는 고정 문자열뿐이어야 한다.
    system, _ = brain.build_prompt("멍멍 & del /q *", "강아지", [], "", "hi")
    for agent in ("claude", "codex"):
        argv = " ".join(brain.command(agent, "/x/" + agent, outfile="/tmp/o"))
        assert "멍멍" not in argv and "\n" not in argv
    assert "멍멍" in brain.stdin_for(system, "hi")


def test_command_codex_has_no_hooks_no_shell_and_reads_stdin():
    argv = brain.command("codex", "/usr/bin/codex", outfile="/tmp/o.txt")
    assert argv[:2] == ["/usr/bin/codex", "exec"]
    for f in ("hooks", "shell_tool", "unified_exec", "computer_use"):
        assert "features.%s=false" % f in argv
    assert "--ephemeral" in argv and "--ignore-user-config" in argv
    assert argv[argv.index("-o") + 1] == "/tmp/o.txt"
    assert argv[-1] == "-"


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
