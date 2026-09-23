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


# ---------- 켜주기: 무엇을 우리가 켤 수 있고 무엇은 못 켜나 ----------

def test_we_can_turn_on_what_belongs_to_the_user():
    # 사용자 자기 설정이고 되돌리기 쉬운 것만 우리가 켠다.
    assert doctor.fix_command("atspi_toolkit")
    assert doctor.fix_command("java_bridge")
    assert doctor.fix_command("hooks")


def test_we_do_not_touch_what_is_not_ours_to_touch():
    # apt 설치(sudo)와 Konsole 의 보안 스위치는 사용자가 직접 결정할 일이다.
    assert doctor.fix_command("atspi_gi") is None
    assert doctor.fix_command("konsole_send") is None
    assert doctor.fix_command("ax_trusted") is None


def test_turning_something_on_comes_with_how_to_undo_it():
    # 남의 데스크톱 전역 설정을 건드리는 것이니, 끄는 법을 같이 보여준다.
    assert "false" in " ".join(doctor.undo_command("atspi_toolkit"))


def test_the_offer_says_what_it_will_run():
    ask = doctor.offer_text("atspi_toolkit", "ko")
    assert "toolkit-accessibility true" in ask     # 실행할 명령 그대로
    assert "포인터" in ask or "글자" in ask         # 그래서 되는 일


def test_appending_the_java_line_is_idempotent(tmp_path, monkeypatch):
    from claudlet.cli import doctorcli
    prop = tmp_path / ".accessibility.properties"
    monkeypatch.setattr(doctorcli.os.path, "expanduser",
                        lambda p: str(prop) if p.startswith("~/.access") else p)
    assert doctorcli.apply_fix("java_bridge") is True
    assert doctorcli.apply_fix("java_bridge") is True          # 두 번 켜도 한 줄
    assert prop.read_text(encoding="utf-8").count("AtkWrapper") == 1


def test_a_fix_we_do_not_own_is_refused():
    from claudlet.cli import doctorcli
    assert doctorcli.apply_fix("atspi_gi") is False            # sudo 는 우리 몫이 아니다
