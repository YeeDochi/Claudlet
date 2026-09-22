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


def render(notes):
    """쪽지들을 에이전트에게 들어갈 한 덩어리로 만든다. 순수.

    출처를 밝히는 머리말이 붙는다 — 이것이 사용자가 직접 친 프롬프트로
    보이면 에이전트가 하던 일을 통째로 갈아탄다. 같은 말투 지시가 여러 장에
    반복되면 한 번만 싣는다."""
    lines = [HEADER]
    seen = []
    for note in notes:
        persona = note.get("persona")
        if persona and persona not in seen:
            seen.append(persona)
            lines.append("말투: " + persona)
    for note in notes:
        lines.append("- " + note["text"])
    return "\n".join(lines)


def payload(event, notes):
    """훅이 stdout 으로 뱉을 dict, 또는 전할 것이 없으면 None. 순수."""
    if not notes:
        return None
    return {"hookSpecificOutput": {"hookEventName": event,
                                   "additionalContext": render(notes)}}
