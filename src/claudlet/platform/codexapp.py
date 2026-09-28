"""코덱스 앱(데스크톱)의 스레드에 사용자 메시지로 말을 넣는다.

코덱스 앱은 자기 app-server 에 `codex_app` 도구들(send_message_to_thread 등)을
유닉스 소켓 하나로 열어두고, 그 경로를 app-server 의 환경변수
CODEX_APP_TOOLS_PIPE_PATH 로 넘긴다. 훅은 그 app-server 아래에서 돌고 펫은 훅이
띄우므로, 펫의 환경에 그 경로가 그대로 있다 — 코덱스 앱 세션이라는 표시이기도 하다.

와이어: 4바이트 little-endian 길이 + JSON-RPC 2.0 (앱 번들의
plugins/codex-app-tools/server.mjs 에서 읽었다). send_message_to_thread 의 설명이
"The prompt appears as a user-visible message in the destination task" 이고,
실기(리눅스, 앱 26.9)에서 보낸 말에 스레드가 답했다.
"""
import json
import os
import socket
import struct
import uuid

PIPE_ENV = "CODEX_APP_TOOLS_PIPE_PATH"


def pipe_path(env=None):
    """이 프로세스가 코덱스 앱 세션 아래에서 떴으면 그 도구 파이프, 아니면 None."""
    path = (os.environ if env is None else env).get(PIPE_ENV, "").strip()
    return path or None


def rollout_path(thread_id, env=None):
    """이 스레드의 대화 기록(rollout) 경로, 없으면 None.

    앱이 넣은 메시지는 위임(delegation) 입력으로 들어가 UserPromptSubmit·Stop
    훅이 불리지 않는다(실측: 말투 쪽지가 그대로 남았다). 그래서 펫이 턴 끝을
    훅으로 못 듣고, 이 파일을 직접 지켜봐야 답을 받는다."""
    import glob
    env = os.environ if env is None else env
    home = env.get("CODEX_HOME") or os.path.join(os.path.expanduser("~"), ".codex")
    hits = glob.glob(os.path.join(home, "sessions", "*", "*", "*",
                                  "rollout-*-%s.jsonl" % thread_id))
    return max(hits, key=os.path.getmtime) if hits else None


def frame(obj):
    data = json.dumps(obj, ensure_ascii=False).encode("utf-8")
    return struct.pack("<I", len(data)) + data


def unframe(buf):
    """(한 메시지, 남은 바이트) 또는 아직 덜 왔으면 (None, buf)."""
    if len(buf) < 4:
        return None, buf
    n = struct.unpack("<I", buf[:4])[0]
    if len(buf) < 4 + n:
        return None, buf
    return json.loads(buf[4:4 + n].decode("utf-8")), buf[4 + n:]


def send_request(thread_id, text):
    """send_message_to_thread 를 부르는 tools/call 요청. 순수.

    바깥 threadId 는 "누가 부르나"(도구를 쓰는 쪽 스레드) 자리다. 펫은 스레드가
    아니므로 보낼 스레드를 그대로 쓴다."""
    return {"id": 1, "jsonrpc": "2.0", "method": "tools/call",
            "params": {"namespace": "codex_app",
                       "tool": "send_message_to_thread",
                       "threadId": thread_id,
                       "callId": "claudlet-" + uuid.uuid4().hex,
                       "turnId": "claudlet-" + uuid.uuid4().hex,
                       "arguments": {"threadId": thread_id, "prompt": text}}}


def accepted(response):
    """앱이 받아들였나. 순수."""
    result = (response or {}).get("result") or {}
    return bool(result.get("success"))


def send_message(path, thread_id, text, timeout=5):
    """그 스레드에 말을 넣는다. 실패는 False — 호출자가 쪽지로 강등한다."""
    # ponytail: 유닉스 소켓만. 윈도우 앱은 named pipe 일 텐데 재보지 않았다.
    if not path or not thread_id or not hasattr(socket, "AF_UNIX"):
        return False
    try:
        s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        s.settimeout(timeout)
        try:
            s.connect(path)
            s.sendall(frame(send_request(thread_id, text)))
            buf = b""
            while True:
                msg, buf = unframe(buf)
                if msg is not None:
                    return accepted(msg)
                chunk = s.recv(65536)
                if not chunk:
                    return False
                buf += chunk
        finally:
            s.close()
    except (OSError, ValueError):
        return False
