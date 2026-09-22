"""점검이 무엇을 말해주는가 — 판정과 문구는 데스크톱 없이 테스트된다."""
from claudlet.core import doctor


def test_nothing_wrong_says_so():
    out = doctor.render([("hooks", True, ""), ("konsole_send", True, "")])
    assert "전부 켜져" in out
    assert doctor.problems([("hooks", True, "")]) == []


def test_a_dead_switch_names_the_feature_it_blocks():
    # 핵심: "꺼져 있다" 로 끝나면 사용자는 그래서 뭐가 안 되는지 모른다.
    out = doctor.render([("konsole_send", False, "AccessDenied")])
    assert "지금 물어보기" in out          # 못 하게 되는 일
    assert "DBus API" in out               # 켜는 법
    assert "AccessDenied" in out           # 실제로 본 것


def test_several_switches_that_block_the_same_thing_are_listed_once():
    # AT-SPI 는 세 겹이라 다 꺼지면 같은 기능이 세 번 나온다 — 기능 목록은 한 번만.
    facts = [("atspi_daemon", False, ""), ("atspi_gi", False, ""),
             ("atspi_toolkit", False, "")]
    assert doctor.blocked_features(facts) == ["read_screen"]


def test_each_dead_switch_still_gets_its_own_fix():
    facts = [("atspi_gi", False, ""), ("atspi_toolkit", False, "")]
    out = doctor.render(facts)
    assert "python3-gi" in out and "toolkit-accessibility" in out


def test_java_windows_are_called_out_separately():
    out = doctor.render([("java_bridge", False, "")])
    assert "IntelliJ" in out
    assert "jabswitch" in out              # 윈도우 쪽 켜는 법도 같이


def test_english_is_a_full_translation_not_a_fallback():
    out = doctor.render([("atspi_toolkit", False, "")], lang="en")
    assert "toolkit-accessibility" in out
    assert "한글" not in out and "켜는" not in out


def test_an_unknown_fact_is_shown_but_blocks_nothing():
    # 새 점검을 추가하다 매핑을 빠뜨려도 보고서가 죽지는 않는다.
    facts = [("something_new", False, "")]
    assert doctor.problems(facts) == []
    assert "something_new" in doctor.render(facts)


# ---------- 찔러보는 쪽: 얇은지, 그리고 죽지 않는지 ----------

def test_a_check_that_blows_up_does_not_take_the_report_down():
    # 진단 도구가 진단하다 죽으면 고치려던 것보다 나쁘다.
    from claudlet.cli import doctorcli

    def boom():
        raise RuntimeError("bus is gone")

    facts = doctorcli.gather([("hooks", boom)])
    assert facts == [("hooks", False, "bus is gone")]


def test_checks_that_do_not_apply_here_are_left_out():
    # 리눅스에서 macOS 접근성 권한을 "꺼짐" 으로 보고하면 거짓말이다.
    from claudlet.cli import doctorcli
    facts = doctorcli.gather([("ax_trusted", lambda: (None, ""))])
    assert facts == []
