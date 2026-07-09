import sys, os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
from PyQt6.QtWidgets import QApplication
import pet as P

_app = QApplication.instance() or QApplication(sys.argv)


def test_pet_constructs_and_uses_engine():
    p = P.Pet()
    assert hasattr(p, "engine")
    # feed a PreToolUse and confirm the engine drives the claude state
    p._handle_event({"event": "PreToolUse", "session": "a", "tool_name": "Bash"})
    p._tick()
    assert p.claude_state == "work_computer"
    p._cleanup()


def test_pet_is_session_and_host_aware():
    p = P.Pet(session_id="sess-x", host="vscode")
    try:
        assert p.host_classes == ["code"]
        assert p.sock_path.endswith("claude-pet-sess-x.sock")
        assert p._wtitle == "claude-pet-sess-x"
    finally:
        p._cleanup()


def test_sessionend_quit_is_cancelled_by_later_event():
    p = P.Pet(session_id="q1")
    try:
        p._handle_event({"event": "SessionEnd", "session": "q1"})
        assert p._quit_timer is not None          # quit armed
        p._handle_event({"event": "UserPromptSubmit", "session": "q1"})
        assert p._quit_timer is None              # a later event cancels it
    finally:
        p._cleanup()
