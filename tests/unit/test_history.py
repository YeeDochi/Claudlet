"""The durable log of what was asked and answered."""
import json
import os
import stat

import pytest

from claudlet.core import history as H


@pytest.fixture(autouse=True)
def _cfg(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    return tmp_path


def test_a_question_round_trips():
    H.record_question("s1", "what is this?", "Safari", "page text")
    rec = H.load("s1")[0]
    assert rec["question"] == "what is this?"
    assert rec["target"] == "Safari"
    assert rec["text"] == "page text"


def test_a_new_question_has_no_answer_yet():
    H.record_question("s1", "q")
    assert H.load("s1")[0]["answer"] is None


def test_an_answer_attaches_to_the_pending_question():
    H.record_question("s1", "q")
    H.record_answer("s1", "a")
    recs = H.load("s1")
    assert len(recs) == 1                 # one exchange, not two rows
    assert recs[0]["answer"] == "a"
    assert recs[0]["answered_ts"] is not None


def test_an_answer_attaches_to_the_newest_pending_one():
    H.record_question("s1", "first")
    H.record_question("s1", "second")
    H.record_answer("s1", "reply")
    by_q = {r["question"]: r["answer"] for r in H.load("s1")}
    assert by_q["second"] == "reply"
    assert by_q["first"] is None


def test_an_answer_can_target_a_specific_exchange():
    first = H.record_question("s1", "first")
    H.record_question("s1", "second")
    H.record_answer("s1", "reply", rec_id=first)
    by_q = {r["question"]: r["answer"] for r in H.load("s1")}
    assert by_q["first"] == "reply"
    assert by_q["second"] is None


def test_an_orphan_answer_is_still_logged():
    """Evidence that something arrived is what "did it ever reply?" needs."""
    H.record_answer("s1", "out of nowhere")
    recs = H.load("s1")
    assert len(recs) == 1
    assert recs[0]["answer"] == "out of nowhere"


def test_records_come_back_newest_first():
    H.record_question("s1", "old", now=1000.0)
    H.record_question("s1", "new", now=2000.0)
    assert [r["question"] for r in H.load("s1")] == ["new", "old"]


def test_sessions_are_kept_apart():
    H.record_question("a", "for a")
    H.record_question("b", "for b")
    assert [r["question"] for r in H.load("a")] == ["for a"]
    assert [r["question"] for r in H.load("b")] == ["for b"]


def test_loading_every_session_at_once():
    H.record_question("a", "for a")
    H.record_question("b", "for b")
    assert len(H.load()) == 2


def test_pending_only_hides_answered_exchanges():
    H.record_question("s1", "answered")
    H.record_answer("s1", "yes")
    H.record_question("s1", "still waiting")
    pending = H.load("s1", pending_only=True)
    assert [r["question"] for r in pending] == ["still waiting"]


def test_limit_takes_the_newest():
    for i in range(5):
        H.record_question("s1", "q%d" % i, now=1000.0 + i)
    assert [r["question"] for r in H.load("s1", limit=2)] == ["q4", "q3"]


def test_the_log_is_capped():
    for i in range(H.MAX_RECORDS + 20):
        H.record_question("s1", "q%d" % i, now=1000.0 + i)
    assert len(H.load("s1")) == H.MAX_RECORDS


def test_capping_keeps_the_newest():
    for i in range(H.MAX_RECORDS + 5):
        H.record_question("s1", "q%d" % i, now=1000.0 + i)
    assert H.load("s1")[0]["question"] == "q%d" % (H.MAX_RECORDS + 4)


def test_long_screen_text_is_clipped():
    H.record_question("s1", "q", text="x" * (H.MAX_TEXT * 2))
    assert len(H.load("s1")[0]["text"]) < H.MAX_TEXT * 2


def test_the_region_is_kept_when_there_was_one():
    H.record_question("s1", "q", region={"x": 1, "y": 2, "w": 3, "h": 4})
    assert H.load("s1")[0]["region"] == {"x": 1.0, "y": 2.0, "w": 3.0, "h": 4.0}


def test_no_region_key_when_the_whole_window_was_read():
    H.record_question("s1", "q")
    assert "region" not in H.load("s1")[0]


def test_the_file_is_private():
    H.record_question("s1", "q")
    mode = stat.S_IMODE(os.stat(H.history_path()).st_mode)
    assert mode == 0o600


def test_a_missing_log_reads_as_empty():
    assert H.load() == []


def test_a_torn_line_costs_one_record_not_the_log():
    H.record_question("s1", "good one")
    with open(H.history_path(), "a", encoding="utf-8") as f:
        f.write('{"half written\n')
    H.record_question("s1", "after the tear")
    questions = [r["question"] for r in H.load("s1")]
    assert "good one" in questions and "after the tear" in questions


def test_a_non_dict_line_is_skipped():
    H.record_question("s1", "real")
    with open(H.history_path(), "a", encoding="utf-8") as f:
        f.write(json.dumps([1, 2, 3]) + "\n")
    assert [r["question"] for r in H.load("s1")] == ["real"]


def test_clearing_one_session_leaves_the_others():
    H.record_question("a", "for a")
    H.record_question("b", "for b")
    assert H.clear("a") == 1
    assert [r["question"] for r in H.load()] == ["for b"]


def test_clearing_everything():
    H.record_question("a", "one")
    H.record_question("b", "two")
    assert H.clear() == 2
    assert H.load() == []


def test_clearing_an_empty_log_is_harmless():
    assert H.clear() == 0


def test_unicode_survives():
    H.record_question("s1", "이 창 뭐야? 🐾", target="사파리")
    rec = H.load("s1")[0]
    assert rec["question"] == "이 창 뭐야? 🐾"
    assert rec["target"] == "사파리"


def test_no_temp_files_are_left_behind(_cfg):
    for i in range(3):
        H.record_question("s1", "q%d" % i)
    H.record_answer("s1", "a")
    d = os.path.dirname(H.history_path())
    assert not [p for p in os.listdir(d) if p.endswith(".tmp")]


# ---------- rendering ----------

@pytest.mark.parametrize("secs,want", [
    (5, "방금"), (300, "5분 전"), (7200, "2시간 전"), (200000, "2일 전"),
])
def test_relative_times_read_naturally(secs, want):
    assert H.ago(1000.0, now=1000.0 + secs) == want


@pytest.mark.parametrize("secs,want", [
    (5, "just now"), (300, "5m ago"), (7200, "2h ago"), (200000, "2d ago"),
])
def test_relative_times_in_english(secs, want):
    assert H.ago(1000.0, now=1000.0 + secs, lang="en") == want


def test_an_empty_log_renders_a_message():
    assert "아직" in H.render_html([])


def test_an_empty_log_renders_in_english():
    assert "No conversations" in H.render_html([], lang="en")


def test_a_question_and_answer_both_appear():
    html = H.render_html([{"ts": 0, "question": "what?", "answer": "this"}],
                         now=0)
    assert "what?" in html and "this" in html


def test_an_unanswered_exchange_says_it_is_waiting():
    html = H.render_html([{"ts": 0, "question": "q", "answer": None}], now=0)
    assert "기다리" in html


def test_the_screen_text_is_hidden_by_default():
    html = H.render_html([{"ts": 0, "question": "q", "text": "PAGE BODY"}],
                         now=0)
    assert "PAGE BODY" not in html


def test_the_screen_text_appears_in_full_mode():
    html = H.render_html([{"ts": 0, "question": "q", "text": "PAGE BODY"}],
                         full=True, now=0)
    assert "PAGE BODY" in html


def test_markup_in_a_record_cannot_reach_the_page():
    """Records hold text scraped off the user's screen; it is data, not markup."""
    html = H.render_html([{"ts": 0, "question": "<b>bold</b>",
                           "answer": "a & b", "target": "<script>x</script>"}],
                         now=0)
    assert "<b>bold</b>" not in html
    assert "&lt;b&gt;" in html
    assert "<script>" not in html
    assert "&amp;" in html


def test_markup_in_the_screen_text_is_escaped_too():
    html = H.render_html([{"ts": 0, "text": "<img src=x>"}], full=True, now=0)
    assert "<img src=x>" not in html


def test_the_target_window_is_shown():
    html = H.render_html([{"ts": 0, "question": "q", "target": "Safari"}], now=0)
    assert "Safari" in html
