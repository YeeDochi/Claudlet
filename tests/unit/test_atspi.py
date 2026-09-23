"""리눅스 화면 읽기 백엔드 — 판정과 파싱은 데스크톱 없이 테스트한다."""
from claudlet.platform import atspi
from claudlet.platform.geom import Win


def _win(pid=4242):
    return Win("1", 0, 0, 800, 600, "konsole", pid, "Konsole")


def test_only_prefixed_lines_are_window_text():
    # 바인딩이 같은 스트림에 경고를 쓴다(deprecation, dbus 잡음). 경고는 창의
    # 글자가 아니다.
    out = atspi.parse_output(
        "DeprecationWarning: Atspi.Accessible.get_text is deprecated\n"
        "T:Claude Code v2.1.280\n"
        "T:❯ pkill -f claudlet\n"
        "(process:123): dbus-WARNING **: whatever\n")
    assert out == ["Claude Code v2.1.280", "❯ pkill -f claudlet"]


def test_a_window_is_matched_by_pid_not_title():
    # 같은 제목의 Konsole 창이 둘이면 제목으로는 못 고른다. 호출자는 이미 pid 를
    # 알고 있다.
    sent = {}

    def fake(argv, **kw):
        sent["argv"] = argv
        return "T:hello"

    atspi.read_window(_win(pid=777), run=fake)
    assert "777" in sent["argv"]


def test_a_window_with_no_pid_is_not_read():
    assert atspi.read_window(Win("1", 0, 0, 10, 10, "x", None, ""), run=None) is None


def test_nothing_to_read_is_none_not_a_crash():
    def dead(argv, **kw):
        raise OSError("atspi reader exited 4")

    assert atspi.read_window(_win(), run=dead) is None


def test_the_hint_tells_installing_apart_from_turning_on(monkeypatch):
    # 다 깔려 있는데 스위치가 꺼져 읽히지 않는 것과, 아예 못 읽는 것은 다른 일이다.
    monkeypatch.setattr(atspi, "_system_python", lambda: None)
    assert "apt install" in atspi.install_hint()

    monkeypatch.setattr(atspi, "_system_python", lambda: "/usr/bin/python3")
    monkeypatch.setattr(atspi, "trusted", lambda: False)
    assert "toolkit-accessibility" in atspi.install_hint()

    monkeypatch.setattr(atspi, "trusted", lambda: True)
    assert atspi.install_hint() == ""


def test_trusted_reads_the_session_switch():
    assert atspi.trusted(run=lambda: "b true") is True
    assert atspi.trusted(run=lambda: "b false") is False


def test_the_four_function_surface_matches_the_other_backends():
    # core/inspect.py 는 어느 OS 인지 몰라야 한다.
    for name in ("available", "trusted", "install_hint", "read_window"):
        assert callable(getattr(atspi, name))


def test_the_reader_skips_what_is_not_on_screen():
    # 접힌 도크 패널·뒤쪽 탭·숨은 검색바가 딸려 와서, 사용자가 보고 있지도 않은
    # 것이 질문에 실려 갔다(실사용 보고). 실측: 179줄 → 41줄.
    assert "STATE" in atspi.READ_PY or "SHOWING" in atspi.READ_PY


def test_the_reader_skips_the_app_furniture():
    # 메뉴가 190여 줄을 차지해 정작 화면 내용이 잘려 나갔다.
    assert "menu item" in atspi.READ_PY and "tool bar" in atspi.READ_PY
