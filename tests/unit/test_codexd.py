"""코덱스 CLI 세션에 데몬으로 턴 넣기."""
import json
import os
import socket
import struct
import tempfile
import threading

import pytest

from claudlet.platform import codexd


def _server_frame(obj):
    data = json.dumps(obj).encode()
    n = len(data)
    head = bytes([0x81, n]) if n < 126 else bytes([0x81, 126]) + struct.pack(">H", n)
    return head + data


def test_a_client_frame_reads_back_as_what_went_in_even_in_pieces():
    raw = codexd.client_frame({"m": "한글" * 50}, mask=b"\x01\x02\x03\x04")
    assert codexd.read_frame(raw[:3]) is None
    op, payload, rest = codexd.read_frame(raw + b"xx")
    assert op == 1 and json.loads(payload) == {"m": "한글" * 50} and rest == b"xx"


def test_no_daemon_socket_means_no_path(tmp_path):
    assert codexd.socket_path({"CODEX_HOME": str(tmp_path)}) is None


def _fake_daemon(loaded):
    """initialize / thread/loaded/list / turn/start 에 답하는 가짜 데몬. 받은 호출을 모은다."""
    path = os.path.join(tempfile.mkdtemp(), "d.sock")
    srv = socket.socket(socket.AF_UNIX)
    srv.bind(path)
    srv.listen(1)
    calls = []

    def serve():
        c, _ = srv.accept()
        buf = b""
        while b"\r\n\r\n" not in buf:
            buf += c.recv(4096)
        c.sendall(b"HTTP/1.1 101 Switching Protocols\r\nUpgrade: websocket\r\n"
                  b"Connection: Upgrade\r\n\r\n")
        buf = buf.split(b"\r\n\r\n", 1)[1]
        while True:
            got = codexd.read_frame(buf)
            if got is None:
                chunk = c.recv(65536)
                if not chunk:
                    break
                buf += chunk
                continue
            _, payload, buf = got
            msg = json.loads(payload)
            calls.append(msg)
            if "id" not in msg:
                continue
            result = {"thread/loaded/list": {"data": loaded},
                      "turn/start": {"turn": {"id": "t1"}}}.get(msg["method"], {})
            c.sendall(_server_frame({"id": msg["id"], "result": result}))
        c.close()

    threading.Thread(target=serve, daemon=True).start()
    return path, calls, srv


@pytest.mark.skipif(not hasattr(socket, "AF_UNIX"), reason="unix socket")
def test_a_turn_goes_into_a_thread_the_daemon_holds():
    path, calls, srv = _fake_daemon(["th-1"])
    assert codexd.start_turn("th-1", "안녕", path=path) is True
    srv.close()
    turn = [c for c in calls if c.get("method") == "turn/start"]
    assert turn and turn[0]["params"] == {"threadId": "th-1",
                                          "input": [{"type": "text", "text": "안녕"}]}


@pytest.mark.skipif(not hasattr(socket, "AF_UNIX"), reason="unix socket")
def test_a_thread_the_daemon_does_not_hold_is_left_alone():
    # 데몬이 안 들고 있는 스레드에 턴을 열면 그 세션을 데몬이 새로 띄워 버린다
    path, calls, srv = _fake_daemon(["someone-else"])
    assert codexd.start_turn("th-1", "안녕", path=path) is False
    srv.close()
    assert not [c for c in calls if c.get("method") == "turn/start"]
