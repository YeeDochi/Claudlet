"""Backend selection and the consent gate."""
import io
from claudlet.cli import askcli
from claudlet.platform.geom import win32


def test_win32_reports_whether_it_can_enumerate():
    # the bug this covers: askcli used getattr(win32,"available",...) and so
    # silently found no windows on Windows, because the function didn't exist
    assert hasattr(win32, "available")
    assert win32.available() in (True, False)


def test_win32_available_agrees_with_dump():
    # dump() guards on user32 being importable; available() must mirror it,
    # not answer a different question (like sys.platform)
    assert win32.available() == (win32.user32 is not None)


def test_macos_gets_the_ax_backend():
    assert askcli.text_backend("darwin").__name__.endswith("axtree")


def test_windows_gets_the_uia_backend():
    assert askcli.text_backend("win32").__name__.endswith("uiatree")


def test_other_platforms_get_no_backend():
    assert askcli.text_backend("linux") is None
    assert askcli.text_backend("freebsd7") is None


# ---------- history display ----------

import io
import os

import pytest

from claudlet.core import history as H


@pytest.fixture
def _cfg(tmp_path, monkeypatch):
    """Isolate BOTH stores this CLI touches.

    XDG_CONFIG_HOME alone is not enough: the mailbox lives under
    XDG_RUNTIME_DIR, so `--answer` reached the developer's real mailbox and a
    running pet picked it up and logged it. Found in real use -- "the reply"
    turned up in an actual conversation history.
    """
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path))
    return tmp_path


def _run(*argv):
    out = io.StringIO()
    code = askcli.main(list(argv), out=out)
    return code, out.getvalue()


def test_history_of_an_empty_log_says_so(_cfg):
    code, text = _run("--history")
    assert code == 1
    assert "기록된 대화가 없습니다" in text


def test_history_shows_question_and_answer(_cfg):
    H.record_question("default", "what is this?", "Safari", "page text")
    H.record_answer("default", "a wiki page")
    _, text = _run("--history")
    assert "what is this?" in text
    assert "a wiki page" in text
    assert "Safari" in text


def test_history_hides_the_screen_text_by_default(_cfg):
    H.record_question("default", "q", "Safari", "SECRET PAGE BODY")
    _, text = _run("--history")
    assert "SECRET PAGE BODY" not in text
    assert "--full" in text            # and says how to see it


def test_full_history_shows_the_screen_text(_cfg):
    H.record_question("default", "q", "Safari", "THE PAGE BODY")
    _, text = _run("--history", "--full")
    assert "THE PAGE BODY" in text


def test_an_unanswered_question_is_marked(_cfg):
    H.record_question("default", "q")
    _, text = _run("--history")
    assert "아직 없음" in text


def test_pending_only_lists_what_never_came_back(_cfg):
    H.record_question("default", "answered one")
    H.record_answer("default", "here you go")
    H.record_question("default", "orphan one")
    _, text = _run("--history", "--pending")
    assert "orphan one" in text
    assert "answered one" not in text


def test_history_is_scoped_to_the_session(_cfg):
    H.record_question("default", "mine")
    H.record_question("other", "theirs")
    _, text = _run("--history")
    assert "mine" in text and "theirs" not in text


def test_all_sessions_shows_everything(_cfg):
    H.record_question("default", "mine")
    H.record_question("other", "theirs")
    _, text = _run("--history", "--all-sessions")
    assert "mine" in text and "theirs" in text


def test_the_limit_is_honoured(_cfg):
    for i in range(5):
        H.record_question("default", "question%d" % i, now=1000.0 + i)
    _, text = _run("--history", "--limit", "2")
    assert "question4" in text and "question3" in text
    assert "question0" not in text


def test_clearing_history_reports_the_count(_cfg):
    H.record_question("default", "q")
    code, text = _run("--clear-history")
    assert code == 0 and "1건" in text
    assert H.load() == []


def test_clearing_only_touches_this_session(_cfg):
    H.record_question("default", "mine")
    H.record_question("other", "theirs")
    _run("--clear-history")
    assert [r["question"] for r in H.load()] == ["theirs"]


@pytest.mark.parametrize("secs,want", [
    (5, "방금"), (300, "5분 전"), (7200, "2시간 전"), (200000, "2일 전"),
])
def test_relative_times_read_naturally(secs, want):
    assert askcli._ago(1000.0, now=1000.0 + secs) == want


def test_sending_an_answer_does_not_log_it_here(_cfg):
    """The pet logs the answer when it shows it; doing it here too double-counts.

    Caught in real use: one reply appeared twice in the log because the CLI and
    the pet each recorded it.
    """
    H.record_question("default", "q")
    _run("--answer", "the reply")
    recs = H.load("default")
    assert len(recs) == 1
    assert recs[0]["answer"] is None      # still pending until the pet shows it


def test_the_cli_touches_neither_real_store(_cfg, monkeypatch):
    """Guard: both stores must be redirected, not just the config one.

    The mailbox lives under XDG_RUNTIME_DIR and the history under
    XDG_CONFIG_HOME. Isolating only the latter let a test answer land in the
    developer's real mailbox, where their running pet picked it up and wrote it
    into an actual conversation history.
    """
    from claudlet.core import ask, history
    _run("--answer", "isolated")
    assert str(_cfg) in ask.answer_path("default")
    assert str(_cfg) in history.history_path()


def test_pull_takes_what_the_pet_left_in_the_outbox(tmp_path, monkeypatch, capsys):
    # 질문은 한 곳(아웃박스)에만 쌓이고, 가져가는 길이 둘이다: 훅이 다음 경계에서
    # 자동으로, 또는 세션이 --pull 로 지금 당장. take() 가 한 번만 주므로
    # 어느 쪽이 먼저 가져가든 같은 질문이 두 번 가지 않는다.
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path))
    from claudlet.core import outbox
    outbox.append("s1", "이 창 뭐 하는 앱이야?")
    out = io.StringIO()
    assert askcli.main(["--pull", "--session", "s1"], out=out) == 0
    assert "이 창 뭐 하는 앱이야?" in out.getvalue()
    # 가져갔으면 훅에게는 남지 않는다
    assert outbox.take("s1") == []


def test_pull_says_so_when_nothing_is_waiting(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path))
    out = io.StringIO()
    assert askcli.main(["--pull", "--session", "s1"], out=out) == 1
    assert "없음" in out.getvalue()


def test_pull_hands_over_every_waiting_note_at_once(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path))
    from claudlet.core import outbox
    outbox.append("s1", "첫 질문")
    outbox.append("s1", "둘째 질문")
    out = io.StringIO()
    assert askcli.main(["--pull", "--session", "s1"], out=out) == 0
    text = out.getvalue()
    assert "첫 질문" in text and "둘째 질문" in text
