"""mod 링크 — Claude Code mod 가 펫의 말을 진짜 턴으로 넣는 길.

펫은 `claudlet-<sid>.send` 에 한 줄씩 쌓고(`{"id", "text", "framed"?}`),
세션 안의 mod(`src/claudlet/mod`)가 읽어 `$.prompt.submit` 한다. mod 는
rename·삭제를 못 하므로 이 파일에 쓰는 쪽은 펫 하나뿐이다. mod 는 어디까지
넣었는지(ack)를 하트비트 파일 `claudlet-<sid>.mod` 에 남기고, 펫은 다음에 쓸
때 ack 이하 줄을 걷어낸다. 쓰는 쪽이 하나라 경합이 없다.

mod 가 살아 있으면 터미널에 직접 치기(Konsole·Windows 콘솔)와 waiter 깨우기를
이것 하나가 대신한다. OS·터미널과 상관없다. 없으면 옛 길 그대로다.
"""
import json
import os
import time

from claudlet.core import hostinfo

FRESH_S = 30.0             # mod 는 10초마다 뛴다 — 세 번 놓치면 없는 것으로 본다


def _path(session_id, ext):
    sid = session_id or "default"
    return os.path.join(hostinfo.runtime_dir(), "claudlet-{}.{}".format(sid, ext))


def send_file(session_id):
    return _path(session_id, "send")


def beat_file(session_id):
    return _path(session_id, "mod")


def read_beat(session_id):
    """(ack, 살아 있나). 하트비트가 없거나 깨졌으면 (0, False)."""
    path = beat_file(session_id)
    try:
        with open(path, encoding="utf-8") as f:
            beat = json.load(f)
        mtime = os.path.getmtime(path)
    except (OSError, ValueError):
        return 0, False
    if not isinstance(beat, dict):
        return 0, False
    return int(beat.get("ack") or 0), is_alive(beat, mtime, time.time())


def is_alive(beat, mtime, now):
    """순수. 세션이 끝나며 끈 하트비트(gone)거나 오래됐으면 죽은 것."""
    return not beat.get("gone") and now - mtime < FRESH_S


def alive(session_id):
    return bool(session_id) and read_beat(session_id)[1]


def pending_lines(raw, ack):
    """순수. 아직 mod 가 넣지 않은 줄(ack 보다 큰 id)만 남긴다."""
    keep = []
    for line in (raw or "").splitlines():
        try:
            m = json.loads(line)
        except ValueError:
            continue
        if isinstance(m, dict) and isinstance(m.get("id"), int) and m["id"] > ack:
            keep.append(m)
    return keep


def next_id(lines, ack, now_ms):
    """순수. 시각(ms)을 id 로 쓰되 앞선 것보다 늘 크게 — 펫을 다시 띄워도 이어진다."""
    last = max([ack] + [m["id"] for m in lines])
    return max(int(now_ms), last + 1)


def push(session_id, text, framed=False, context=None, fork=False):
    """한 줄을 쌓는다(펫 쪽). 넣은 것은 걷어내고 다시 쓴다. 그 줄의 id, 실패는
    None — 호출자가 옛 길로 강등한다.

    framed: mod 가 "claudlet 플러그인이 보낸 말" 틀을 씌워 넣는다(쪽지 배달).
    아니면 사용자가 직접 친 말처럼 맨말로 들어간다(지금 물어보기).
    context: 그 턴에만 모델이 읽는 덧붙임(말투·창 정보). 훅 경계에 맡기면 세션이
    일하는 중일 때 엉뚱한 턴이 가져간다(Gate 0 실측) — mod 가 이 말의 턴에 붙인다.
    fork: 세션에 넣지 않고 mod 가 `$.model.fork` 로 이 세션 맥락 위에서 따로 묻는다
    (크리처 머리). 답은 `forked()` 로 온다."""
    if not text:
        return None
    path = send_file(session_id)
    ack = read_beat(session_id)[0]
    try:
        with open(path, encoding="utf-8") as f:
            lines = pending_lines(f.read(), ack)
    except OSError:
        lines = []
    line = {"id": next_id(lines, ack, time.time() * 1000), "text": text}
    if framed:
        line["framed"] = True
    if context:
        line["context"] = context
    if fork:
        line["fork"] = True
    lines.append(line)
    body = "".join(json.dumps(m, ensure_ascii=False) + "\n" for m in lines)
    tmp = path + ".tmp"
    try:
        # 다른 사용자가 줄을 심으면 그게 사용자 말로 들어간다 — 나만 읽고 쓴다
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(body)
        os.replace(tmp, path)          # mod 가 반쯤 쓴 파일을 읽지 않게
        return line["id"]
    except OSError:
        return None


def _mod_lines(session_id, ext):
    """mod 가 쓰는 파일(.forked / .said)의 줄들. 쓰는 쪽은 mod 하나, 펫은 읽기만."""
    try:
        with open(_path(session_id, ext), encoding="utf-8") as f:
            raw = f.read()
    except OSError:
        return []
    out = []
    for line in raw.splitlines():
        try:
            m = json.loads(line)
        except ValueError:
            continue
        if isinstance(m, dict) and isinstance(m.get("id"), (int, float)):
            out.append(m)
    return out


def forked(session_id):
    """fork 로 물은 것의 답: {id: {"text"} 또는 {"error"}}."""
    return {m["id"]: m for m in _mod_lines(session_id, "forked")}


def said(session_id, after=0):
    """에이전트가 say 도구로 펫에게 시킨 말 중 `after` 보다 새 것들, 오래된 것부터."""
    return sorted((m for m in _mod_lines(session_id, "said")
                   if m["id"] > after and m.get("text")), key=lambda m: m["id"])
