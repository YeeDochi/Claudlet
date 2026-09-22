"""The question mailbox: one-shot delivery, atomic writes, no stale answers."""
import json
import os

import pytest

from claudlet.core import ask


@pytest.fixture(autouse=True)
def _runtime(tmp_path, monkeypatch):
    monkeypatch.setattr(ask.hostinfo, "runtime_dir", lambda: str(tmp_path))
    return tmp_path


def test_question_round_trips():
    ask.post_question("s1", "why is the sky blue", "Safari")
    got = ask.take_question("s1")
    assert got["prompt"] == "why is the sky blue"
    assert got["target"] == "Safari"


def test_a_question_is_delivered_once():
    ask.post_question("s1", "q")
    assert ask.take_question("s1") is not None
    assert ask.take_question("s1") is None


def test_answer_round_trips_and_clears():
    ask.post_answer("s1", "because of rayleigh scattering")
    assert ask.take_answer("s1") == "because of rayleigh scattering"
    assert ask.take_answer("s1") is None


def test_a_stale_question_is_not_delivered():
    ask.post_question("s1", "q", now=1000.0)
    assert ask.take_question("s1", now=1000.0 + ask.TTL + 1) is None


def test_a_fresh_question_is_delivered():
    ask.post_question("s1", "q", now=1000.0)
    assert ask.take_question("s1", now=1000.0 + 1) is not None


def test_missing_mailbox_is_not_an_error():
    assert ask.take_question("never") is None
    assert ask.take_answer("never") is None


def test_corrupt_mailbox_is_not_an_error(_runtime):
    with open(ask.ask_path("s1"), "w") as f:
        f.write("{not json")
    assert ask.take_question("s1") is None


def test_non_dict_payload_is_rejected(_runtime):
    with open(ask.ask_path("s1"), "w") as f:
        json.dump([1, 2, 3], f)
    assert ask.take_question("s1") is None


def test_clear_removes_both_sides():
    ask.post_question("s1", "q")
    ask.post_answer("s1", "a")
    ask.clear("s1")
    assert not os.path.exists(ask.ask_path("s1"))
    assert not os.path.exists(ask.answer_path("s1"))


def test_sessions_do_not_share_a_mailbox():
    ask.post_question("a", "for a")
    ask.post_question("b", "for b")
    assert ask.take_question("a")["prompt"] == "for a"
    assert ask.take_question("b")["prompt"] == "for b"


def test_no_temp_files_are_left_behind(_runtime):
    ask.post_question("s1", "q")
    ask.post_answer("s1", "a")
    assert not [p for p in os.listdir(str(_runtime)) if p.endswith(".tmp")]


def test_unicode_survives_the_round_trip():
    ask.post_question("s1", "이 창 뭐야? 🐾")
    assert ask.take_question("s1")["prompt"] == "이 창 뭐야? 🐾"
