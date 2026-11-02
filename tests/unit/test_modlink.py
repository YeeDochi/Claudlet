"""mod 링크: 펫이 쌓고, mod 가 읽고 ack 하고, 펫이 걷어낸다."""
import json

import pytest

from claudlet.core import modlink


@pytest.fixture(autouse=True)
def _runtime(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path))


def _lines(sid="s1"):
    with open(modlink.send_file(sid), encoding="utf-8") as f:
        return [json.loads(l) for l in f if l.strip()]


def _beat(tmp_path, ack, gone=False, sid="s1"):
    (tmp_path / "claudlet-{}.mod".format(sid)).write_text(
        json.dumps({"ack": ack, "ts": 1, "gone": gone}))


def test_no_heartbeat_means_no_mod():
    assert modlink.alive("s1") is False


def test_a_fresh_heartbeat_is_alive_and_a_goodbye_or_stale_one_is_not(tmp_path):
    _beat(tmp_path, 0)
    assert modlink.alive("s1")
    _beat(tmp_path, 0, gone=True)
    assert not modlink.alive("s1")
    assert not modlink.is_alive({}, mtime=0, now=modlink.FRESH_S + 1)


def test_pushed_lines_keep_order_with_increasing_ids():
    assert modlink.push("s1", "하나")
    assert modlink.push("s1", "둘", framed=True)
    a, b = _lines()
    assert (a["text"], b["text"]) == ("하나", "둘")
    assert b["id"] > a["id"] and b.get("framed") and "framed" not in a


def test_lines_the_mod_acked_are_dropped_on_the_next_push(tmp_path):
    modlink.push("s1", "하나")
    first = _lines()[0]["id"]
    _beat(tmp_path, first)                      # mod 가 넣었다
    modlink.push("s1", "둘")
    assert [m["text"] for m in _lines()] == ["둘"]
    assert _lines()[0]["id"] > first


def test_ids_stay_above_the_ack_even_if_the_clock_is_behind():
    assert modlink.next_id([], ack=5000, now_ms=10) == 5001
    assert modlink.next_id([{"id": 7}], ack=0, now_ms=3) == 8


def test_broken_lines_are_skipped():
    assert modlink.pending_lines('nope\n{"id": 3, "text": "a"}\n{"id": 1}', ack=2) \
        == [{"id": 3, "text": "a"}]


def test_empty_text_is_not_sent():
    assert modlink.push("s1", "") is None


def test_fork_lines_are_marked_and_answers_are_read_back(tmp_path):
    rid = modlink.push("s1", "뭐 해?", fork=True)
    assert _lines()[0]["fork"] is True and _lines()[0]["id"] == rid
    (tmp_path / "claudlet-s1.forked").write_text(
        json.dumps({"id": rid, "text": "SAY: 일해"}) + "\nbroken\n")
    assert modlink.forked("s1")[rid]["text"] == "SAY: 일해"


def test_said_lines_after_the_last_seen_one(tmp_path):
    (tmp_path / "claudlet-s1.said").write_text(
        "\n".join(json.dumps(m) for m in [{"id": 2, "text": "b"}, {"id": 1, "text": "a"}]))
    assert [m["text"] for m in modlink.said("s1")] == ["a", "b"]
    assert [m["text"] for m in modlink.said("s1", after=1)] == ["b"]
