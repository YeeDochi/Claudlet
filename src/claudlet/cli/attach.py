"""claudlet-attach — bring up a pet for a Claude Code session (or standalone).

A console entry point so the /claudlet skill can just run `claudlet-attach`
instead of shelling into `python3 -c "import hostinfo; ..."` — which breaks under
a pipx install, where the package lives in an isolated venv the system python
can't import. Detects the session id and host, skips if a pet is already
attached (via the same liveness handshake the hook uses), and launches a
detached pet bound to the session.

    claudlet-attach                 attach to this session (env/newest transcript)
    claudlet-attach --session <id>  attach to a specific session
    claudlet-attach --agent <name>  which agent's session this is (default: claude)
    claudlet-attach --standalone    an unattached, decorative roaming pet
    claudlet-attach --new           START a new agent session and pair a pet to it
    claudlet-attach --no-start      don't start a session; fall back to a loose pet
"""
import glob
import os
import subprocess
import sys

from claudlet.cli import hook, utf8_output
from claudlet.core import agents, hostinfo, petconfig, session_launch
from claudlet.platform import termlaunch

utf8_output()


def _newest_session_id():
    """Fallback when $CLAUDE_CODE_SESSION_ID is unset: the session id of the
    most recently modified transcript under ~/.claude/projects/."""
    files = glob.glob(os.path.expanduser("~/.claude/projects/*/*.jsonl"))
    if not files:
        return None
    newest = max(files, key=os.path.getmtime)
    return os.path.splitext(os.path.basename(newest))[0]


def _launch(extra_args):
    """Launch a detached `python -m claudlet` that outlives this call."""
    kw = {"stdin": subprocess.DEVNULL, "stdout": subprocess.DEVNULL,
          "stderr": subprocess.DEVNULL}
    if os.name == "posix":
        kw["start_new_session"] = True            # own process group; survives us
    # ensure the child interpreter can import claudlet from a source checkout
    # (pipx/pip installs already have it importable; the extra PYTHONPATH is harmless)
    env = dict(os.environ)
    src_dir = os.path.dirname(os.path.dirname(os.path.abspath(hostinfo.__file__)))
    env["PYTHONPATH"] = src_dir + os.pathsep + env.get("PYTHONPATH", "")
    subprocess.Popen([sys.executable, "-m", "claudlet"] + extra_args, env=env, **kw)


def _claude_pid(agent):
    """The agent process this pet belongs to, or 0 if it isn't in our chain.

    The pet needs this for two things: the orphan reaper, and -- the reason a
    manually attached pet used to behave differently from a hook-launched one --
    host-window tracking. The host window is the one owned by an ANCESTOR of
    this pid, so with 0 the pet falls back to its own ancestors and click-to-
    focus/hide-when-covered quietly stop finding the right window.

    `claudlet-attach` runs from a shell inside the session just like the hook
    does, so the same upward walk from our parent finds the same process. Reuses
    the hook's walk rather than repeating it, so the two can't drift.
    """
    try:
        return hook.resolve_claude_pid(os.getppid(), hook._proc_info,
                                       needle=agents.get(agent)["proc"])
    except Exception:
        return 0                                  # no pid -> pet's old fallback


def _arg_value(argv, flag):
    if flag in argv:
        i = argv.index(flag)
        if i + 1 < len(argv):
            return argv[i + 1]
    return None


def new_session(agent=None, cwd=None, launch_term=None, launch_pet=None,
                config_dir=None):
    """Start a fresh agent session and bring up a pet bound to it.

    The id is minted here and handed to BOTH sides -- `claude --session-id`
    takes ours, so the pairing is exact instead of a race to spot the newest
    transcript. The pet goes up first: it owns the session's port file, and
    starting it after the agent would leave the agent's first hook events with
    nowhere to land.

    Returns (session_id, terminal_ok). A false `terminal_ok` means the pet is
    running and waiting for a session that never started.
    """
    agent = agent or agents.DEFAULT
    spec = agents.get(agent)
    flag = spec.get("session_id_flag")
    if not flag:
        raise ValueError(
            "%s cannot be started with a chosen session id" % agent)

    cwd = session_launch.resolve_cwd(cwd)
    session_id = session_launch.new_session_id()

    (launch_pet or _launch)(["--session", session_id,
                             "--host", hostinfo.detect_host(),
                             "--agent", agent])

    command = session_launch.build_command(
        session_id, cwd, spec.get("proc") or "claude", session_flag=flag,
        config_dir=config_dir or petconfig.pointer_config_dir())
    ok = (launch_term or termlaunch.launch)(command)
    return session_id, ok


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)

    if "--standalone" in argv:
        _launch([])
        print("standalone pet running")
        return 0

    if "--new" in argv:
        agent = _arg_value(argv, "--agent") or agents.DEFAULT
        if not termlaunch.available():
            print("no terminal app found to start a session in")
            return 2
        try:
            session_id, ok = new_session(agent, _arg_value(argv, "--cwd"))
        except ValueError as e:
            print(str(e))
            return 2
        if ok:
            print("started session %s with a pet attached" % session_id)
            return 0
        print("pet is up for session %s, but the terminal would not open"
              % session_id)
        return 1

    agent = _arg_value(argv, "--agent") or agents.DEFAULT
    host = hostinfo.detect_host()
    asked_for = _arg_value(argv, "--session")
    claude_pid = _claude_pid(agent)

    session_id = (asked_for
                  or os.environ.get("CLAUDE_CODE_SESSION_ID")
                  or (_newest_session_id() if claude_pid else None))

    # Nothing to attach to: no id was given, we are not running inside a
    # session, and so the "newest transcript" guess would bind the pet to a
    # session that ENDED. A pet paired with a dead id looks attached and
    # answers nothing, which is worse than no pet -- start a real session
    # instead. `--no-start` keeps the old decorative fallback.
    if session_id is None:
        if "--no-start" in argv:
            session_id = "default"
        else:
            if not termlaunch.available():
                print("no live session and no terminal app to start one in")
                return 2
            try:
                session_id, ok = new_session(agent, _arg_value(argv, "--cwd"))
            except ValueError as e:
                print("%s -- run it yourself, then `claudlet-attach`" % e)
                return 2
            if ok:
                print("no session to attach to; started %s with a pet"
                      % session_id)
                return 0
            print("pet is up for session %s, but the terminal would not open"
                  % session_id)
            return 1

    if hostinfo.pet_alive(session_id):
        print("already attached to session %s (host=%s)" % (session_id, host))
        return 0
    _launch(["--session", session_id, "--host", host, "--agent", agent,
             "--claude-pid", str(claude_pid)])
    print("attached to session %s (host=%s, agent=%s, %s)"
          % (session_id, host, agent,
             "pid=%d" % claude_pid if claude_pid
             else "no agent pid -> host-window tracking off"))
    return 0


def _cli():
    """console-script entry point; never hard-fails the caller."""
    try:
        sys.exit(main())
    except Exception:
        sys.exit(0)


if __name__ == "__main__":
    _cli()
