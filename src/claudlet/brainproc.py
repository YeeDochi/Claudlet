"""크리처 머리를 띄우고 말을 주고받는 얇은 Qt 어댑터. 무엇을 보내고 어떻게 읽을지는
`core/brain.py`(순수)가 정한다.

claude 는 한 번 띄워 두고 stream-json 으로 계속 말을 넣는다. 들어간 순서대로 답이
나오므로 기다리는 말들을 줄(`_queue`)로 세워 두고 결과가 나올 때마다 맨 앞의 것에
붙인다. 오래 말이 없으면 내린다 — 펫 하나에 220MB(실측)를 늘 물려 둘 이유는 없다.

codex 는 우리만 쓰는 `codex app-server` 를 띄워 둔다(stdio JSON-RPC). 스레드 하나에
턴을 하나씩 — 돌고 있는 턴에 turn/start 를 또 보내면 그 턴에 끼어들어 버리므로, 말이
여럿이면 줄을 세워 앞의 턴이 끝난 뒤에 다음 것을 연다.

어떤 경우에도 말은 `answered` 아니면 `failed` 로 한 번 돌아온다. failed 를 받은
쪽(펫)이 그 말을 본 세션으로 넘긴다 — 말이 사라지지 않게 하는 약속은 여기서 시작한다.
"""
from PyQt6.QtCore import QObject, QProcess, QProcessEnvironment, QTimer, pyqtSignal

from claudlet.core import brain

IDLE_S = 600          # 이만큼 말이 없으면 띄워 둔 머리를 내린다


class CreatureBrain(QObject):
    answered = pyqtSignal(object, object)     # token, parse_reply 결과(None 가능)
    failed = pyqtSignal(object)               # token

    def __init__(self, agent, exe, session_id, parent=None):
        super().__init__(parent)
        self.agent = agent
        self.exe = exe
        self.session_id = session_id or "default"
        self.timeout_s = brain.TIMEOUT_S
        self.idle_s = IDLE_S
        self._proc = None          # 띄워 둔 머리
        self._buf = b""
        self._queue = []           # 답을 기다리는 (token, compose) — 들어간 순서
        # codex: 스레드가 준비되기 전엔 턴을 못 연다. 턴은 한 번에 하나.
        self._thread = None
        self._turn = None          # 지금 돌고 있는 턴의 token
        self._turn_text = ""
        self._turns = 0            # 이 스레드에서 연 턴 수 (0 이면 첫 말 = 지시를 싣는다)
        self._rid = 0
        self._idle = QTimer(self)
        self._idle.setSingleShot(True)
        self._idle.timeout.connect(self.stop)

    # --- 바깥에서 쓰는 것 ----------------------------------------------------

    def busy(self):
        return bool(self._queue or self._turn is not None)

    def pending(self):
        """답을 기다리는 token 들 (돌고 있는 것 먼저)."""
        head = [self._turn] if self._turn is not None else []
        return head + [t for t, _c in self._queue]

    def ask(self, token, compose):
        """말 하나를 넣는다. `compose(first)` 가 보낼 글을 만든다 — 새로 띄운 머리면
        first=True 라 지시와 맥락을 처음부터 실어야 한다."""
        self._idle.stop()
        fresh = self._proc is None
        if fresh and not self._spawn():
            self.failed.emit(token)
            return
        if self.agent == "codex":
            self._queue.append((token, compose))
            self._codex_next()
            return
        self._queue.append((token, None))
        self._proc.write(brain.stream_message(compose(fresh)).encode("utf-8"))
        self._arm(token)

    def stop(self):
        """머리를 내린다. 기다리던 말은 모두 failed 로 돌아간다."""
        self._idle.stop()
        proc, self._proc = self._proc, None
        if proc is not None:
            try:
                proc.finished.disconnect()
            except TypeError:
                pass
            proc.kill()
            proc.waitForFinished(1000)     # 펫이 꺼지는 중이면 이벤트 루프가 거둘 틈이 없다
            proc.deleteLater()
        pending = [t for t, _c in self._queue]
        if self._turn is not None:
            pending.insert(0, self._turn)
        self._queue, self._turn, self._thread, self._turns = [], None, None, 0
        for token in pending:
            self.failed.emit(token)

    # --- 공통 -----------------------------------------------------------------

    def _spawn(self):
        if self.agent == "codex":
            argv = brain.codex_server_command(self.exe)
        else:
            argv = brain.stream_command(self.exe)
        proc = QProcess(self)
        env = QProcessEnvironment.systemEnvironment()
        env.insert(brain.CREATURE_ENV, "1")
        proc.setProcessEnvironment(env)
        proc.setStandardErrorFile(QProcess.nullDevice())   # 안 읽는 파이프는 막힌다
        proc.setProgram(argv[0])
        proc.setArguments(argv[1:])
        proc.readyReadStandardOutput.connect(lambda p=proc: self._read(p))
        proc.finished.connect(lambda *_a, p=proc: self._died(p))
        proc.start()
        if not proc.waitForStarted(5000):
            proc.deleteLater()
            return False
        self._proc, self._buf = proc, b""
        self._thread, self._turn, self._turns = None, None, 0
        if self.agent == "codex":
            self._send(brain.rpc(self._next_id(), "initialize",
                                 {"clientInfo": {"name": "claudlet", "version": "1"}}))
            self._send(brain.rpc(None, "initialized"))
            self._thread_rid = self._next_id()
            self._send(brain.rpc(self._thread_rid, "thread/start", brain.CODEX_THREAD))
        return True

    def _send(self, line):
        self._proc.write(line.encode("utf-8"))

    def _next_id(self):
        self._rid += 1
        return self._rid

    def _arm(self, token):
        QTimer.singleShot(int(self.timeout_s * 1000),
                          lambda p=self._proc, t=token: self._overdue(p, t))

    def _read(self, proc):
        if proc is not self._proc:
            return
        self._buf += bytes(proc.readAllStandardOutput())
        while b"\n" in self._buf and proc is self._proc:
            line, self._buf = self._buf.split(b"\n", 1)
            line = line.decode("utf-8", "replace")
            if self.agent == "codex":
                self._codex_line(line)
            else:
                self._claude_line(line)
        if self._proc is proc and not self.busy():
            self._idle.start(int(self.idle_s * 1000))

    def _died(self, proc):
        if proc is self._proc:
            self.stop()

    def _overdue(self, proc, token):
        """제한 시간이 지났는데 이 말이 아직 안 끝났다 — 머리가 멈췄다. 내리고 다음 말
        때 다시 띄우게 둔다(기다리던 말은 전부 failed → 본 세션으로)."""
        if proc is not self._proc:
            return
        if self._turn is token or any(t is token for t, _c in self._queue):
            self.stop()

    # --- claude: stream-json --------------------------------------------------

    def _claude_line(self, line):
        res = brain.stream_result(line)
        if res is None or not self._queue:
            return
        ok, text = res
        token, _c = self._queue.pop(0)
        if ok:
            self.answered.emit(token, brain.parse_reply(text))
        else:
            self.failed.emit(token)

    # --- codex: app-server -----------------------------------------------------

    def _codex_next(self):
        """스레드가 준비됐고 도는 턴이 없으면 줄 맨 앞의 말로 턴을 연다."""
        if self._thread is None or self._turn is not None or not self._queue:
            return
        token, compose = self._queue.pop(0)
        self._turn, self._turn_text = token, ""
        first = self._turns == 0
        self._turns += 1
        self._send(brain.rpc(self._next_id(), "turn/start",
                             brain.codex_turn(self._thread, compose(first))))
        self._arm(token)

    def _codex_line(self, line):
        ev = brain.codex_event(line)
        if ev is None:
            return
        if ev[0] == "reply":
            _k, rid, result, error = ev
            if rid == getattr(self, "_thread_rid", None):
                tid = ((result or {}).get("thread") or {}).get("id")
                if error or not tid:
                    self.stop()                  # 스레드를 못 열었다 — 기다리던 말은 세션으로
                    return
                self._thread = tid
                self._codex_next()
            elif error and self._turn is not None:
                token, self._turn = self._turn, None   # 턴을 못 열었다
                self.failed.emit(token)
                self._codex_next()
            return
        if ev[0] == "text" and self._turn is not None:
            self._turn_text = ev[1]              # 마지막 에이전트 말이 답이다
            return
        if ev[0] == "done" and self._turn is not None:
            token, self._turn = self._turn, None
            if ev[1]:
                self.answered.emit(token, brain.parse_reply(self._turn_text))
            else:
                self.failed.emit(token)
            self._codex_next()
