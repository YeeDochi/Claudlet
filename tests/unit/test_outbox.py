"""펫이 에이전트에게 건네려고 쌓아둔 쪽지(아웃박스)."""
import json

import pytest

from claudlet.core import outbox


@pytest.fixture(autouse=True)
def _runtime(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path))


# ---------- 순수: 무엇이 에이전트에게 보이는가 ----------

def test_nothing_queued_means_no_hook_output():
    assert outbox.payload("UserPromptSubmit", []) is None


def test_a_note_rides_along_as_additional_context():
    p = outbox.payload("UserPromptSubmit", [{"text": "이거 왜 느려?"}])
    assert p["hookSpecificOutput"] == {
        "hookEventName": "UserPromptSubmit",
        "additionalContext": outbox.render([{"text": "이거 왜 느려?"}]),
    }


def test_the_rendered_note_says_where_it_came_from():
    # 에이전트가 이 문장을 사용자의 프롬프트로 착각하면 안 된다.
    text = outbox.render([{"text": "이거 왜 느려?"}])
    assert "이거 왜 느려?" in text
    assert "펫" in text


def test_every_queued_note_survives_into_one_context():
    text = outbox.render([{"text": "첫째"}, {"text": "둘째"}])
    assert "첫째" in text and "둘째" in text


def test_a_personality_line_rides_in_front_of_the_note():
    text = outbox.render([{"text": "안녕?", "persona": "짧고 퉁명스럽게"}])
    assert text.index("짧고 퉁명스럽게") < text.index("안녕?")


def test_the_same_note_carries_its_persona_only_once():
    text = outbox.render([{"text": "하나", "persona": "명랑하게"},
                          {"text": "둘", "persona": "명랑하게"}])
    assert text.count("명랑하게") == 1


# ---------- 파일: 펫이 쓰고 훅이 가져간다 ----------

def test_an_empty_outbox_hands_back_nothing():
    assert outbox.take("s1") == []


def test_what_the_pet_put_in_is_what_the_hook_takes_out():
    outbox.append("s1", "이거 왜 느려?")
    assert [n["text"] for n in outbox.take("s1")] == ["이거 왜 느려?"]


def test_taking_empties_it_so_a_note_is_delivered_once():
    outbox.append("s1", "한 번만")
    outbox.take("s1")
    assert outbox.take("s1") == []


def test_notes_keep_the_order_they_were_written_in():
    for t in ("하나", "둘", "셋"):
        outbox.append("s1", t)
    assert [n["text"] for n in outbox.take("s1")] == ["하나", "둘", "셋"]


def test_one_session_cannot_read_another_session_s_notes():
    outbox.append("s1", "비밀")
    assert outbox.take("s2") == []


def test_a_note_survives_a_newline(tmp_path):
    # 아웃박스는 한 줄에 한 쪽지라, 줄바꿈이 쪽지를 둘로 쪼개면 안 된다.
    outbox.append("s1", "첫 줄\n둘째 줄")
    assert [n["text"] for n in outbox.take("s1")] == ["첫 줄\n둘째 줄"]


def test_a_corrupt_line_does_not_hide_the_notes_around_it():
    path = outbox.outbox_file("s1")
    outbox.append("s1", "앞")
    with open(path, "a", encoding="utf-8") as f:
        f.write("{이건 JSON 이 아니다\n")
    outbox.append("s1", "뒤")
    assert [n["text"] for n in outbox.take("s1")] == ["앞", "뒤"]


def test_how_many_notes_are_waiting_without_taking_them():
    # 펫은 "쪽지를 물고 있다"를 그리려고 개수만 본다. 세는 것이 배달이 되면 안 된다.
    outbox.append("s1", "하나")
    assert outbox.pending("s1") == 1
    assert outbox.pending("s1") == 1
    assert len(outbox.take("s1")) == 1


def test_dropping_what_is_held_leaves_nothing_to_deliver():
    outbox.append("s1", "실수로 넣음")
    outbox.drop("s1")
    assert outbox.take("s1") == []


def test_a_note_is_stored_as_one_json_line():
    outbox.append("s1", "확인", persona="말투")
    with open(outbox.outbox_file("s1"), encoding="utf-8") as f:
        lines = f.read().splitlines()
    assert len(lines) == 1
    assert json.loads(lines[0])["text"] == "확인"


# ---------- 즉시 전송: 프롬프트에 그대로 찍히는 한 줄 ----------

def test_typed_line_carries_the_persona_where_the_user_can_see_it():
    # 터미널에 찍히는 문장이므로 숨길 수가 없다. 숨기지 않는 편이 정직하다.
    line = outbox.typed_line("이거 왜 느려?", "짧고 퉁명스럽게")
    assert "이거 왜 느려?" in line
    assert "짧고 퉁명스럽게" in line
    assert "\n" not in line


def test_typed_line_is_just_the_question_without_a_persona():
    assert outbox.typed_line("이거 왜 느려?", "") == "이거 왜 느려?"
    assert outbox.typed_line("이거 왜 느려?", None) == "이거 왜 느려?"


# ---------- 크리처의 답: 에이전트의 답과 분리된다 ----------

def test_the_agent_is_told_to_answer_in_the_creature_s_own_voice():
    text = outbox.render([{"text": "안녕?", "persona": "물컹하게"}])
    assert outbox.MARK_OPEN in text and outbox.MARK_CLOSE in text


def test_the_creature_line_is_pulled_out_of_a_reply():
    out = outbox.extract_reply(
        "고치는 중이야. 저기는 인덱스가 없어서 느렸어.\n"
        "<claudlet>느려터졌더라구우…</claudlet>")
    assert out == "느려터졌더라구우…"


def test_an_ordinary_reply_has_nothing_for_the_creature_to_say():
    assert outbox.extract_reply("그냥 평범한 답변이다") is None
    assert outbox.extract_reply("") is None
    assert outbox.extract_reply(None) is None


def test_only_the_last_creature_line_is_spoken():
    out = outbox.extract_reply("<claudlet>먼저</claudlet> 어쩌고 "
                               "<claudlet>나중</claudlet>")
    assert out == "나중"


def test_a_creature_line_is_kept_to_one_line_and_a_sane_length():
    out = outbox.extract_reply("<claudlet>%s</claudlet>" % ("가" * 300))
    assert len(out) <= outbox.SAY_MAX
    assert outbox.extract_reply("<claudlet>첫 줄\n둘째 줄</claudlet>") == "첫 줄 둘째 줄"


# ---------- transcript 에서 마지막 답을 찾는다 (포맷은 비공식이다) ----------

def test_the_last_assistant_line_is_what_the_creature_answers_to():
    lines = [
        json.dumps({"type": "user", "message": {"content": "안녕?"}}),
        json.dumps({"type": "assistant", "message": {"content": [
            {"type": "text", "text": "먼저 한 말"}]}}),
        json.dumps({"type": "assistant", "message": {"content": [
            {"type": "text", "text": "나중 한 말 <claudlet>물컹</claudlet>"}]}}),
    ]
    assert outbox.last_assistant_text(lines).endswith("</claudlet>")


def test_plain_string_content_is_read_too():
    lines = [json.dumps({"type": "assistant", "message": {"content": "문자열 답"}})]
    assert outbox.last_assistant_text(lines) == "문자열 답"


def test_a_transcript_we_cannot_read_says_nothing_rather_than_failing():
    # 비공식 JSONL 이라 언젠가 모양이 바뀐다. 그때는 말풍선만 안 뜨면 된다.
    assert outbox.last_assistant_text(["{깨진 줄", ""]) is None
    assert outbox.last_assistant_text([]) is None
    assert outbox.last_assistant_text(
        [json.dumps({"type": "user", "message": {"content": "나뿐"}})]) is None
