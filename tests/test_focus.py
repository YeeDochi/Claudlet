import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
import focus


def test_focused_true_when_active_matches(monkeypatch):
    monkeypatch.setattr(focus, "_active_window_class", lambda: "org.kde.konsole")
    assert focus.terminal_focused(["konsole"]) is True

def test_focused_false_when_other_window(monkeypatch):
    monkeypatch.setattr(focus, "_active_window_class", lambda: "firefox")
    assert focus.terminal_focused(["konsole"]) is False

def test_focused_true_when_active_unknown(monkeypatch):
    monkeypatch.setattr(focus, "_active_window_class", lambda: None)
    assert focus.terminal_focused(["konsole"]) is True

def test_focused_true_when_no_classes(monkeypatch):
    # unknown host: empty class list -> conservative suppress-celebrate
    assert focus.terminal_focused([]) is True

def test_vscode_class_matches(monkeypatch):
    monkeypatch.setattr(focus, "_active_window_class", lambda: "code")
    assert focus.terminal_focused(["code"]) is True
