"""아웃박스 — 펫이 에이전트에게 건네려고 쌓아둔 쪽지.

claudlet 은 오랫동안 완전한 단방향이었다(훅 -> 펫). 이것이 반대 방향의
유일한 통로다. 그리고 **파일**이다 — 훅이 펫에게 소켓으로 되묻지 않는다.
훅은 절대 블록하거나 실패하면 안 되는데, 펫이 페인팅 중이면 수십 ms 가
수백 ms 가 되기 때문이다. 펫이 쓰고, 훅은 파일 하나 읽고 끝낸다.
펫이 죽어 있어도 훅은 멀쩡하다.

`.port` 파일과 같은 디렉터리에 세션마다 하나 (`hostinfo.runtime_dir`).
한 줄에 쪽지 하나(JSON), 그래서 쓰는 쪽은 append 한 번으로 끝난다.

배달은 `PostToolUse` 와 `UserPromptSubmit` 두 훅 경계에서 일어난다. 에이전트가
일하는 중이면 다음 툴콜에서, 놀고 있었으면 다음 프롬프트에서 도착한다.
"""
import json
import os

from claudlet.core import hostinfo


def outbox_file(session_id):
    """이 세션의 아웃박스 경로. `.port` 와 같은 자리, 같은 규칙."""
    sid = session_id or "default"
    return os.path.join(hostinfo.runtime_dir(), "claudlet-{}.outbox".format(sid))


def append(session_id, text, persona=None):
    """쪽지 하나를 쌓는다(펫 쪽). 실패는 조용히 삼킨다 — 말을 못 전한 것이
    펫을 죽일 일은 아니다."""
    if not text:
        return False
    note = {"text": text}
    if persona:
        note["persona"] = persona
    try:
        with open(outbox_file(session_id), "a", encoding="utf-8") as f:
            f.write(json.dumps(note, ensure_ascii=False) + "\n")
        return True
    except OSError:
        return False


def _read(path):
    try:
        with open(path, encoding="utf-8") as f:
            raw = f.read()
    except OSError:
        return []
    notes = []
    for line in raw.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            note = json.loads(line)
        except ValueError:
            continue                  # 깨진 한 줄이 나머지를 가리지 않는다
        if isinstance(note, dict) and note.get("text"):
            notes.append(note)
    return notes


def take(session_id):
    """쌓인 쪽지를 모두 가져가고 비운다(훅 쪽). 한 번만 배달되게.

    읽고 나서 지우는 것이 아니라 먼저 **rename** 해서 가져간다. 그 사이 펫이
    새로 쓴 쪽지는 새 파일에 들어가므로 유실되지 않는다.

    ponytail: 윈도우에서는 펫이 append 로 연 순간과 겹치면 rename 이 막힌다.
    그 경우 이번 경계에서는 그냥 포기하고(다음 훅에서 배달된다) 훅은 아무
    일도 없던 듯 넘어간다. 쪽지가 늦는 것은 훅이 느려지는 것보다 훨씬 싸다."""
    path = outbox_file(session_id)
    taking = path + ".taking"
    try:
        os.replace(path, taking)
    except OSError:
        return []
    notes = _read(taking)
    try:
        os.unlink(taking)
    except OSError:
        pass
    return notes


def pending(session_id):
    """배달하지 않고 몇 장이나 물고 있는지만 센다 — 펫이 그리려고 본다."""
    return len(_read(outbox_file(session_id)))


def drop(session_id):
    """물고 있는 것을 버린다(우클릭 메뉴). 이미 없으면 아무 일도 아니다."""
    try:
        os.unlink(outbox_file(session_id))
        return True
    except OSError:
        return False


# ---------- 순수: 에이전트가 실제로 읽는 문장 ----------

HEADER = "[claudlet] 사용자가 데스크톱 펫을 통해 전한 말이다. 프롬프트가 아니라 곁다리 메시지이므로, 하던 일이 있으면 그것을 이어가면서 아래에 답해라."

# 에이전트의 답과 크리처의 답은 다른 것이어야 한다. 일은 평소처럼 터미널에서
# 하고, 크리처의 목소리는 이 마커로 감싼 한 줄로만 낸다 — 훅이 그것만 집어
# 펫의 말풍선에 띄운다. 마커가 없으면 말풍선도 없다(평소와 똑같이 동작한다).
MARK_OPEN = "<claudlet>"
MARK_CLOSE = "</claudlet>"
SAY_MAX = 120                # 말풍선에 들어갈 만큼. 긴 설명은 터미널의 몫이다.
ASK_LINE = ("답할 때 마지막에 펫의 목소리로 딱 한 줄을 %s 와 %s 로 감싸 덧붙여라"
            " (말풍선에 뜬다). 작업에 대한 설명은 평소대로 따로 쓴다."
            % (MARK_OPEN, MARK_CLOSE))


def render(notes):
    """쪽지들을 에이전트에게 들어갈 한 덩어리로 만든다. 순수.

    출처를 밝히는 머리말이 붙는다 — 이것이 사용자가 직접 친 프롬프트로
    보이면 에이전트가 하던 일을 통째로 갈아탄다. 같은 말투 지시가 여러 장에
    반복되면 한 번만 싣는다."""
    lines = [HEADER, ASK_LINE]
    seen = []
    for note in notes:
        persona = note.get("persona")
        if persona and persona not in seen:
            seen.append(persona)
            lines.append("말투: " + persona)
    for note in notes:
        lines.append("- " + note["text"])
    return "\n".join(lines)


def extract_reply(text):
    """에이전트의 답에서 크리처가 말할 한 줄, 없으면 None. 순수.

    마커가 없으면 None 이다 — 그러면 말풍선이 안 뜰 뿐 아무것도 깨지지 않는다."""
    body = text or ""
    end = body.rfind(MARK_CLOSE)
    if end < 0:
        return None
    start = body.rfind(MARK_OPEN, 0, end)
    if start < 0:
        return None
    one = " ".join(body[start + len(MARK_OPEN):end].split())
    return one[:SAY_MAX] if one else None


def last_assistant_text(lines):
    """transcript JSONL 줄들에서 마지막 assistant 발화의 텍스트, 없으면 None.

    포맷이 비공식이라는 것이 이 함수의 전제다 — 모르는 모양은 조용히 건너뛴다.
    2026-07-14 에 사용량 대시보드를 접은 이유가 이 포맷 의존이었으므로, 여기서
    나오는 것은 "있으면 좋은 것"이지 기능의 뼈대가 아니다."""
    for line in reversed(list(lines or ())):
        try:
            rec = json.loads(line)
        except (ValueError, TypeError):
            continue
        if not isinstance(rec, dict) or rec.get("type") != "assistant":
            continue
        content = (rec.get("message") or {}).get("content")
        if isinstance(content, str):
            return content or None
        if isinstance(content, list):
            parts = [b.get("text") for b in content
                     if isinstance(b, dict) and b.get("type") == "text"
                     and isinstance(b.get("text"), str)]
            if parts:
                return "\n".join(parts)
    return None


def reply_from_transcript(path, tail_bytes=65536):
    """transcript 파일 끝에서 크리처가 말할 한 줄을 뽑는다. 얇은 껍데기.

    전부 읽지 않는다 — 긴 대화의 JSONL 은 수십 MB 가 되고, 훅은 빨라야 한다."""
    try:
        with open(path, "rb") as f:
            f.seek(0, os.SEEK_END)
            size = f.tell()
            f.seek(max(0, size - tail_bytes))
            raw = f.read().decode("utf-8", "replace")
    except (OSError, TypeError):
        return None
    lines = raw.splitlines()
    if size > tail_bytes and lines:
        lines = lines[1:]              # 잘린 첫 줄은 JSON 이 아니다
    return extract_reply(last_assistant_text(lines) or "")


def typed_line(text, persona):
    """즉시 전송일 때 프롬프트에 그대로 찍힐 한 줄. 순수.

    쪽지와 달리 이건 사용자 눈앞에 찍히므로 말투 지시를 숨길 수가 없다 —
    숨기지 않는 편이 정직하고, 무엇이 제출됐는지 그대로 보인다."""
    return "[펫: %s] %s" % (persona, text) if persona else text


def payload(event, notes):
    """훅이 stdout 으로 뱉을 dict, 또는 전할 것이 없으면 None. 순수."""
    if not notes:
        return None
    return {"hookSpecificOutput": {"hookEventName": event,
                                   "additionalContext": render(notes)}}
