"""윈도우에서 이 세션의 프롬프트에 한 줄을 써 넣는다.

KDE 쪽 짝은 `konsole.send_text` 인데, 거기서는 Konsole 이 보안상 막아둔 D-Bus
스위치를 사용자가 직접 켜야 한다. 윈도우에는 그런 전역 스위치가 필요 없다:
콘솔에는 **입력 버퍼**가 있고, 다른 프로세스가 `AttachConsole` 로 거기 붙어
`WriteConsoleInput` 으로 키 입력을 넣을 수 있다. 창을 앞으로 끌어올 필요도 없다.

붙는 방법은 훅이 이미 쓰고 있다 — `cli/hook.py:_win_console_title` 이 같은
`FreeConsole` → `AttachConsole(pid)` 순서로 콘솔 제목을 읽는다. 여기서는 읽는
대신 쓴다.

순수한 부분(무엇을 보낼 것인가)은 `konsole.submit_text` 가 이미 갖고 있어서
그대로 쓴다 — 줄바꿈을 접고 끝에 하나만 붙이는 규칙은 OS 와 무관하다.
konsole.py 는 순수 파이썬이라 윈도우에서 import 해도 안전하다.

**펫 프로세스 안에서 직접 붙지 않는다.** AttachConsole 은 붙는 쪽 프로세스의
콘솔 상태를 바꾸고, 그 콘솔의 수명·종료 이벤트(CTRL_CLOSE_EVENT)가 우리에게
딸려온다 — GUI 인 펫이 남의 콘솔에 매이면 그 창이 닫힐 때 같이 얼어붙는다.
그래서 이 모듈을 **짧게 사는 자식 프로세스로 실행**하고(`__main__`), 펫은
그 종료 코드만 본다. 창은 CREATE_NO_WINDOW 로 뜨지 않는다.

하드웨어 미검증: 이 파일의 ctypes 경로는 실기에서 확인해야 한다.
"""
import os
import subprocess
import sys

from claudlet.platform.konsole import submit_text

KEY_EVENT = 0x0001


def send_text(pid, text, timeout=5):
    """자식 프로세스를 띄워 거기서 붙여 쓴다. 성공하면 True.

    펫은 콘솔에 손대지 않는다 — 붙는 일은 곧 죽을 프로세스가 대신 한다."""
    if submit_text(text) is None or os.name != "nt" or not pid:
        return False
    try:
        r = subprocess.run(
            [sys.executable, "-m", "claudlet.platform.winsend",
             str(int(pid)), text],
            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL, timeout=timeout,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        return r.returncode == 0
    except Exception:
        return False


def _write_here(pid, text):
    """`pid` 가 쓰는 콘솔의 입력 버퍼에 `text` 를 넣고 제출한다.

    성공하면 True. 콘솔이 없거나(GUI 로 뜬 세션) 권한이 없거나 무엇이든
    어긋나면 False — 호출자는 쪽지로 강등한다."""
    payload = submit_text(text)
    if payload is None or os.name != "nt" or not pid:
        return False
    try:
        import ctypes
        from ctypes import wintypes
    except Exception:
        return False

    class _CHAR(ctypes.Union):
        _fields_ = [("UnicodeChar", wintypes.WCHAR), ("AsciiChar", ctypes.c_char)]

    class _KEY(ctypes.Structure):
        _fields_ = [("bKeyDown", wintypes.BOOL),
                    ("wRepeatCount", wintypes.WORD),
                    ("wVirtualKeyCode", wintypes.WORD),
                    ("wVirtualScanCode", wintypes.WORD),
                    ("uChar", _CHAR),
                    ("dwControlKeyState", wintypes.DWORD)]

    class _EVENT_U(ctypes.Union):
        _fields_ = [("KeyEvent", _KEY)]

    class _RECORD(ctypes.Structure):
        _fields_ = [("EventType", wintypes.WORD), ("Event", _EVENT_U)]

    k = ctypes.windll.kernel32
    # 콘솔은 한 번에 하나만 붙을 수 있다. 우리 것을 놓고 상대 것에 붙는다.
    k.FreeConsole()
    if not k.AttachConsole(int(pid)):
        return False
    try:
        # CONIN$ 는 "지금 붙어 있는 콘솔의 입력" 이다. 3 = OPEN_EXISTING,
        # GENERIC_READ|GENERIC_WRITE = 0xC0000000, 공유 3 = READ|WRITE.
        handle = k.CreateFileW("CONIN$", 0xC0000000, 3, None, 3, 0, None)
        if handle in (0, -1, 0xFFFFFFFFFFFFFFFF):
            return False
        records = (_RECORD * (len(payload) * 2))()
        for i, ch in enumerate(payload):
            for j, down in enumerate((True, False)):
                r = records[i * 2 + j]
                r.EventType = KEY_EVENT
                r.Event.KeyEvent.bKeyDown = down
                r.Event.KeyEvent.wRepeatCount = 1
                # 문자만 넣는다: 가상 키코드 없이 UnicodeChar 만으로도 콘솔은
                # 그 글자를 읽는다. 한글처럼 키 하나에 대응하지 않는 글자를
                # 보내려면 이 길밖에 없다.
                r.Event.KeyEvent.uChar.UnicodeChar = ch
        written = wintypes.DWORD(0)
        ok = k.WriteConsoleInputW(handle, records, len(records),
                                  ctypes.byref(written))
        k.CloseHandle(handle)
        return bool(ok) and written.value == len(records)
    except Exception:
        return False
    finally:
        k.FreeConsole()


if __name__ == "__main__":       # 자식 프로세스로만 쓰인다 (send_text 가 띄운다)
    try:
        ok = _write_here(int(sys.argv[1]), sys.argv[2])
    except Exception:
        ok = False
    raise SystemExit(0 if ok else 1)
