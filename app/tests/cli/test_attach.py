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


# ---------- --new: start a session and pair a pet to it ----------

import io

import pytest

from claudlet.cli import attach as A


class _Spy:
    """Captures what each half was launched with."""
    def __init__(self, term_ok=True):
        self.pet_argv = None
        self.command = None
        self._ok = term_ok

    def pet(self, argv):
        self.pet_argv = list(argv)

    def term(self, command):
        self.command = command
        return self._ok


def test_both_halves_get_the_same_session_id():
    """The whole point: no racing to spot the newest transcript."""
    spy = _Spy()
    sid, ok = A.new_session("claude", "/tmp", spy.term, spy.pet)
    assert ok
    assert sid in spy.pet_argv
    assert sid in spy.command


def test_the_pet_is_bound_to_that_session():
    spy = _Spy()
    sid, _ = A.new_session("claude", "/tmp", spy.term, spy.pet)
    assert spy.pet_argv[spy.pet_argv.index("--session") + 1] == sid


def test_the_session_starts_in_the_requested_directory():
    spy = _Spy()
    A.new_session("claude", "/tmp", spy.term, spy.pet)
    assert spy.command.startswith("cd '/tmp' &&")


def test_each_call_makes_a_different_session():
    a, b = _Spy(), _Spy()
    first, _ = A.new_session("claude", "/tmp", a.term, a.pet)
    second, _ = A.new_session("claude", "/tmp", b.term, b.pet)
    assert first != second


def test_the_pet_comes_up_even_if_the_terminal_will_not_open():
    """It owns the port file; the caller reports the half-failure."""
    spy = _Spy(term_ok=False)
    sid, ok = A.new_session("claude", "/tmp", spy.term, spy.pet)
    assert ok is False
    assert sid in spy.pet_argv


def test_an_agent_that_cannot_take_an_id_is_refused():
    """Better than opening a window that just prints a usage error."""
    spy = _Spy()
    with pytest.raises(ValueError):
        A.new_session("codex", "/tmp", spy.term, spy.pet)


def test_the_cli_reports_the_new_session(monkeypatch, capsys):
    spy = _Spy()
    monkeypatch.setattr(A.termlaunch, "available", lambda: True)
    monkeypatch.setattr(A.termlaunch, "launch", spy.term)
    monkeypatch.setattr(A, "_launch", spy.pet)
    assert A.main(["--new", "--cwd", "/tmp"]) == 0
    assert "started session" in capsys.readouterr().out


def test_the_cli_says_so_when_no_terminal_exists(monkeypatch, capsys):
    monkeypatch.setattr(A.termlaunch, "available", lambda: False)
    assert A.main(["--new"]) == 2
    assert "no terminal" in capsys.readouterr().out


def test_the_cli_reports_a_pet_without_a_session(monkeypatch, capsys):
    spy = _Spy(term_ok=False)
    monkeypatch.setattr(A.termlaunch, "available", lambda: True)
    monkeypatch.setattr(A.termlaunch, "launch", spy.term)
    monkeypatch.setattr(A, "_launch", spy.pet)
    assert A.main(["--new"]) == 1
    assert "would not open" in capsys.readouterr().out


def test_the_cli_refuses_an_unsupported_agent(monkeypatch, capsys):
    monkeypatch.setattr(A.termlaunch, "available", lambda: True)
    monkeypatch.setattr(A, "_launch", lambda argv: None)
    assert A.main(["--new", "--agent", "codex"]) == 2
    assert "session id" in capsys.readouterr().out


def test_plain_attach_still_does_not_start_a_session(monkeypatch):
    """--new is opt-in; the old behaviour must not change."""
    launched = []
    monkeypatch.setattr(A.termlaunch, "launch",
                        lambda c: launched.append(c) or True)
    monkeypatch.setattr(A, "_launch", lambda argv: None)
    monkeypatch.setattr(A.hostinfo, "pet_alive", lambda sid: False)
    A.main(["--session", "abc"])
    assert launched == []


# ---------- no session to attach to -> start one ----------

@pytest.fixture
def _detached(monkeypatch):
    """Not inside a session: no env id, no claude ancestor."""
    monkeypatch.delenv("CLAUDE_CODE_SESSION_ID", raising=False)
    monkeypatch.setattr(A, "_claude_pid", lambda agent: 0)
    monkeypatch.setattr(A.hostinfo, "pet_alive", lambda sid: False)
    spy = _Spy()
    monkeypatch.setattr(A.termlaunch, "available", lambda: True)
    monkeypatch.setattr(A.termlaunch, "launch", spy.term)
    monkeypatch.setattr(A, "_launch", spy.pet)
    return spy


def test_with_no_session_a_new_one_is_started(_detached, capsys):
    assert A.main([]) == 0
    assert "started" in capsys.readouterr().out
    assert _detached.command is not None


def test_the_started_session_gets_its_own_pet(_detached):
    A.main([])
    sid = _detached.pet_argv[_detached.pet_argv.index("--session") + 1]
    assert sid in _detached.command


def test_a_stale_transcript_is_not_attached_to(_detached, monkeypatch):
    """The old fallback bound the pet to a session that had already ended.

    A pet paired with a dead id looks attached and answers nothing, which is
    worse than no pet at all.
    """
    monkeypatch.setattr(A, "_newest_session_id", lambda: "long-finished")
    A.main([])
    assert "long-finished" not in (_detached.command or "")


def test_a_transcript_is_used_when_we_are_inside_a_session(monkeypatch, capsys):
    """Being inside one is what makes the newest transcript trustworthy."""
    monkeypatch.delenv("CLAUDE_CODE_SESSION_ID", raising=False)
    monkeypatch.setattr(A, "_claude_pid", lambda agent: 4242)
    monkeypatch.setattr(A, "_newest_session_id", lambda: "live-one")
    monkeypatch.setattr(A.hostinfo, "pet_alive", lambda sid: False)
    monkeypatch.setattr(A, "_launch", lambda argv: None)
    started = []
    monkeypatch.setattr(A.termlaunch, "launch",
                        lambda c: started.append(c) or True)
    A.main([])
    assert started == []                      # attached, nothing started
    assert "live-one" in capsys.readouterr().out


def test_an_explicit_session_is_never_second_guessed(_detached, capsys):
    A.main(["--session", "chosen-id"])
    assert _detached.command is None
    assert "chosen-id" in capsys.readouterr().out


def test_the_env_session_is_used_when_set(monkeypatch, capsys):
    monkeypatch.setenv("CLAUDE_CODE_SESSION_ID", "from-env")
    monkeypatch.setattr(A, "_claude_pid", lambda agent: 0)
    monkeypatch.setattr(A.hostinfo, "pet_alive", lambda sid: False)
    monkeypatch.setattr(A, "_launch", lambda argv: None)
    started = []
    monkeypatch.setattr(A.termlaunch, "launch",
                        lambda c: started.append(c) or True)
    A.main([])
    assert started == []
    assert "from-env" in capsys.readouterr().out


def test_no_start_keeps_the_old_loose_pet(_detached, capsys):
    """The escape hatch for someone who just wants a decorative creature."""
    assert A.main(["--no-start"]) == 0
    assert _detached.command is None
    assert "default" in capsys.readouterr().out


def test_no_terminal_is_reported_rather_than_guessed_at(monkeypatch, capsys):
    monkeypatch.delenv("CLAUDE_CODE_SESSION_ID", raising=False)
    monkeypatch.setattr(A, "_claude_pid", lambda agent: 0)
    monkeypatch.setattr(A.termlaunch, "available", lambda: False)
    assert A.main([]) == 2
    assert "no live session" in capsys.readouterr().out


def test_an_agent_that_cannot_be_started_says_what_to_do(monkeypatch, capsys):
    monkeypatch.delenv("CLAUDE_CODE_SESSION_ID", raising=False)
    monkeypatch.setattr(A, "_claude_pid", lambda agent: 0)
    monkeypatch.setattr(A.termlaunch, "available", lambda: True)
    monkeypatch.setattr(A, "_launch", lambda argv: None)
    assert A.main(["--agent", "codex"]) == 2
    assert "run it yourself" in capsys.readouterr().out


def test_standalone_still_starts_nothing(_detached, capsys):
    assert A.main(["--standalone"]) == 0
    assert _detached.command is None
