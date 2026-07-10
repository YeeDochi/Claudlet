import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
import hostinfo


def test_detect_vscode_by_term_program():
    assert hostinfo.detect_host({"TERM_PROGRAM": "vscode"}) == "vscode"

def test_detect_vscode_by_pid():
    assert hostinfo.detect_host({"VSCODE_PID": "123"}) == "vscode"

def test_detect_jetbrains():
    assert hostinfo.detect_host({"TERMINAL_EMULATOR": "JetBrains-JediTerm"}) == "jetbrains"

def test_detect_konsole():
    assert hostinfo.detect_host({"KONSOLE_VERSION": "250801"}) == "konsole"

def test_detect_unknown():
    assert hostinfo.detect_host({}) == "unknown"

def test_detect_macos_terminals():
    assert hostinfo.detect_host({"TERM_PROGRAM": "Apple_Terminal"}) == "apple_terminal"
    assert hostinfo.detect_host({"TERM_PROGRAM": "iTerm.app"}) == "iterm"

def test_mac_app_names():
    assert hostinfo.mac_app("vscode") == "Visual Studio Code"
    assert hostinfo.mac_app("apple_terminal") == "Terminal"
    assert hostinfo.mac_app("konsole") is None      # no macOS app for konsole
    assert hostinfo.mac_app("unknown") is None

def test_macos_host_classes_match_app_names():
    # frontmost app name on macOS is matched against these substrings
    assert hostinfo.host_classes("apple_terminal") == ["terminal"]
    assert hostinfo.host_classes("iterm") == ["iterm"]

def test_host_classes():
    assert hostinfo.host_classes("vscode") == ["code"]
    assert hostinfo.host_classes("konsole") == ["konsole"]
    assert hostinfo.host_classes("unknown") == []
    assert hostinfo.host_classes("nonsense") == []

def test_session_port_file_path(monkeypatch):
    monkeypatch.setenv("XDG_RUNTIME_DIR", "/run/user/1000")
    assert hostinfo.session_port_file("abc") == os.path.join("/run/user/1000", "claude-pet-abc.port")
    assert hostinfo.session_port_file(None) == os.path.join("/run/user/1000", "claude-pet-default.port")

def test_read_session_port_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path))
    hostinfo.write_session_port("abc", 54321)
    assert hostinfo.read_session_port("abc") == 54321

def test_read_session_port_missing(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path))
    assert hostinfo.read_session_port("nope") is None
