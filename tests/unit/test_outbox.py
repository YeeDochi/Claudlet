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


# ---------- 즉시 전송: 프롬프트에는 질문만 찍힌다 ----------

def test_only_the_question_is_typed_into_the_prompt():
    # 말투 지시가 프롬프트 줄에 찍히면 사용자 눈에 계속 밟힌다. 그것은 훅으로
    # 따로 들어간다 — 즉시 전송도 UserPromptSubmit 을 발동시키므로 같은 턴에 닿는다.
    assert outbox.typed_line("이거 왜 느려?", "짧고 퉁명스럽게") == "이거 왜 느려?"
    assert outbox.typed_line("이거 왜 느려?", None) == "이거 왜 느려?"


def test_a_voice_note_carries_the_persona_without_repeating_a_message():
    outbox.append_voice("s1", "물컹하게")
    text = outbox.render(outbox.take("s1"))
    assert "물컹하게" in text
    assert outbox.MARK in text               # 크리처 목소리로 답하라는 요청은 그대로
    assert "- " not in text                  # 사용자가 한 말을 지어내지는 않는다


def test_a_voice_note_alone_does_not_claim_the_user_said_something():
    outbox.append_voice("s1", "물컹하게")
    assert outbox.HEADER not in outbox.render(outbox.take("s1"))


def test_a_voice_note_and_a_whisper_together_read_as_one_message():
    outbox.append_voice("s1", "물컹하게")
    outbox.append("s1", "이거 왜 느려?")
    text = outbox.render(outbox.take("s1"))
    assert outbox.HEADER in text and "- 이거 왜 느려?" in text
    assert text.count("물컹하게") == 1


# ---------- 크리처의 답: 에이전트의 답과 분리된다 ----------

def test_the_agent_is_told_to_answer_in_the_creature_s_own_voice():
    text = outbox.render([{"text": "안녕?", "persona": "물컹하게"}])
    assert outbox.MARK in text


def test_the_creature_line_is_pulled_out_of_a_reply():
    out = outbox.extract_reply(
        "고치는 중이야. 저기는 인덱스가 없어서 느렸어.\n"
        "🗨 느려터졌더라구우…")
    assert out == "느려터졌더라구우…"


def test_the_marker_reads_as_a_line_a_human_wrote_not_as_markup():
    # 이 줄은 터미널에 그대로 보인다. XML 태그가 보이면 사용자는 마크업을 읽는다.
    assert "<" not in outbox.MARK and ">" not in outbox.MARK


def test_the_pet_name_prefix_is_not_spoken_twice():
    # 터미널에서는 "🗨 라임: ..." 가 자연스럽지만 말풍선에 이름까지 넣을 이유는 없다
    assert outbox.extract_reply("🗨 라임: 물컹하다아") == "물컹하다아"


def test_an_ordinary_reply_has_nothing_for_the_creature_to_say():
    assert outbox.extract_reply("그냥 평범한 답변이다") is None
    assert outbox.extract_reply("") is None
    assert outbox.extract_reply(None) is None


def test_only_the_last_creature_line_is_spoken():
    out = outbox.extract_reply("🗨 먼저\n어쩌고\n🗨 나중")
    assert out == "나중"


def test_a_creature_line_is_kept_to_a_sane_length():
    assert len(outbox.extract_reply("🗨 " + "가" * 300)) <= outbox.SAY_MAX


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


def test_the_pet_does_not_hold_up_its_own_plumbing_as_a_note():
    # 말투 쪽지는 내부 배관이다. 쪽지를 문 그림은 "네 말을 들고 있다"는 뜻이라야 한다.
    outbox.append_voice("s1", "물컹하게")
    assert outbox.pending("s1") == 0
    outbox.append("s1", "이거 왜 느려?")
    assert outbox.pending("s1") == 1


# ---------- 이름: 펫이 제 이름을 안다 ----------

def test_the_agent_is_told_what_the_pet_is_called():
    outbox.append("s1", "안녕 라임아", persona="물컹하게", nickname="라임")
    text = outbox.render(outbox.take("s1"))
    assert "라임" in text


def test_the_name_rides_with_a_voice_note_too():
    outbox.append_voice("s1", "물컹하게", nickname="라임")
    text = outbox.render(outbox.take("s1"))
    assert "라임" in text and "물컹하게" in text


def test_a_nameless_pet_says_nothing_about_a_name():
    outbox.append("s1", "안녕", persona="물컹하게")
    text = outbox.render(outbox.take("s1"))
    assert "이름" not in text


def test_small_talk_to_the_pet_is_not_a_task_for_the_agent():
    # 펫에게 건 잡담에 에이전트가 업무 답변까지 얹으면 두 번 답하는 꼴이 된다.
    text = outbox.render([{"text": "안녕", "persona": "물컹하게"}])
    assert "잡담" in text and "그 한 줄만" in text


def test_a_real_request_through_the_pet_still_gets_done():
    text = outbox.render([{"text": "이거 고쳐줘"}])
    assert "작업" in text


def test_a_codex_rollout_is_read_too():
    # Codex 는 다른 모양으로 적는다: payload.type=="message", content[].output_text
    lines = [json.dumps({"type": "response_item", "payload": {
        "type": "message", "role": "assistant",
        "content": [{"type": "output_text", "text": "확인했습니다.\n🗨 됐다 아이가"}]}})]
    assert outbox.extract_reply(outbox.last_assistant_text(lines)) == "됐다 아이가"


def test_a_codex_user_turn_is_not_mistaken_for_an_answer():
    lines = [json.dumps({"type": "response_item", "payload": {
        "type": "message", "role": "user",
        "content": [{"type": "input_text", "text": "안녕"}]}})]
    assert outbox.last_assistant_text(lines) is None
