from claudlet.platform import konsole


# --- pure helpers ---------------------------------------------------------

def test_pick_service_matches_pid_in_ancestors():
    names = ["org.kde.KWin", "org.kde.konsole-6931", "org.freedesktop.DBus"]
    assert konsole.pick_service(names, {19137, 6931, 4201}) == "org.kde.konsole-6931"


def test_pick_service_none_when_konsole_pid_not_ours():
    # a Konsole on the bus, but a different one (another window/user)
    assert konsole.pick_service(["org.kde.konsole-9999"], {19137, 6931}) is None


def test_pick_service_ignores_malformed_names():
    assert konsole.pick_service(["org.kde.konsole-", "org.kde.konsole-x"], {6931}) is None


def test_pick_session_returns_our_tab():
    # session 3's shell (19137) is our ancestor; session 4's (21321) is not
    assert konsole.pick_session([(3, 19137), (4, 21321)], {19613, 19137, 6931}) == 3


def test_pick_session_none_when_no_tab_is_ours():
    assert konsole.pick_session([(4, 21321), (6, 22536)], {19137, 6931}) is None


def test_window_for_session_finds_owning_window():
    ws = [("/Windows/2", [3, 4]), ("/Windows/5", [6, 7])]
    assert konsole.window_for_session(ws, 6) == "/Windows/5"
    assert konsole.window_for_session(ws, 3) == "/Windows/2"
    assert konsole.window_for_session(ws, 99) is None


# --- orchestrator with a fake qdbus6 runner -------------------------------

def _fake_bus(services, paths, session_pid, window_sessions, calls):
    """Build a run(*args) that mimics qdbus6 over a canned bus and records
    setCurrentSession calls into `calls`."""
    def run(*args):
        if not args:                                   # list services
            return "\n".join(services)
        if len(args) == 1:                             # list object paths
            return "\n".join(paths)
        svc, path, method = args[0], args[1], args[2]
        if method == "org.kde.konsole.Session.processId":
            return str(session_pid[path])
        if method == "org.kde.konsole.Window.sessionList":
            return "\n".join(str(s) for s in window_sessions[path])
        if method == "org.kde.konsole.Window.setCurrentSession":
            calls.append((path, args[3]))
            return ""
        raise AssertionError("unexpected method %s" % method)
    return run


def test_focus_selects_the_right_tab_two_tabs_one_window():
    calls = []
    run = _fake_bus(
        # qdbus6 indents each service name with a leading space — focus() must
        # strip before matching (real-hardware regression).
        services=[" org.kde.KWin", " org.kde.konsole-6931"],
        paths=["/Sessions", "/Sessions/3", "/Sessions/6", "/Windows", "/Windows/2"],
        session_pid={"/Sessions/3": 19137, "/Sessions/6": 22536},
        window_sessions={"/Windows/2": [3, 6]},
        calls=calls,
    )
    # our Claude (23001) descends from zsh 22536 -> Konsole session 6
    result = konsole.focus({23001, 22536, 6931, 4201}, run)
    assert result == ("org.kde.konsole-6931", "/Windows/2", 6)
    assert calls == [("/Windows/2", "6")]              # switched to OUR tab


def test_focus_picks_the_right_window_when_two_windows():
    calls = []
    run = _fake_bus(
        services=["org.kde.konsole-6931"],
        paths=["/Sessions/3", "/Sessions/6", "/Windows/2", "/Windows/5"],
        session_pid={"/Sessions/3": 19137, "/Sessions/6": 22536},
        window_sessions={"/Windows/2": [3], "/Windows/5": [6]},
        calls=calls,
    )
    result = konsole.focus({22536, 6931}, run)
    assert result == ("org.kde.konsole-6931", "/Windows/5", 6)
    assert calls == [("/Windows/5", "6")]


def test_focus_none_when_not_konsole_host():
    calls = []
    run = _fake_bus(services=["org.kde.KWin"], paths=[], session_pid={},
                    window_sessions={}, calls=calls)
    assert konsole.focus({19137, 6931}, run) is None
    assert calls == []                                 # nothing activated


def test_focus_none_when_our_tab_absent():
    calls = []
    run = _fake_bus(
        services=["org.kde.konsole-6931"],
        paths=["/Sessions/3", "/Windows/2"],
        session_pid={"/Sessions/3": 19137},
        window_sessions={"/Windows/2": [3]},
        calls=calls,
    )
    # ancestor pids don't include session 3's shell 19137
    assert konsole.focus({22536, 6931}, run) is None
    assert calls == []


def test_focus_empty_ancestors_is_noop():
    calls = []
    run = _fake_bus(services=["org.kde.konsole-6931"], paths=[], session_pid={},
                    window_sessions={}, calls=calls)
    assert konsole.focus(set(), run) is None


def test_focus_survives_a_bus_error():
    def run(*args):
        raise RuntimeError("dbus down")
    assert konsole.focus({6931}, run) is None


# ---------- 펫이 이 세션의 프롬프트에 직접 써 넣는다 ----------

def test_submit_text_ends_with_a_carriage_return():
    # Enter 키가 터미널에 보내는 것은 CR 이다. LF 를 보내면 raw 모드로 도는
    # TUI(Claude Code)에서는 글자만 찍히고 제출되지 않는다.
    assert konsole.submit_text("이거 왜 느려?") == "이거 왜 느려?\r"


def test_submit_text_never_submits_more_than_one_prompt():
    # 여러 줄을 그대로 보내면 줄마다 프롬프트가 하나씩 제출된다.
    assert konsole.submit_text("첫 줄\n둘째 줄").count("\r") == 1
    assert konsole.submit_text("첫 줄\r\n둘째 줄") == "첫 줄 둘째 줄\r"


def test_submit_text_refuses_to_submit_nothing():
    assert konsole.submit_text("   ") is None
    assert konsole.submit_text("") is None


def test_send_text_types_into_our_own_tab():
    calls, sent = [], []
    base = _fake_bus(
        services=[" org.kde.konsole-6931"],
        paths=["/Sessions/3", "/Sessions/6", "/Windows/2"],
        session_pid={"/Sessions/3": 19137, "/Sessions/6": 22536},
        window_sessions={"/Windows/2": [3, 6]},
        calls=calls,
    )

    def run(*args):
        if len(args) > 2 and args[2] == "org.kde.konsole.Session.sendText":
            sent.append((args[1], args[3]))
            return ""
        return base(*args)

    assert konsole.send_text({23001, 22536, 6931}, run, "안녕?") is True
    assert sent == [("/Sessions/6", "안녕?\r")]        # 남의 탭이 아니라 우리 탭


def test_send_text_is_false_when_this_is_not_our_konsole():
    def run(*args):
        return "" if not args else "org.kde.konsole-1\n"

    assert konsole.send_text({999}, run, "안녕?") is False


def test_send_text_sends_nothing_for_an_empty_message():
    def run(*args):
        raise AssertionError("빈 메시지로 버스를 건드리면 안 된다")

    assert konsole.send_text({1}, run, "  ") is False


# ---------- Konsole 이 sendText 를 아예 막아두었는지 ----------
# 설정 파일을 읽어 판단하면 틀린다(사용자가 켠 직후에도 KDE 가 파일 쓰기를
# 미룬다). 빈 문자열을 실제로 보내 본다 — 아무것도 타이핑되지 않는다.

def _probe_bus(allowed, calls):
    def run(*args):
        if not args:
            return " org.kde.konsole-6931"
        if len(args) == 1:
            return "/Sessions/3\n/Windows/2"
        if args[2] == "org.kde.konsole.Session.sendText":
            calls.append(args[3])
            if not allowed:
                raise RuntimeError("AccessDenied")
            return ""
        raise AssertionError("unexpected %s" % args[2])
    return run


def test_sending_is_allowed_when_the_probe_goes_through():
    calls = []
    assert konsole.can_send_text({6931}, _probe_bus(True, calls)) is True
    assert calls == [""]              # 아무것도 타이핑하지 않는 probe


def test_sending_is_refused_when_konsole_blocks_the_api():
    assert konsole.can_send_text({6931}, _probe_bus(False, [])) is False


def test_a_foreign_konsole_is_not_probed():
    assert konsole.can_send_text({999}, _probe_bus(True, [])) is False


def test_no_ancestors_means_no_probe():
    def run(*a):
        raise AssertionError("버스를 건드리면 안 된다")
    assert konsole.can_send_text(set(), run) is False


# ---------- 붙여넣기로 오해받지 않게 엔터를 떼어 보낸다 ----------

def test_the_text_can_be_sent_without_the_enter():
    # 코덱스 TUI 는 빠르게 들어온 입력을 붙여넣기로 보고, 그때 끝의 CR 은
    # 제출이 아니라 줄바꿈이 된다. 글자와 엔터를 떼어 보낼 수 있어야 한다.
    assert konsole.submit_text("안녕", submit=False) == "안녕"
    assert konsole.submit_text("안녕") == "안녕\r"


def test_send_text_can_leave_the_enter_for_later():
    sent = []
    base = _fake_bus(
        services=[" org.kde.konsole-6931"], paths=["/Sessions/3", "/Windows/1"],
        session_pid={"/Sessions/3": 22536}, window_sessions={"/Windows/1": [3]},
        calls=[])

    def run(*args):
        if len(args) > 2 and args[2] == "org.kde.konsole.Session.sendText":
            sent.append(args[3])
            return ""
        return base(*args)

    assert konsole.send_text({22536, 6931}, run, "안녕", submit=False) is True
    assert sent == ["안녕"]
    assert konsole.send_enter({22536, 6931}, run) is True
    assert sent == ["안녕", "\r"]
