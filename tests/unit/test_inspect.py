"""What we would send, and what we would never send."""
import pytest

from claudlet.core import inspect as I
from claudlet.platform.geom import Win


def win(**kw):
    base = dict(wid=1, x=10, y=20, w=800, h=600, title="Mail", pid=42,
                caption="mail")
    base.update(kw)
    return Win(**base)


@pytest.mark.parametrize("raw,gone", [
    ("mail me at a.b@corp.com", "a.b@corp.com"),
    ("export T=ghp_abcdefghij1234567890abcd", "ghp_abcdefghij1234567890abcd"),
    ("password: hunter2", "hunter2"),
    ("api_key = sk-live-aaaaaaaaaaaaaaaaaaaa", "sk-live"),
    ("host 10.0.0.7 down", "10.0.0.7"),
    ("card 4111 1111 1111 1111", "4111"),
    ("sha 5d41402abc4b2a76b9719d911017c592", "5d41402abc4b2a76b9719d911017c592"),
])
def test_secrets_never_reach_the_preview(raw, gone):
    assert gone not in I.redact(raw)


def test_ordinary_text_survives():
    line = "Meeting with the platform team at 3pm"
    assert I.redact(line) == line


def test_context_without_a_reader_is_metadata_only():
    ctx = I.build_context(win(), "뭐야?")
    assert ctx["text"] == ""
    assert ctx["pid"] == 42
    assert "Mail" in ctx["target"]


def test_reader_failure_degrades_instead_of_raising():
    def boom(_):
        raise RuntimeError("no permission")
    ctx = I.build_context(win(), "뭐야?", read_text=boom)
    assert ctx["text"] == ""
    assert "RuntimeError" in ctx["note"]


def test_reader_returning_none_is_reported_as_no_access():
    ctx = I.build_context(win(), "뭐야?", read_text=lambda _: None)
    assert "accessibility" in ctx["note"]


def test_repeated_labels_collapse():
    ctx = I.build_context(win(), "q", read_text=lambda _: ["Inbox"] * 5)
    assert ctx["text"].count("Inbox") == 1


def test_long_lines_are_truncated():
    ctx = I.build_context(win(), "q", read_text=lambda _: ["x" * 5000])
    assert len(ctx["text"]) <= I.MAX_LINE + 4


def test_line_count_is_bounded():
    many = ["line %d" % i for i in range(1000)]
    ctx = I.build_context(win(), "q", read_text=lambda _: many)
    assert ctx["lines"] <= I.MAX_LINES + 1


def test_no_window_is_said_plainly():
    ctx = I.build_context(None, "뭐야?", read_text=lambda _: ["secret"])
    assert ctx["pid"] is None
    assert ctx["text"] == ""
    assert "no window" in ctx["target"]


def test_preview_states_when_nothing_is_sent():
    ctx = I.build_context(win(), "뭐야?")
    assert "창 정보만" in I.render_preview(ctx)


def test_preview_shows_the_text_that_would_be_sent():
    ctx = I.build_context(win(), "뭐야?", read_text=lambda _: ["Quarterly plan"])
    preview = I.render_preview(ctx)
    assert "Quarterly plan" in preview
    assert "뭐야?" in preview


def test_prompt_carries_question_and_target():
    ctx = I.build_context(win(), "이게 뭐야?", read_text=lambda _: ["Hello"])
    p = I.render_prompt(ctx)
    assert "이게 뭐야?" in p and "Mail" in p and "Hello" in p
