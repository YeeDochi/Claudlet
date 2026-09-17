import pytest

from claudlet.cli import attach

# Grabbed at import, before any fixture can patch the module attribute, so the
# walk tests below exercise the real function.
_real_claude_pid = attach._claude_pid


@pytest.fixture
def pinned_pid(monkeypatch):
    """The launch-arg tests are about which ARGS reach the pet, not about what
    process tree the test runner happens to sit in -- pin the walk."""
    monkeypatch.setattr(attach, "_claude_pid", lambda agent: 4242)


def test_arg_value():
    assert attach._arg_value(["--session", "abc"], "--session") == "abc"
    assert attach._arg_value(["--session"], "--session") is None   # flag, no value
    assert attach._arg_value([], "--session") is None


def test_standalone_launches_unbound(monkeypatch):
    calls = []
    monkeypatch.setattr(attach, "_launch", lambda args: calls.append(args))
    assert attach.main(["--standalone"]) == 0
    assert calls == [[]]                          # no --session/--host


def test_attach_skips_when_already_alive(monkeypatch):
    monkeypatch.setattr(attach.hostinfo, "detect_host", lambda: "konsole")
    monkeypatch.setattr(attach.hostinfo, "pet_alive", lambda sid, **k: True)
    launched = []
    monkeypatch.setattr(attach, "_launch", lambda args: launched.append(args))
    assert attach.main(["--session", "s1"]) == 0
    assert launched == []                          # alive -> don't double-launch


def test_attach_launches_when_dead(monkeypatch, pinned_pid):
    monkeypatch.setattr(attach.hostinfo, "detect_host", lambda: "konsole")
    monkeypatch.setattr(attach.hostinfo, "pet_alive", lambda sid, **k: False)
    launched = []
    monkeypatch.setattr(attach, "_launch", lambda args: launched.append(args))
    assert attach.main(["--session", "s1"]) == 0
    assert launched == [["--session", "s1", "--host", "konsole",
                         "--agent", "claude", "--claude-pid", "4242"]]


def test_attach_session_from_env(monkeypatch, pinned_pid):
    monkeypatch.setenv("CLAUDE_CODE_SESSION_ID", "envsid")
    monkeypatch.setattr(attach.hostinfo, "detect_host", lambda: "code")
    monkeypatch.setattr(attach.hostinfo, "pet_alive", lambda sid, **k: False)
    launched = []
    monkeypatch.setattr(attach, "_launch", lambda args: launched.append(args))
    attach.main([])                                # no --session -> use env
    assert launched == [["--session", "envsid", "--host", "code",
                         "--agent", "claude", "--claude-pid", "4242"]]


def test_attach_passes_the_named_agent(monkeypatch, pinned_pid):
    monkeypatch.setattr(attach.hostinfo, "detect_host", lambda: "konsole")
    monkeypatch.setattr(attach.hostinfo, "pet_alive", lambda sid, **k: False)
    launched = []
    monkeypatch.setattr(attach, "_launch", lambda args: launched.append(args))
    attach.main(["--session", "s1", "--agent", "codex"])
    assert launched == [["--session", "s1", "--host", "konsole",
                         "--agent", "codex", "--claude-pid", "4242"]]


def test_claude_pid_walks_up_to_the_agent(monkeypatch):
    # attach runs under the session's shell, so the walk must reach the agent
    # process the same way the hook's does -- that pid is what pins the pet to
    # its host window.
    monkeypatch.setattr(attach.os, "getppid", lambda: 90)
    monkeypatch.setattr(attach.hook, "_proc_info",
                        lambda pid: {90: ("bash", 80),
                                     80: ("claude", 1)}.get(pid))
    assert _real_claude_pid("claude") == 80


def test_claude_pid_uses_the_agents_own_needle(monkeypatch):
    monkeypatch.setattr(attach.os, "getppid", lambda: 90)
    monkeypatch.setattr(attach.hook, "_proc_info",
                        lambda pid: {90: ("bash", 80),
                                     80: ("codex", 1)}.get(pid))
    assert _real_claude_pid("codex") == 80
    assert _real_claude_pid("claude") == 0        # 'claude' must not match codex


def test_claude_pid_is_zero_when_the_agent_is_not_an_ancestor(monkeypatch):
    monkeypatch.setattr(attach.os, "getppid", lambda: 90)
    monkeypatch.setattr(attach.hook, "_proc_info",
                        lambda pid: {90: ("bash", 1)}.get(pid))
    assert _real_claude_pid("claude") == 0


def test_claude_pid_never_raises(monkeypatch):
    # a failed walk must degrade to the pet's old fallback, not kill the attach
    def boom(pid):
        raise OSError("no process table here")
    monkeypatch.setattr(attach.hook, "_proc_info", boom)
    assert _real_claude_pid("claude") == 0
