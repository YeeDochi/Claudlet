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


def append(session_id, text, persona=None, nickname=None):
    """쪽지 하나를 쌓는다(펫 쪽). 실패는 조용히 삼킨다 — 말을 못 전한 것이
    펫을 죽일 일은 아니다."""
    if not text:
        return False
    note = {"text": text}
    if persona:
        note["persona"] = persona
    if nickname:
        note["name"] = nickname
    try:
        with open(outbox_file(session_id), "a", encoding="utf-8") as f:
            f.write(json.dumps(note, ensure_ascii=False) + "\n")
        return True
    except OSError:
        return False


def append_voice(session_id, persona, nickname=None):
    """"이번 턴은 펫을 통해 들어온 것이다"를 쌓는다 — 말투만 싣고 사용자가 한
    말은 싣지 않는다.

    즉시 전송은 프롬프트에 질문을 그대로 타이핑하므로, 말투 지시까지 거기
    끼워 넣으면 사용자 눈에 계속 밟힌다(실사용에서 바로 걸렸다). 타이핑이
    제출되면 UserPromptSubmit 이 돌고, 훅이 이 쪽지를 같은 턴에 실어 보낸다.

    말투·이름이 비어도 쌓는다: 이 쪽지가 곧 "🗨 한 줄을 붙여라" 는 지시라서,
    없으면 에이전트가 크리처 답을 안 쓰고 말풍선이 영영 안 뜬다(코덱스 실측)."""
    note = {"voice": persona or ""}
    if nickname:
        note["name"] = nickname
    try:
        with open(outbox_file(session_id), "a", encoding="utf-8") as f:
            f.write(json.dumps(note, ensure_ascii=False) + "\n")
        return True
    except OSError:
        return False


def wake(session_id):
    """"지금 깨워라" 표시를 쌓는다. 프롬프트에 직접 쳐 넣을 수 없는 호스트
    (IDE 터미널, 데스크톱 앱)에서 즉시 전송이 이것이다 — 세션이 놀고 있으면
    대기 중인 waiter(`claudlet-hook Rewake`) 가 보고 쪽지를 들고 세션을 깨운다.
    일하는 중이면 다음 툴콜 경계가 평소처럼 가져간다."""
    try:
        with open(outbox_file(session_id), "a", encoding="utf-8") as f:
            f.write(json.dumps({"wake": True}) + "\n")
        return True
    except OSError:
        return False


def wants_wake(session_id):
    """가져가지 않고, 깨워 달라는 표시가 있는지만 본다(waiter 쪽)."""
    return any(n.get("wake") for n in _read(outbox_file(session_id)))


# ---------- waiter: 놀고 있는 세션을 깨우는 쪽 ----------
# Claude Code 의 asyncRewake 훅은 백그라운드로 돌다가 exit 2 로 끝나면 쉬던
# 세션을 깨우고 stderr 를 모델에게 건넨다(2.1.283 바이너리의 훅 스키마 설명,
# IntelliJ 터미널에서 실측). Stop 마다 새 waiter 가 뜨므로, 파일에 지금 주인의
# pid 를 적어 두고 옛 waiter 는 주인이 바뀐 것을 보면 조용히 물러난다.

def waiter_file(session_id):
    sid = session_id or "default"
    return os.path.join(hostinfo.runtime_dir(), "claudlet-{}.waiter".format(sid))


def claim_waiter(session_id, pid):
    try:
        with open(waiter_file(session_id), "w") as f:
            f.write(str(pid))
        return True
    except OSError:
        return False


def waiter_owner(session_id):
    try:
        with open(waiter_file(session_id)) as f:
            return int(f.read().strip() or 0)
    except (OSError, ValueError):
        return 0


def can_wake(session_id):
    """이 세션에 waiter 가 한 번이라도 섰나 — 깨우는 훅이 설치돼 있다는 뜻.
    지금 대기 중인지는 묻지 않는다: 일하는 중이면 waiter 가 없어도 다음 툴콜
    경계가, 그 턴이 끝나면 새 waiter 가 표시를 보고 바로 깨운다."""
    return os.path.exists(waiter_file(session_id))


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
        # "voice" 는 비어 있어도 쪽지다 — 펫으로 들어온 턴이라는 표시 자체다
        if isinstance(note, dict) and (note.get("text") or "voice" in note
                                       or note.get("name") or note.get("wake")):
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


def restore(session_id, note):
    """가져갔던 쪽지를 되돌려 놓는다 — 배달에 실패했을 때.

    take() 는 먼저 가져가고 나중에 쓴다. 그 사이에 실패하면 사용자의 말이 영영
    사라지므로, 실패한 쪽은 이것으로 되돌린다."""
    if not isinstance(note, dict) or not (note.get("text") or note.get("voice")):
        return False
    try:
        with open(outbox_file(session_id), "a", encoding="utf-8") as f:
            f.write(json.dumps(note, ensure_ascii=False) + "\n")
        return True
    except OSError:
        return False


def pending(session_id):
    """배달하지 않고 몇 장이나 물고 있는지만 센다 — 펫이 그리려고 본다.

    말투 쪽지는 세지 않는다. 쪽지를 문 그림은 "네 말을 들고 있다"는 뜻이고,
    내부 배관까지 물고 있는 것처럼 보이면 거짓말이 된다."""
    return len([n for n in _read(outbox_file(session_id)) if n.get("text")])


def drop(session_id):
    """물고 있는 것을 버린다(우클릭 메뉴). 이미 없으면 아무 일도 아니다."""
    try:
        os.unlink(outbox_file(session_id))
        return True
    except OSError:
        return False


# ---------- 순수: 에이전트가 실제로 읽는 문장 ----------

HEADER = ("[claudlet] 사용자가 데스크톱 펫에게 건 말이다. 에이전트인 너에게"
          " 직접 시킨 일이 아니다. 하던 일이 있으면 그것을 이어가면서 아래를 받아라.")

# 에이전트의 답과 크리처의 답은 다른 것이어야 한다. 일은 평소처럼 터미널에서
# 하고, 크리처의 목소리는 이 마커로 감싼 한 줄로만 낸다 — 훅이 그것만 집어
# 펫의 말풍선에 띄운다. 마커가 없으면 말풍선도 없다(평소와 똑같이 동작한다).
# 이 줄은 터미널에도 그대로 보인다. XML 태그로 감싸면 사용자가 마크업을 읽게
# 되므로(실사용에서 바로 걸렸다), 사람이 쓴 것처럼 읽히는 표시를 쓴다.
MARK = "🗨"
SAY_MAX = 120                # 말풍선에 들어갈 만큼. 긴 설명은 터미널의 몫이다.
ASK_LINE = ("펫의 목소리로 '%s ' 로 시작하는 한 줄을 답의 맨 마지막에 덧붙여라"
            " (그 줄이 말풍선에 뜬다). 펫에게 건 잡담이면 그 한 줄만 내고 다른"
            " 말은 하지 마라 — 두 번 답하는 꼴이 된다. 실제로 처리할 작업이 있는"
            " 요청일 때만 평소대로 처리하고 그 한 줄을 덧붙인다. 이 지시는 이번"
            " 턴에만 해당한다 — 다음 턴부터는 [claudlet] 쪽지가 다시 오지 않는 한"
            " 그 줄을 붙이지 마라. 터미널에서 직접 받은 요청에 크리처가 답하면 안 된다."
            % MARK)


def render(notes):
    """쪽지들을 에이전트에게 들어갈 한 덩어리로 만든다. 순수.

    출처를 밝히는 머리말이 붙는다 — 이것이 사용자가 직접 친 프롬프트로
    보이면 에이전트가 하던 일을 통째로 갈아탄다. 같은 말투 지시가 여러 장에
    반복되면 한 번만 싣는다."""
    said = [n for n in notes if n.get("text")]
    lines = [HEADER] if said else []
    lines.append(ASK_LINE)
    for note in notes:
        name = note.get("name")
        if name:
            # 조사를 붙이지 않는 문장으로 둔다 — 받침에 따라 이/가가 갈린다
            lines.append("이 펫은 '%s' 라고 불린다. 그렇게 부르면 너를 부르는 "
                         "것이니 자기 얘기로 받아라." % name)
            break
    seen = []
    for note in notes:
        persona = note.get("persona") or note.get("voice")
        if persona and persona not in seen:
            seen.append(persona)
            lines.append("말투: " + persona)
    for note in said:
        lines.append("- " + note["text"])
    return "\n".join(lines)


def extract_reply(text):
    """에이전트의 답에서 크리처가 말할 한 줄, 없으면 None. 순수.

    마커가 없으면 None 이다 — 그러면 말풍선이 안 뜰 뿐 아무것도 깨지지 않는다."""
    for line in reversed((text or "").splitlines()):
        line = line.strip()
        if not line.startswith(MARK):
            continue
        one = " ".join(line[len(MARK):].split())
        # "🗨 라임: 물컹하다아" 처럼 이름을 붙여 쓰는 편이 터미널에서 자연스럽다.
        # 말풍선은 크리처 위에 뜨므로 이름까지 되풀이할 이유가 없다.
        head, sep, rest = one.partition(":")
        if sep and len(head) <= 24 and rest.strip():
            one = rest.strip()
        return one[:SAY_MAX] if one else None
    return None


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
        if not isinstance(rec, dict):
            continue
        # Claude Code: {"type":"assistant","message":{"content":…}}
        # Codex rollout: {"type":"response_item","payload":{"type":"message",
        #                 "role":"assistant","content":[{"output_text"…}]}}
        if rec.get("type") == "assistant":
            content = (rec.get("message") or {}).get("content")
        else:
            pay = rec.get("payload") or {}
            if (pay.get("type") != "message" or pay.get("role") != "assistant"):
                continue
            content = pay.get("content")
        if isinstance(content, str):
            return content or None
        if isinstance(content, list):
            parts = [b.get("text") for b in content
                     if isinstance(b, dict)
                     and b.get("type") in ("text", "output_text")
                     and isinstance(b.get("text"), str)]
            if parts:
                return "\n".join(parts)
    return None


TAIL_START = 65536          # 대개 여기서 찾는다
TAIL_MAX = 8 << 20          # 못 찾으면 여기까지만 거슬러 올라간다


def has_more(text):
    """답에 크리처 한 줄 말고도 할 말(설명·작업 내역)이 있나. 순수."""
    return any(l.strip() and not l.strip().startswith(MARK)
               for l in (text or "").splitlines())


_TOOL_BLOCKS = ("tool_use", "server_tool_use")
_TOOL_ITEMS = ("function_call", "custom_tool_call", "local_shell_call")


def turn_had_more(lines):
    """이번 턴에 크리처 한 줄 말고 에이전트가 한 일(도구·설명)이 있었나. 순수.

    마지막 사용자 프롬프트까지 거슬러 올라간다. 도구 결과도 'user' 로 기록되니
    그것은 프롬프트로 치지 않는다. 모르는 모양은 last_assistant_text 처럼 넘긴다."""
    for line in reversed(list(lines or ())):
        try:
            rec = json.loads(line)
        except (ValueError, TypeError):
            continue
        if not isinstance(rec, dict):
            continue
        if rec.get("type") in ("user", "assistant"):        # Claude Code
            role, content = rec["type"], (rec.get("message") or {}).get("content")
        else:                                                # Codex rollout
            pay = rec.get("payload") or {}
            if pay.get("type") in _TOOL_ITEMS:
                return True
            if pay.get("type") != "message":
                continue
            role, content = pay.get("role"), pay.get("content")
        blocks = content if isinstance(content, list) else [
            {"type": "text", "text": content}]
        kinds = {b.get("type") for b in blocks if isinstance(b, dict)}
        if role == "user":
            if "tool_result" in kinds:
                continue
            return False                                     # 턴의 시작에 닿았다
        if role != "assistant":
            continue
        if kinds & set(_TOOL_BLOCKS):
            return True
        if any(has_more(b.get("text")) for b in blocks
               if isinstance(b, dict) and isinstance(b.get("text"), str)):
            return True
    return False


def reply_from_transcript(path, tail_bytes=TAIL_START, tail_max=TAIL_MAX,
                          with_more=False):
    """transcript 파일 끝에서 크리처가 말할 한 줄을 뽑는다. 얇은 껍데기.

    전부 읽지 않는다 — 긴 대화의 JSONL 은 수십 MB 가 되고, 펫은 이것을 0.2초마다
    돌린다. 그렇다고 고정 꼬리만 읽어서도 안 된다: 한 턴이 남기는 기록(시스템
    리마인더, 큰 툴 결과)이 수백 KB 가 되어 정작 답이 창 밖으로 밀려난다 —
    실측에서 답이 파일 끝에서 124KB 앞에 있었고, 그래서 첫 말풍선이 아예 뜨지
    않았다. 그래서 찾을 때까지 꼬리를 배로 늘리되 상한을 둔다.

    with_more: (한 줄, 그 밖에도 할 말이 있었나) 로 돌려준다."""
    miss = (None, False) if with_more else None
    while True:
        try:
            with open(path, "rb") as f:
                f.seek(0, os.SEEK_END)
                size = f.tell()
                f.seek(max(0, size - tail_bytes))
                raw = f.read().decode("utf-8", "replace")
        except (OSError, TypeError):
            return miss
        lines = raw.splitlines()
        if size > tail_bytes and lines:
            lines = lines[1:]          # 잘린 첫 줄은 JSON 이 아니다
        text = last_assistant_text(lines)
        if text is not None:
            line = extract_reply(text)
            return (line, turn_had_more(lines)) if with_more else line
        if tail_bytes >= size or tail_bytes >= tail_max:
            return miss                # 파일을 다 봤거나, 충분히 거슬러 올라갔다
        tail_bytes = min(tail_bytes * 4, tail_max)


def payload(event, notes):
    """훅이 stdout 으로 뱉을 dict, 또는 전할 것이 없으면 None. 순수."""
    if not notes:
        return None
    return {"hookSpecificOutput": {"hookEventName": event,
                                   "additionalContext": render(notes)}}
