"""코덱스 CLI 세션에 사용자 턴을 넣는다 — 관리형 app-server 데몬을 통해.

코덱스 CLI(TUI)는 대화를 자기 안에서 돌리지 않고 관리형 데몬
(`codex app-server --listen unix:// --managed-daemon`)에 맡긴다. 훅도 그 데몬
안에서 돈다 — 그래서 펫의 조상은 터미널이 아니라 데몬이고, 터미널에 글자를
쳐 넣는 길(Konsole sendText)로는 IDE 터미널의 코덱스에 닿지 못했다.

대신 데몬에 직접 `turn/start` 를 보낸다. 실측(0.158, IntelliJ 터미널): TUI 화면에
사용자 메시지로 뜨고 rollout 에도 role=user 로 남는다 — 코덱스 앱의 위임 입력과
달리 진짜 사용자 턴이라 UserPromptSubmit 훅이 불리고, 말투 쪽지도 그 훅으로 간다.
돌고 있는 턴이 있으면 turn/start 가 그 턴에 끼어든다(steer).

와이어: 유닉스 소켓 위의 WebSocket(텍스트 프레임 하나 = JSON-RPC 한 통).
소켓은 CODEX_HOME/app-server-control/app-server-control.sock.
"""
import base64
import json
import os
import socket
import struct

SOCK = os.path.join("app-server-control", "app-server-control.sock")


def socket_path(env=None):
    """데몬 제어 소켓 경로, 없으면 None."""
    env = os.environ if env is None else env
    home = env.get("CODEX_HOME") or os.path.join(os.path.expanduser("~"), ".codex")
    path = os.path.join(home, SOCK)
    return path if os.path.exists(path) else None


def client_frame(obj, mask=None):
    """클라이언트 → 서버 텍스트 프레임(가려야 한다, RFC 6455). 순수."""
    data = json.dumps(obj, ensure_ascii=False).encode("utf-8")
    mask = mask if mask is not None else os.urandom(4)
    n = len(data)
    if n < 126:
        head = bytes([0x81, 0x80 | n])
    elif n < 65536:
        head = bytes([0x81, 0x80 | 126]) + struct.pack(">H", n)
    else:
        head = bytes([0x81, 0x80 | 127]) + struct.pack(">Q", n)
    return head + mask + bytes(c ^ mask[i % 4] for i, c in enumerate(data))


def read_frame(buf):
    """(opcode, payload, 남은 바이트) 또는 덜 왔으면 None. 서버 프레임은 안 가린다. 순수."""
    if len(buf) < 2:
        return None
    op, n = buf[0] & 0x0F, buf[1] & 0x7F
    at = 2
    if n == 126:
        if len(buf) < 4:
            return None
        n, at = struct.unpack(">H", buf[2:4])[0], 4
    elif n == 127:
        if len(buf) < 10:
            return None
        n, at = struct.unpack(">Q", buf[2:10])[0], 10
    masked = buf[1] & 0x80
    if masked:
        key, at = buf[at:at + 4], at + 4
    if len(buf) < at + n:
        return None
    payload = buf[at:at + n]
    if masked:
        payload = bytes(c ^ key[i % 4] for i, c in enumerate(payload))
    return op, payload, buf[at + n:]


class _Conn:
    def __init__(self, path, timeout):
        self.s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.s.settimeout(timeout)
        self.s.connect(path)
        key = base64.b64encode(os.urandom(16)).decode()
        self.s.sendall(("GET / HTTP/1.1\r\nHost: localhost\r\nUpgrade: websocket\r\n"
                        "Connection: Upgrade\r\nSec-WebSocket-Key: %s\r\n"
                        "Sec-WebSocket-Version: 13\r\n\r\n" % key).encode())
        buf = b""
        while b"\r\n\r\n" not in buf:
            chunk = self.s.recv(4096)
            if not chunk:
                raise OSError("daemon closed during handshake")
            buf += chunk
        head, self.buf = buf.split(b"\r\n\r\n", 1)
        if b" 101 " not in head.split(b"\r\n", 1)[0]:
            raise OSError("daemon refused the websocket upgrade")

    def send(self, obj):
        self.s.sendall(client_frame(obj))

    def recv(self):
        while True:
            got = read_frame(self.buf)
            if got is not None:
                op, payload, self.buf = got
                if op == 0x1:
                    return json.loads(payload.decode("utf-8"))
                if op == 0x8:
                    raise OSError("daemon closed")
                continue                      # ping/pong 등은 넘긴다
            chunk = self.s.recv(65536)
            if not chunk:
                raise OSError("daemon closed")
            self.buf += chunk

    def call(self, rid, method, params):
        self.send({"id": rid, "method": method, "params": params})
        while True:
            msg = self.recv()
            if msg.get("id") == rid:
                return msg                    # 그 사이 알림(notification)은 버린다

    def close(self):
        self.s.close()


def start_turn(thread_id, text, path=None, timeout=5):
    """그 스레드에 사용자 턴을 넣는다. 데몬이 그 스레드를 들고 있지 않거나 실패하면
    False — 호출자가 다른 길(쪽지)로 간다."""
    path = path or socket_path()
    if not path or not thread_id or not hasattr(socket, "AF_UNIX"):
        return False
    try:
        c = _Conn(path, timeout)
        try:
            if "result" not in c.call(1, "initialize",
                                      {"clientInfo": {"name": "claudlet", "version": "1"}}):
                return False
            c.send({"method": "initialized"})
            loaded = c.call(2, "thread/loaded/list", {}).get("result") or {}
            # 데몬이 안 들고 있는 스레드(다른 데서 도는 세션)에 턴을 열면 데몬이
            # 그 세션을 새로 띄워 버린다 — 우리가 원하는 게 아니다
            if thread_id not in (loaded.get("data") or []):
                return False
            r = c.call(3, "turn/start", {"threadId": thread_id,
                                         "input": [{"type": "text", "text": text}]})
            return "result" in r
        finally:
            c.close()
    except (OSError, ValueError):
        return False
