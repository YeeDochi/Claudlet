"""크리처 머리: 말 걸기를 본 세션 대신 크리처가 먼저 받는다.

진짜 `claude` 대신 PATH 앞에 둔 가짜 실행 파일로 머리를 흉내 낸다 — 무엇을 답할지는
가짜가 정하고, 테스트는 펫이 *보여주는 것*(snapshot 의 말풍선)과 본 세션에 *남은 것*
(아웃박스 쪽지)만 본다.
"""
import json
import os
import stat
import sys
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import pytest

from claudlet import pet as P
from claudlet.core import outbox

from harness import pet  # noqa: F401  (`pet` used as a fixture)

pytestmark = pytest.mark.skipif(os.name == "nt", reason="가짜 실행 파일이 sh 스크립트")


@pytest.fixture
def world(pet, tmp_path, monkeypatch):  # noqa: F811
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "cfg"))
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path / "run"))
    (tmp_path / "run").mkdir(exist_ok=True)
    (tmp_path / "bin").mkdir(exist_ok=True)
    monkeypatch.setenv("PATH", str(tmp_path / "bin") + os.pathsep + os.environ["PATH"])
    monkeypatch.setattr(pet, "_konsole_send", lambda t: False)   # 본 세션 = 쪽지
    yield tmp_path
    pet._brain_stop()
    outbox.drop(pet.session_id)


def _brain_on(tmp_path, on=True):
    from claudlet.core import petconfig
    with open(petconfig.config_path(), "w", encoding="utf-8") as f:
        json.dump({"pointer": {"brain": on}}, f)


def _fake_claude(tmp_path, body):
    exe = tmp_path / "bin" / "claude"
    exe.write_text("#!/bin/sh\n" + body + "\n")
    exe.chmod(exe.stat().st_mode | stat.S_IEXEC)
    return exe


def _wait(cond, secs=5.0):
    end = time.monotonic() + secs
    while time.monotonic() < end:
        P.QApplication.processEvents()
        if cond():
            return True
        time.sleep(0.02)
    return False


def _notes(pet):  # noqa: F811
    """본 세션에 넘어간 말 (말투 쪽지는 빼고)."""
    return [n["text"] for n in outbox.take(pet.session_id) if n.get("text")]


def test_small_talk_is_answered_by_the_creature_and_never_reaches_the_session(pet, world):  # noqa: F811
    _brain_on(world)
    _fake_claude(world, "cat >/dev/null; echo 'SAY: 응 지금 테스트 돌리는 중~'")
    pet._talk(immediate=True, text="지금 뭐 해?")
    assert _wait(lambda: pet.snapshot()["saying"])
    assert pet.snapshot()["saying"] == "응 지금 테스트 돌리는 중~"
    assert _notes(pet) == []


def test_work_is_relayed_to_the_session(pet, world):  # noqa: F811
    _brain_on(world)
    _fake_claude(world, "cat >/dev/null; printf 'SAY: 알았어 전할게\\nRELAY: 로그인 테스트 고쳐줘\\n'")
    pet._talk(immediate=True, text="로그인 테스트 좀 고쳐달라고 해줘")
    assert _wait(lambda: pet.snapshot()["saying"])
    assert pet.snapshot()["saying"] == "알았어 전할게"
    assert _notes(pet) == ["로그인 테스트 고쳐줘"]


def test_the_creature_sees_what_the_user_said(pet, world):  # noqa: F811
    _brain_on(world)
    seen = world / "stdin.txt"
    _fake_claude(world, "cat >'%s'; echo 'SAY: 들었어'" % seen)
    pet._talk(immediate=True, text="오늘 점심 뭐 먹지")
    assert _wait(lambda: pet.snapshot()["saying"])
    assert "오늘 점심 뭐 먹지" in seen.read_text()


def test_a_failing_brain_hands_the_words_to_the_session(pet, world):  # noqa: F811
    _brain_on(world)
    _fake_claude(world, "cat >/dev/null; exit 3")
    pet._talk(immediate=True, text="들리나?")
    assert _wait(lambda: not pet._brain_busy())
    assert _notes(pet) == ["들리나?"]


def test_no_agent_cli_hands_the_words_to_the_session(pet, world, monkeypatch):  # noqa: F811
    _brain_on(world)
    monkeypatch.setattr(P.shutil, "which", lambda name: None)
    pet._talk(immediate=True, text="거기 있어?")
    assert _notes(pet) == ["거기 있어?"]


def test_a_hung_brain_times_out_to_the_session(pet, world, monkeypatch):  # noqa: F811
    _brain_on(world)
    monkeypatch.setattr(pet, "BRAIN_TIMEOUT_S", 0.3)
    _fake_claude(world, "sleep 30")
    pet._talk(immediate=True, text="왜 대답이 없어")
    assert _wait(lambda: not pet._brain_busy(), secs=5)
    assert _notes(pet) == ["왜 대답이 없어"]


def test_speaking_again_answers_both(pet, world):  # noqa: F811
    # 앞의 생각을 죽였더니 앞의 말이 답도 못 받고 본 세션에도 안 가서 사라졌다.
    from claudlet.core import history as H
    _brain_on(world)
    _fake_claude(world, 'line=$(sed -n "/## The user says/{n;p;}"); sleep 0.3; echo "SAY: $line 들었어"')
    pet._talk(immediate=True, text="첫번째")
    pet._talk(immediate=True, text="두번째")
    assert _wait(lambda: not pet._brain_busy())
    got = {r["question"]: r["answer"] for r in H.load(pet.session_id)}
    assert got == {"첫번째": "첫번째 들었어", "두번째": "두번째 들었어"}


def test_the_sessions_own_reply_does_not_take_the_creatures_question(pet, world):  # noqa: F811
    # 크리처가 생각하는 동안 본 세션이 자기 턴을 끝내도, 그 답이 크리처에게 한
    # 질문에 붙거나 말풍선으로 뜨면 안 된다.
    from claudlet.core import history as H
    _brain_on(world)
    _fake_claude(world, "cat >/dev/null; sleep 0.3; echo 'SAY: 내 답'")
    pet._talk(immediate=True, text="안녕")
    assert H.load(pet.session_id, pending_only=True) == []   # 본 세션 몫이 아니다
    H.record_answer(pet.session_id, "본 세션이 한 말")         # turn_end 가 하는 일
    assert _wait(lambda: not pet._brain_busy())
    mine = [r for r in H.load(pet.session_id) if r["question"] == "안녕"]
    assert mine and mine[0]["answer"] == "내 답"


def test_a_failed_brain_question_waits_for_the_sessions_answer(pet, world):  # noqa: F811
    from claudlet.core import history as H
    _brain_on(world)
    _fake_claude(world, "cat >/dev/null; exit 1")
    pet._talk(immediate=True, text="넘어가라")
    assert _wait(lambda: not pet._brain_busy())
    assert [r["question"] for r in H.load(pet.session_id, pending_only=True)] == ["넘어가라"]


def test_a_blank_answer_hands_the_words_to_the_session(pet, world):  # noqa: F811
    _brain_on(world)
    _fake_claude(world, "cat >/dev/null; echo 'SAY:'")
    pet._talk(immediate=True, text="뭐라고?")
    assert _wait(lambda: not pet._brain_busy())
    assert _notes(pet) == ["뭐라고?"]


def test_brain_off_keeps_the_old_path(pet, world):  # noqa: F811
    _brain_on(world, on=False)
    _fake_claude(world, "echo 'SAY: 나오면 안 됨'")
    pet._talk(immediate=True, text="그냥 세션에")
    assert _notes(pet) == ["그냥 세션에"]


def test_a_note_skips_the_brain(pet, world):  # noqa: F811
    _brain_on(world)
    _fake_claude(world, "echo 'SAY: 나오면 안 됨'")
    pet._talk(immediate=False, text="나중에 봐")
    assert _notes(pet) == ["나중에 봐"]
    assert not pet._brain_busy()


def test_pointing_at_a_window_asks_the_creature_with_what_it_reads(pet, world, monkeypatch):  # noqa: F811
    from claudlet.platform.geom import Win
    _brain_on(world)
    seen = world / "stdin.txt"
    _fake_claude(world, "cat >'%s'; echo 'SAY: 그건 원장 창이야'" % seen)
    monkeypatch.setattr(pet, "_ask_backend", lambda: None)
    pet.ask_window(Win(wid=1, x=100, y=100, w=400, h=300, title="Ledger", pid=7,
                       caption="ledger"), "이거 뭐야?")
    assert _wait(lambda: pet.snapshot()["saying"])
    assert pet.snapshot()["saying"] == "그건 원장 창이야"
    assert "Ledger" in seen.read_text() and "이거 뭐야?" in seen.read_text()
    assert _notes(pet) == []


def test_a_failed_pointer_question_still_carries_the_window(pet, world, monkeypatch):  # noqa: F811
    from claudlet.platform.geom import Win
    _brain_on(world)
    _fake_claude(world, "cat >/dev/null; exit 1")
    monkeypatch.setattr(pet, "_ask_backend", lambda: None)
    pet.ask_window(Win(wid=1, x=100, y=100, w=400, h=300, title="Ledger", pid=7,
                       caption="ledger"), "이거 뭐야?")
    assert _wait(lambda: not pet._brain_busy())
    notes = _notes(pet)
    assert notes and "Ledger" in notes[0] and "이거 뭐야?" in notes[0]
