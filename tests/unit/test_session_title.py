"""The name Claude Code gives a session, read back out of its transcript.

It is what the pet's hover tooltip says, because the session id means nothing
to a person. Written as JSON lines: {"type":"ai-title","aiTitle":"..."}.
"""
import json

from claudlet.core import hostinfo as H


def _transcript(root, project, session_id, records):
    d = root / project
    d.mkdir(parents=True, exist_ok=True)
    f = d / ("%s.jsonl" % session_id)
    f.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in records)
                 + "\n", encoding="utf-8")
    return f


def test_reads_the_title(tmp_path):
    _transcript(tmp_path, "-home-me-proj", "s1", [
        {"type": "user", "message": {"content": "hi"}},
        {"type": "ai-title", "aiTitle": "펫 클릭 포커스 고치기", "sessionId": "s1"},
    ])
    assert H.session_title("s1", root=str(tmp_path)) == "펫 클릭 포커스 고치기"


def test_last_title_wins(tmp_path):
    # the title is re-emitted (and can change) as the conversation goes on
    _transcript(tmp_path, "-p", "s2", [
        {"type": "ai-title", "aiTitle": "처음 제목", "sessionId": "s2"},
        {"type": "ai-title", "aiTitle": "나중 제목", "sessionId": "s2"},
    ])
    assert H.session_title("s2", root=str(tmp_path)) == "나중 제목"


def test_no_title_yet_is_empty(tmp_path):
    # before the first exchange Claude Code hasn't named the session
    _transcript(tmp_path, "-p", "s3", [{"type": "user", "message": {}}])
    assert H.session_title("s3", root=str(tmp_path)) == ""


def test_missing_transcript_is_empty(tmp_path):
    assert H.session_title("nope", root=str(tmp_path)) == ""
    assert H.session_title("", root=str(tmp_path)) == ""
    assert H.transcript_path("nope", root=str(tmp_path)) is None


def test_a_line_cut_in_half_by_the_tail_seek_is_skipped(tmp_path):
    # only the tail is read, so the first line read is usually a fragment;
    # it must not take the whole read down
    _transcript(tmp_path, "-p", "s4", [
        {"type": "ai-title", "aiTitle": "x" * 400, "sessionId": "s4"},
        {"type": "ai-title", "aiTitle": "끝 제목", "sessionId": "s4"},
    ])
    assert H.session_title("s4", root=str(tmp_path), tail=120) == "끝 제목"


def test_a_huge_transcript_still_finds_the_title(tmp_path):
    noise = [{"type": "assistant", "message": {"content": "z" * 200}}
             for _ in range(500)]
    _transcript(tmp_path, "-p", "s5",
                [{"type": "ai-title", "aiTitle": "묻힌 제목", "sessionId": "s5"}]
                + noise
                + [{"type": "ai-title", "aiTitle": "최근 제목", "sessionId": "s5"}])
    assert H.session_title("s5", root=str(tmp_path)) == "최근 제목"
