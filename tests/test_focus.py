import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
import focus


def test_focused_true_when_class_is_konsole(monkeypatch):
    monkeypatch.setattr(focus, "_active_window_class", lambda: "konsole")
    assert focus.terminal_focused() is True


def test_focused_false_when_other_window(monkeypatch):
    monkeypatch.setattr(focus, "_active_window_class", lambda: "firefox")
    assert focus.terminal_focused() is False


def test_focused_true_when_unknown(monkeypatch):
    # detection unavailable -> conservative: assume focused (suppress celebrate)
    monkeypatch.setattr(focus, "_active_window_class", lambda: None)
    assert focus.terminal_focused() is True
