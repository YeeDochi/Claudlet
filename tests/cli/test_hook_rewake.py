"""놀고 있는 세션을 깨우는 waiter (asyncRewake 훅)."""
import pytest

from claudlet.cli import hook
from claudlet.core import outbox


@pytest.fixture(autouse=True)
def _runtime(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path))


def _wait(session, ticks=5, on_tick=None):
    n = {"i": 0}

    def sleep(_):
        n["i"] += 1
        if on_tick:
            on_tick(n["i"])
    return hook.rewake_wait(session, sleep=sleep, alive=lambda: n["i"] < ticks)


def test_a_wake_hands_the_notes_to_the_session_and_exits_2(capsys):
    outbox.append("s1", "지금 뭐 해?", persona="반말")
    outbox.wake("s1")
    assert _wait("s1") == 2
    err = capsys.readouterr().err
    assert "지금 뭐 해?" in err and "말투: 반말" in err
    assert outbox.take("s1") == []                  # 한 번만 배달된다


def test_a_note_left_for_later_does_not_wake(capsys):
    outbox.append("s1", "나중에 봐")
    assert _wait("s1") == 0
    assert capsys.readouterr().err == ""
    assert [n["text"] for n in outbox.take("s1")] == ["나중에 봐"]


def test_a_wake_arriving_while_waiting_is_picked_up(capsys):
    def later(i):
        if i == 2:
            outbox.append("s1", "이제 왔어")
            outbox.wake("s1")
    assert _wait("s1", ticks=10, on_tick=later) == 2
    assert "이제 왔어" in capsys.readouterr().err


def test_an_older_waiter_steps_aside_for_the_next_one():
    def replaced(i):
        outbox.claim_waiter("s1", -1)               # 다음 Stop 의 waiter
        outbox.append("s1", "x")
        outbox.wake("s1")
    assert _wait("s1", ticks=10, on_tick=replaced) == 0
    assert outbox.wants_wake("s1")                  # 새 주인 몫으로 남는다


def test_a_codex_session_that_missed_its_start_gets_a_pet_on_the_next_event():
    # 코덱스 CLI 는 첫 메시지 전까지 rollout 이 없어 SessionStart 에서 걸러졌다
    assert hook.should_launch_late("codex", "UserPromptSubmit", False, True)
    assert hook.should_launch_late("codex", "PreToolUse", False, True)


def test_a_pet_the_user_closed_is_not_brought_back():
    assert not hook.should_launch_late("codex", "PreToolUse", True, True)


def test_a_tool_worker_without_a_rollout_still_gets_no_pet():
    assert not hook.should_launch_late("codex", "PreToolUse", False, False)
    assert not hook.should_launch_late("codex", "SessionEnd", False, True)
    assert not hook.should_launch_late("claude", "PreToolUse", False, True)
