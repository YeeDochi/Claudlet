"""크리처 머리를 띄우고 말을 주고받는 얇은 Qt 어댑터. 무엇을 보내고 어떻게 읽을지는
`core/brain.py`(순수)가 정한다.

claude 는 한 번 띄워 두고 stream-json 으로 계속 말을 넣는다. 들어간 순서대로 답이
나오므로 기다리는 말들을 줄(`_queue`)로 세워 두고 결과가 나올 때마다 맨 앞의 것에
붙인다. 오래 말이 없으면 내린다 — 펫 하나에 220MB(실측)를 늘 물려 둘 이유는 없다.

codex 는 말할 때마다 `codex exec` 를 한 번 띄운다.

어떤 경우에도 말은 `answered` 아니면 `failed` 로 한 번 돌아온다. failed 를 받은
쪽(펫)이 그 말을 본 세션으로 넘긴다 — 말이 사라지지 않게 하는 약속은 여기서 시작한다.
"""
import os

from PyQt6.QtCore import QObject, QProcess, QProcessEnvironment, QTimer, pyqtSignal

from claudlet.core import brain
from claudlet.core import hostinfo

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
        self._proc = None          # 띄워 둔 claude
        self._buf = b""
        self._queue = []           # 답을 기다리는 token 들 (들어간 순서)
        self._oneshots = {}        # codex: proc -> (token, outfile)
        self._seq = 0
        self._idle = QTimer(self)
        self._idle.setSingleShot(True)
        self._idle.timeout.connect(self.stop)

    # --- 바깥에서 쓰는 것 ----------------------------------------------------

    def busy(self):
        return bool(self._queue or self._oneshots)

    def ask(self, token, compose):
        """말 하나를 넣는다. `compose(first)` 가 보낼 글을 만든다 — 새로 띄운 머리면
        first=True 라 지시와 맥락을 처음부터 실어야 한다."""
        self._idle.stop()
        if self.agent == "codex":
            self._ask_once(token, compose(True))
            return
        first = self._proc is None
        if first and not self._spawn():
            self.failed.emit(token)
            return
        self._queue.append(token)
        self._proc.write(brain.stream_message(compose(first)).encode("utf-8"))
        QTimer.singleShot(int(self.timeout_s * 1000),
                          lambda p=self._proc, t=token: self._overdue(p, t))

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
        pending, self._queue = self._queue, []
        for token in pending:
            self.failed.emit(token)
        for proc, (token, _out) in list(self._oneshots.items()):
            self._oneshots.pop(proc, None)
            proc.kill()
            self.failed.emit(token)

    # --- claude: 띄워 둔 머리 -----------------------------------------------

    def _env(self):
        env = QProcessEnvironment.systemEnvironment()
        env.insert(brain.CREATURE_ENV, "1")
        return env

    def _spawn(self):
        argv = brain.stream_command(self.exe)
        proc = QProcess(self)
        proc.setProcessEnvironment(self._env())
        proc.setProgram(argv[0])
        proc.setArguments(argv[1:])
        proc.readyReadStandardOutput.connect(lambda p=proc: self._read(p))
        proc.finished.connect(lambda *_a, p=proc: self._died(p))
        proc.start()
        if not proc.waitForStarted(5000):
            proc.deleteLater()
            return False
        self._proc, self._buf = proc, b""
        return True

    def _read(self, proc):
        if proc is not self._proc:
            return
        self._buf += bytes(proc.readAllStandardOutput())
        while b"\n" in self._buf:
            line, self._buf = self._buf.split(b"\n", 1)
            res = brain.stream_result(line.decode("utf-8", "replace"))
            if res is None or not self._queue:
                continue
            ok, text = res
            token = self._queue.pop(0)
            if ok:
                self.answered.emit(token, brain.parse_reply(text))
            else:
                self.failed.emit(token)
        if not self.busy():
            self._idle.start(int(self.idle_s * 1000))

    def _died(self, proc):
        if proc is not self._proc:
            return
        self._proc = None
        proc.deleteLater()
        pending, self._queue = self._queue, []
        for token in pending:
            self.failed.emit(token)

    def _overdue(self, proc, token):
        """제한 시간이 지났는데 이 말이 아직 줄에 있다 — 머리가 멈췄다. 내리고 다시
        띄우게 둔다(기다리던 말은 전부 failed → 본 세션으로)."""
        if proc is self._proc and token in self._queue:
            self.stop()

    # --- codex: 말할 때마다 한 번 -------------------------------------------

    def _ask_once(self, token, text):
        self._seq += 1
        outfile = os.path.join(hostinfo.runtime_dir(),
                               "claudlet-%s-%d.brain" % (self.session_id, self._seq))
        argv = brain.command("codex", self.exe, outfile)
        proc = QProcess(self)
        proc.setProcessEnvironment(self._env())
        proc.setProgram(argv[0])
        proc.setArguments(argv[1:])
        proc.finished.connect(lambda *_a, p=proc: self._once_done(p))
        proc.errorOccurred.connect(
            lambda err, p=proc: err == QProcess.ProcessError.FailedToStart
            and self._once_done(p))
        self._oneshots[proc] = (token, outfile)
        proc.start()
        proc.write(text.encode("utf-8"))
        proc.closeWriteChannel()
        QTimer.singleShot(int(self.timeout_s * 1000),
                          lambda p=proc: p in self._oneshots and p.kill())

    def _once_done(self, proc):
        info = self._oneshots.pop(proc, None)
        if info is None:
            return
        token, outfile = info
        out = None
        if (proc.exitStatus() == QProcess.ExitStatus.NormalExit
                and proc.exitCode() == 0):
            try:
                with open(outfile, encoding="utf-8") as f:
                    out = f.read()
            except OSError:
                out = bytes(proc.readAllStandardOutput()).decode("utf-8", "replace")
        try:
            os.unlink(outfile)
        except OSError:
            pass
        proc.deleteLater()
        if out is None:
            self.failed.emit(token)
        else:
            self.answered.emit(token, brain.parse_reply(out))
