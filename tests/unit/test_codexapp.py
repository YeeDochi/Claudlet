"""코덱스 앱의 도구 파이프로 스레드에 말 넣기."""
import json
import os
import socket
import struct
import tempfile
import threading

import pytest

from claudlet.platform import codexapp


def test_only_a_codex_app_session_has_a_pipe():
    assert codexapp.pipe_path({}) is None
    assert codexapp.pipe_path({codexapp.PIPE_ENV: "  "}) is None
    assert codexapp.pipe_path({codexapp.PIPE_ENV: "/tmp/x.sock"}) == "/tmp/x.sock"


def test_a_frame_comes_back_as_what_went_in_even_split_in_pieces():
    raw = codexapp.frame({"a": "한글"}) + codexapp.frame({"b": 2})
    msg, rest = codexapp.unframe(raw[:5])
    assert msg is None and rest == raw[:5]          # 덜 왔다
    msg, rest = codexapp.unframe(raw)
    assert msg == {"a": "한글"}
    assert codexapp.unframe(rest)[0] == {"b": 2}


def test_the_request_targets_the_thread_with_the_text():
    req = codexapp.send_request("t-1", "안녕")
    p = req["params"]
    assert (req["method"], p["tool"], p["namespace"]) == \
        ("tools/call", "send_message_to_thread", "codex_app")
    assert p["callerSource"] == "codex"
    assert p["arguments"] == {"threadId": "t-1", "prompt": "안녕"}


@pytest.mark.skipif(not hasattr(socket, "AF_UNIX"), reason="unix socket")
@pytest.mark.parametrize("success", [True, False])
def test_send_reports_what_the_app_answered(success):
    path = os.path.join(tempfile.mkdtemp(), "p.sock")
    srv = socket.socket(socket.AF_UNIX)
    srv.bind(path)
    srv.listen(1)
    got = {}

    def serve():
        c, _ = srv.accept()
        buf = b""
        while True:
            msg, buf = codexapp.unframe(buf)
            if msg is not None:
                break
            buf += c.recv(65536)
        got.update(msg)
        body = {"id": msg["id"], "jsonrpc": "2.0",
                "result": {"contentItems": [], "success": success}}
        c.sendall(codexapp.frame(body))
        c.close()

    t = threading.Thread(target=serve)
    t.start()
    assert codexapp.send_message(path, "t-1", "지금 뭐 해?") is success
    t.join(2)
    srv.close()
    assert got["params"]["arguments"]["prompt"] == "지금 뭐 해?"


def test_no_app_listening_is_just_false(tmp_path):
    assert codexapp.send_message(str(tmp_path / "none.sock"), "t", "x") is False
    assert codexapp.send_message(None, "t", "x") is False


def test_the_thread_s_rollout_is_found_by_its_id(tmp_path):
    d = tmp_path / "sessions" / "2026" / "09" / "28"
    d.mkdir(parents=True)
    f = d / "rollout-2026-09-28T12-47-13-01a0e61f-b782-7903-98e7-92f725e082b3.jsonl"
    f.write_text("")
    env = {"CODEX_HOME": str(tmp_path)}
    assert codexapp.rollout_path("01a0e61f-b782-7903-98e7-92f725e082b3", env) == str(f)
    assert codexapp.rollout_path("nope", env) is None


def test_a_turn_start_is_read_off_the_rollout_even_split_across_reads():
    start = json.dumps({"type": "event_msg", "payload": {"type": "task_started"}}).encode()
    other = json.dumps({"type": "event_msg", "payload": {"type": "token_count"}}).encode()
    n, rest = codexapp.turn_starts(other + b"\n" + start[:10])
    assert n == 0
    n, rest = codexapp.turn_starts(rest + start[10:] + b"\n")
    assert (n, rest) == (1, b"")


def test_the_windows_pipe_speaks_the_same_frames(tmp_path, monkeypatch):
    # named pipe 는 파일처럼 열린다 — 여기선 보통 파일로 같은 읽기·쓰기를 흉내 낸다.
    import io
    reply = codexapp.frame({"id": 1, "jsonrpc": "2.0", "result": {"success": True}})
    written = []

    class Pipe(io.BytesIO):
        def write(self, b):
            written.append(bytes(b))
            return len(b)

    monkeypatch.setattr("builtins.open", lambda *a, **k: Pipe(reply))
    assert codexapp._send_pipe(r"\\.\pipe\codex-browser-use\x",
                               codexapp.send_request("t", "안녕")) is True
    msg, _ = codexapp.unframe(written[0])
    assert msg["params"]["arguments"]["prompt"] == "안녕"
