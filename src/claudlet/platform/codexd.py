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
소켓은 CODEX_HOME/app-server-control/app-server-control.sock. 유닉스 소켓을 못
여는 파이썬(윈도우 기본 빌드엔 AF_UNIX 가 없다)은 `codex app-server proxy` —
그 소켓을 stdio 로 이어주는 공식 명령 — 를 거친다. 같은 바이트가 오간다(리눅스
에서 핸드셰이크·initialize 까지 실측).
"""
import base64
import json
import os
import shutil
import socket
import struct
import subprocess
import threading

SOCK = os.path.join("app-server-control", "app-server-control.sock")


def socket_path(env=None):
    """데몬 제어 소켓 경로, 없으면 None."""
    env = os.environ if env is None else env
    home = env.get("CODEX_HOME") or os.path.join(os.path.expanduser("~"), ".codex")
    path = os.path.join(home, SOCK)
    return path if os.path.exists(path) else None


def available():
    """데몬에 닿을 길이 있나 — 소켓을 직접 열 수 있거나, 프록시할 codex 가 있거나."""
    if socket_path() is None:
        return False
    return hasattr(socket, "AF_UNIX") or shutil.which("codex") is not None


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


def _unix(path, timeout):
    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    s.settimeout(timeout)
    s.connect(path)
    return s.sendall, lambda: s.recv(65536), s.close


def _proxy(timeout):
    """`codex app-server proxy` 의 stdio 를 통로로. 타임아웃은 프로세스를 죽여서 —
    그러면 막혀 있던 read 가 빈 바이트로 풀린다."""
    exe = shutil.which("codex")
    if not exe:
        raise OSError("codex not on PATH")
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    p = subprocess.Popen([exe, "app-server", "proxy"], stdin=subprocess.PIPE,
                         stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                         creationflags=flags)
    timer = threading.Timer(timeout, p.kill)
    timer.daemon = True
    timer.start()

    def send(b):
        p.stdin.write(b)
        p.stdin.flush()

    def close():
        timer.cancel()
        p.kill()

    return send, lambda: os.read(p.stdout.fileno(), 65536), close


class _Conn:
    def __init__(self, send, recv, close):
        self._send, self._recv, self._close = send, recv, close
        key = base64.b64encode(os.urandom(16)).decode()
        self._send(("GET / HTTP/1.1\r\nHost: localhost\r\nUpgrade: websocket\r\n"
                        "Connection: Upgrade\r\nSec-WebSocket-Key: %s\r\n"
                        "Sec-WebSocket-Version: 13\r\n\r\n" % key).encode())
        buf = b""
        while b"\r\n\r\n" not in buf:
            chunk = self._recv()
            if not chunk:
                raise OSError("daemon closed during handshake")
            buf += chunk
        head, self.buf = buf.split(b"\r\n\r\n", 1)
        if b" 101 " not in head.split(b"\r\n", 1)[0]:
            raise OSError("daemon refused the websocket upgrade")

    def send(self, obj):
        self._send(client_frame(obj))

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
            chunk = self._recv()
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
        self._close()


def start_turn(thread_id, text, path=None, timeout=5):
    """그 스레드에 사용자 턴을 넣는다. 데몬이 그 스레드를 들고 있지 않거나 실패하면
    False — 호출자가 다른 길(쪽지)로 간다."""
    path = path or socket_path()
    if not path or not thread_id:
        return False
    try:
        c = _Conn(*(_unix(path, timeout) if hasattr(socket, "AF_UNIX")
                    else _proxy(timeout)))
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


def reachable(path=None, timeout=3):
    """데몬이 initialize 에 답하나 (doctor 용)."""
    path = path or socket_path()
    if not path:
        return False
    try:
        c = _Conn(*(_unix(path, timeout) if hasattr(socket, "AF_UNIX")
                    else _proxy(timeout)))
        try:
            return "result" in c.call(1, "initialize",
                                      {"clientInfo": {"name": "claudlet", "version": "1"}})
        finally:
            c.close()
    except (OSError, ValueError):
        return False


# ---------- 펫의 수명: 데몬이 아니라 TUI 를 본다 ----------
# 펫은 "나를 띄운 에이전트 프로세스가 죽으면 끈다" 로 산다. 코덱스 CLI 에서 그
# 프로세스는 데몬이라 TUI 를 닫아도 안 죽고, 데몬은 닫힌 세션의 스레드도 계속
# 들고 있다(실측: TUI 하나에 로드된 스레드 셋) — 그래서 펫이 영영 안 꺼졌다.
# 대신 그 세션 폴더에서 도는 TUI 가 남아 있는지 본다.

def is_daemon(argv):
    """이 명령줄이 관리형 데몬인가. 순수."""
    return "app-server" in argv and "--managed-daemon" in argv


def tui_running(procs, cwd):
    """`procs` = [(argv, cwd)] 중에 그 폴더의 코덱스 TUI 가 있나. 순수.

    ponytail: 같은 폴더에 TUI 가 둘이면 둘 다 닫혀야 펫이 꺼진다. 스레드와 TUI 를
    잇는 길을 데몬이 주지 않아서 폴더로 잇는다."""
    for argv, where in procs:
        if (argv and os.path.basename(argv[0]) == "codex"
                and "app-server" not in argv and where == cwd):
            return True
    return False


def _procs():
    """리눅스 /proc 의 (argv, cwd). 다른 OS 는 빈 목록 — 호출자가 옛 방식으로 둔다."""
    out = []
    for pid in os.listdir("/proc") if os.path.isdir("/proc") else ():
        if not pid.isdigit():
            continue
        try:
            with open("/proc/%s/cmdline" % pid, "rb") as f:
                argv = [a.decode("utf-8", "replace") for a in f.read().split(b"\0") if a]
            out.append((argv, os.readlink("/proc/%s/cwd" % pid)))
        except OSError:
            continue
    return out


def pid_is_daemon(pid):
    try:
        with open("/proc/%d/cmdline" % pid, "rb") as f:
            return is_daemon([a.decode("utf-8", "replace")
                              for a in f.read().split(b"\0") if a])
    except OSError:
        return False


def session_cwd(session_id):
    """세션을 연 폴더 (rollout 첫 줄 session_meta 의 cwd), 모르면 None."""
    from claudlet.core import transcript
    path = transcript.codex_rollout(session_id)
    if not path:
        return None
    try:
        with open(path, encoding="utf-8") as f:
            meta = json.loads(f.readline()).get("payload") or {}
        return meta.get("cwd") or None
    except (OSError, ValueError):
        return None


def session_open(session_id):
    """그 세션의 TUI 가 아직 떠 있나. 판단할 수 없으면 True (펫을 죽이지 않는다)."""
    cwd = session_cwd(session_id)
    procs = _procs()
    if not cwd or not procs:
        return True
    return tui_running(procs, cwd)
