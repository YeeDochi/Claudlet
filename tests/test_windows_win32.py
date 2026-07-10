import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
import windows_win32


def test_proc_ancestors_empty_without_kernel32(monkeypatch):
    monkeypatch.setattr(windows_win32, "kernel32", None)
    assert windows_win32.proc_ancestors(1234) == set()


def test_proc_ancestors_empty_for_bad_pid(monkeypatch):
    assert windows_win32.proc_ancestors(None) == set()
    assert windows_win32.proc_ancestors("not-a-pid") == set()


def test_proc_ancestors_walks_real_process_tree():
    if os.name != "nt":
        return
    acc = windows_win32.proc_ancestors(os.getpid())
    assert os.getpid() in acc
    assert len(acc) >= 1


def test_proc_table_empty_without_kernel32(monkeypatch):
    monkeypatch.setattr(windows_win32, "kernel32", None)
    assert windows_win32.proc_table() == {}


def test_proc_table_reflects_real_process_tree():
    if os.name != "nt":
        return
    table = windows_win32.proc_table()
    name, ppid = table[os.getpid()]
    assert "python" in name
    assert ppid > 0


def test_activate_hwnd_noop_without_user32(monkeypatch):
    monkeypatch.setattr(windows_win32, "user32", None)
    windows_win32.activate_hwnd(12345)   # must not raise


def test_activate_hwnd_noop_for_falsy_hwnd():
    windows_win32.activate_hwnd(None)    # must not raise
    windows_win32.activate_hwnd(0)


class _FakeUser32:
    def __init__(self):
        self.calls = []
        self.foreground_set_to = None

    def IsIconic(self, hwnd):
        return False

    def GetForegroundWindow(self):
        return 111

    def GetWindowThreadProcessId(self, hwnd, out):
        return {111: 22, 999: 33}.get(hwnd, 0)

    def AttachThreadInput(self, a, b, attach):
        self.calls.append(("attach", a, b, attach))
        return 1

    def SetForegroundWindow(self, hwnd):
        self.foreground_set_to = hwnd
        return 1

    def BringWindowToTop(self, hwnd):
        self.calls.append(("top", hwnd))


class _FakeKernel32:
    def GetCurrentThreadId(self):
        return 44


def test_activate_hwnd_attaches_both_threads_and_sets_foreground(monkeypatch):
    fake_user32 = _FakeUser32()
    monkeypatch.setattr(windows_win32, "user32", fake_user32)
    monkeypatch.setattr(windows_win32, "kernel32", _FakeKernel32())

    windows_win32.activate_hwnd(999)

    assert fake_user32.foreground_set_to == 999
    assert ("attach", 44, 22, True) in fake_user32.calls   # attach to fg thread
    assert ("attach", 44, 33, True) in fake_user32.calls   # attach to target thread
    assert ("attach", 44, 22, False) in fake_user32.calls  # detach afterwards
    assert ("attach", 44, 33, False) in fake_user32.calls
    assert ("top", 999) in fake_user32.calls
