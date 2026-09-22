#!/usr/bin/env python3
"""claudlet-hook — per-session bridge between Claude Code and its pet.

Claude Code invokes this for each hook event (event name in argv[1], JSON
payload on stdin). It:
  * on SessionStart, launches a pet for this session if one isn't already
    running (launched from inside the session, so it inherits host app + env);
  * forwards every event to that session's pet over a loopback TCP socket,
    whose port is published in $XDG_RUNTIME_DIR/claudlet-<session_id>.port.

Must never block or fail Claude: every error is swallowed and exit is always 0.
"""
import sys
import os
import re
import json
import socket
import subprocess

# stdin matters here on top of the usual output fix: Claude Code always sends
# the hook payload as UTF-8 JSON, and Python's default stdin codec follows the
# console codepage (cp949 on Korean Windows), which mangles any multi-byte
# content in it.
from claudlet.cli import utf8_streams

utf8_streams(sys.stdin, sys.stdout, sys.stderr)

try:
    from claudlet.core import hostinfo
    from claudlet.core import agents
    from claudlet.core import outbox
except Exception:
    hostinfo = None
    agents = None
    outbox = None


def agent_arg(argv):
    """Which agent this hook invocation serves. The installer puts
    `--agent <name>` in the registered command; an old settings.json without
    it (or a name we don't know) means Claude Code."""
    for i, a in enumerate(argv):
        if a == "--agent" and i + 1 < len(argv):
            name = argv[i + 1]
            break
        if a.startswith("--agent="):
            name = a.split("=", 1)[1]
            break
    else:
        return agents.DEFAULT
    return name if name in agents.AGENTS else agents.DEFAULT


_ROLLOUT = re.compile(
    r"rollout-.*-([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})\.jsonl$",
    re.I)


def session_of(data):
    """The session key for this payload. Codex may omit session_id but always
    names the transcript, whose filename ends in the session uuid."""
    sid = data.get("session_id")
    if sid:
        return str(sid)
    m = _ROLLOUT.search(str(data.get("transcript_path") or "").replace("\\", "/"))
    return m.group(1) if m else "default"


def build_message(argv, data, title=None):
    """Build the JSON line to send to the pet. Pure; unit-tested.

    `title` is the terminal tab title this session lives in (see console_title).
    It is NOT part of the hook payload -- Claude Code sends no title field -- so
    the caller reads it off the console and passes it in.
    """
    event = (argv[1] if len(argv) > 1 else "") or data.get("hook_event_name", "")
    msg = {"event": event, "session": session_of(data)}
    if title:
        msg["title"] = title
    # 턴이 시작되는 순간의 transcript 경로. 펫은 이때의 마지막 대사를 기준점으로
    # 삼아, 그 뒤에 나타난 줄만 "이번 턴 것"으로 센다 — 갓 뜬 펫이 지난 대화의
    # 대사를 이번 답으로 착각해 띄우던 것을 막는다.
    if event == "UserPromptSubmit" and data.get("transcript_path"):
        msg["transcript"] = str(data["transcript_path"])
    for key in ("tool_name", "notification_type", "error_type",
                "permission_mode"):
        val = data.get(key)
        if val:
            msg[key] = val
    # Companion lifetime (issue #2): Stop/SubagentStop payloads carry a
    # background_tasks snapshot -- Claude Code's own view of what is still
    # running, i.e. exactly what its UI shows. Forward counts of the RUNNING
    # tasks so the companion is present precisely while the UI shows background
    # work. The stopping agent's OWN entry is excluded: it lists itself as
    # running even at its final SubagentStop, and when that stop is the last
    # hook event of an idle session (a background agent finishing while the
    # user is away) no later snapshot ever arrives to clear it -- counting self
    # left the companion up forever. Excluding self makes the final stop read
    # as an empty snapshot; the engine's depart GRACE (not instant departure)
    # is what keeps the companion trailing the UI instead of leading it.
    bt = data.get("background_tasks")
    if isinstance(bt, list):
        self_id = data.get("agent_id")
        # Only shell/subagent entries are real per-run work; an unknown
        # always-running entry type would otherwise pin bg_tasks above zero and
        # hold the companion up forever.
        running = [b for b in bt if isinstance(b, dict)
                   and b.get("status") == "running" and b.get("id") != self_id
                   and b.get("type") in ("shell", "subagent")]
        msg["bg_tasks"] = len(running)                                  # any bg work
        msg["bg_agents"] = sum(1 for b in running
                               if b.get("type") == "subagent")          # other agents
    return json.dumps(msg) + "\n"


def resolve_claude_pid(start_pid, proc_info, max_hops=32, needle="claude"):
    """Walk up the parent chain from start_pid to the Claude Code process.

    Claude runs hooks under a transient shell, so os.getppid() is that
    shell (which exits within ~1s) rather than the long-lived `claude`
    process. If the pet's orphan reaper polled the shell pid it would quit
    ~3s after launch. So climb parents until one whose command name
    contains 'claude', and give the reaper *that* pid.

    proc_info(pid) -> (comm, ppid) or None if the pid is gone. Returns 0
    if no claude ancestor is found (caller then skips the reaper — the pet
    simply won't self-reap, same as a manually launched one).
    """
    pid = start_pid
    seen = set()
    for _ in range(max_hops):
        if pid <= 1 or pid in seen:
            return 0
        seen.add(pid)
        info = proc_info(pid)
        if info is None:
            return 0
        comm, ppid = info
        if needle in comm:
            return pid
        pid = ppid
    return 0


def ancestor_chain(start_pid, proc_info, max_hops=32):
    """Ancestor pids of `start_pid`, NEAREST FIRST, excluding start_pid itself.

    `resolve_claude_pid` only needs the first 'claude' hit, but console_title
    needs the whole ordered chain, so the walk is factored out here. Pure: the
    same `proc_info(pid) -> (comm, ppid)` injection, so it tests as data."""
    out, seen, pid = [], {start_pid}, start_pid
    for _ in range(max_hops):
        info = proc_info(pid)
        if info is None:
            break
        pid = info[1]
        if pid <= 1 or pid in seen:
            break
        seen.add(pid)
        out.append(pid)
    return out


def console_title(pids, attach, read):
    """The tab title of this session's terminal, or None.

    Claude Code keeps the terminal title in sync with the conversation, and
    Windows Terminal shows that string as the tab's name -- which is the only
    thing that can tell two sessions apart once their pids collapse into one
    terminal process (see platform/winterm.py). The hook runs inside the pane,
    so it can read the title straight off the console.

    `pids` must be ordered FARTHEST ANCESTOR FIRST. That ordering is what makes
    this correct rather than lucky: Claude Code gives each child it spawns a
    fresh console whose title is just the child's exe path, so walking upward
    from the hook would return that junk. Walking DOWNWARD from the top, the
    processes above the pane's shell (windowsterminal.exe, explorer.exe) own no
    console at all and their attach simply fails, so the first success is the
    pane's own shell -- the console Claude Code is writing the title to.

    `attach(pid)` -> truthy if this process is now attached to that pid's
    console; `read()` -> the current console title. Injected so the decision
    logic tests without a real console.
    """
    for pid in pids:
        try:
            if not attach(pid):
                continue
            title = read()
        except Exception:
            continue
        if title:
            return title
    return None


def _win_console_title(start_pid):
    """console_title() wired to the real Win32 console API. Windows-only;
    None anywhere else, on any ctypes failure, or when nothing is attachable.

    Never raises: a hook must not fail Claude, and a pet that merely can't
    switch tabs still raises the terminal window."""
    if os.name != "nt":
        return None
    try:
        import ctypes
        k = ctypes.windll.kernel32

        def attach(pid):
            # A console can only be attached one at a time, so drop whatever
            # Claude Code handed us before trying the next candidate. stdout is
            # a pipe here (Claude Code captures hook output), so detaching the
            # console cannot disturb the reply we still have to write.
            k.FreeConsole()
            return bool(k.AttachConsole(int(pid)))

        def read():
            buf = ctypes.create_unicode_buffer(1024)
            k.GetConsoleTitleW(buf, 1024)
            return buf.value

        chain = ancestor_chain(start_pid, _proc_info)
        return console_title(list(reversed(chain)), attach, read)
    except Exception:
        return None


_win32_proc_table = None   # lazy, cached per hook invocation (see below)


def _proc_info(pid):
    """(comm, ppid) for a pid, or None if it's gone/undetectable.
    Linux: /proc/<pid>/stat. Windows: one cached Toolhelp snapshot (process
    names/parents don't change mid-lookup, so we only take it once even
    though resolve_claude_pid calls this per hop). macOS: undetectable, so
    the reaper is simply skipped there."""
    if os.name == "nt":
        global _win32_proc_table
        if _win32_proc_table is None:
            try:
                from claudlet.platform.geom import win32
                _win32_proc_table = win32.proc_table()
            except Exception:
                _win32_proc_table = {}
        return _win32_proc_table.get(pid)
    try:
        with open("/proc/%d/stat" % pid) as f:
            data = f.read()
        # format: `pid (comm) state ppid ...`; comm may contain spaces/parens
        rparen = data.rindex(")")
        comm = data[data.index("(") + 1:rparen]
        fields = data[rparen + 2:].split()
        return comm, int(fields[1])   # fields[0]=state, fields[1]=ppid
    except (OSError, ValueError, IndexError):
        return None


def _launch_pet(session_id, host, agent):
    # Give the reaper the real agent pid, not our transient shell parent.
    claude_pid = resolve_claude_pid(os.getppid(), _proc_info,
                                    needle=agents.get(agent)["proc"])
    # Launch the pet as `python -m claudlet` with THIS interpreter so it works
    # cross-OS; detach so it outlives the hook. start_new_session is POSIX-only.
    kw = {"stdin": subprocess.DEVNULL, "stdout": subprocess.DEVNULL,
          "stderr": subprocess.DEVNULL}
    if os.name == "posix":
        kw["start_new_session"] = True
    # Make sure the child can import claudlet from a source checkout (pipx
    # installs already have it importable; the extra PYTHONPATH is harmless).
    env = dict(os.environ)
    src_dir = os.path.dirname(os.path.dirname(os.path.abspath(hostinfo.__file__)))
    env["PYTHONPATH"] = src_dir + os.pathsep + env.get("PYTHONPATH", "")
    subprocess.Popen(
        [sys.executable, "-m", "claudlet", "--session", session_id,
         "--host", host, "--agent", agent,
         "--claude-pid", str(claude_pid)], env=env, **kw)


def _send(port, payload):
    if port is None:
        raise OSError("no pet port for this session")
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(0.3)
    s.connect((hostinfo.LOOPBACK, port))
    s.sendall(payload)
    s.close()


def main():
    if hostinfo is None:
        return
    raw = ""
    try:
        if not sys.stdin.isatty():
            raw = sys.stdin.read()
    except Exception:
        pass
    try:
        data = json.loads(raw) if raw.strip() else {}
    except Exception:
        data = {}

    event = (sys.argv[1] if len(sys.argv) > 1 else "") or data.get("hook_event_name", "")
    agent = agent_arg(sys.argv)
    session_id = session_of(data)

    # Codex tool workers emit SessionStart with a transcript path but never
    # create that rollout. They are implementation details, not user sessions.
    if (event == "SessionStart" and agent == "codex"
            and not os.path.isfile(str(data.get("transcript_path") or ""))):
        return

    if os.environ.get("CLAUDLET_DEBUG_HOOK"):
        try:
            import time as _time
            import tempfile as _tempfile
            with open(os.path.join(_tempfile.gettempdir(),
                                   "claudlet-hookdebug.jsonl"), "a") as f:
                f.write(json.dumps({"t": _time.time(), "agent": agent,
                                    "event": event, "payload": data},
                                   ensure_ascii=False) + "\n")
        except Exception:
            pass

    # Opt-in companion-lifetime diagnostic (CLAUDLET_DEBUG_BG=1), same spirit as
    # CLAUDLET_DEBUG_GEOM: append each Stop/SubagentStop's raw background_tasks
    # to <tmp>/claudlet-bgdebug.jsonl so "the companion won't leave" can be
    # diagnosed from what Claude Code actually reported on that machine,
    # instead of guessed at. Never raises (hooks must not fail Claude).
    if os.environ.get("CLAUDLET_DEBUG_BG") and event in ("Stop", "SubagentStop",
                                                         "StopFailure"):
        try:
            import time as _time
            import tempfile as _tempfile
            with open(os.path.join(_tempfile.gettempdir(),
                                   "claudlet-bgdebug.jsonl"), "a") as f:
                f.write(json.dumps({
                    "t": _time.time(), "event": event,
                    "agent_id": data.get("agent_id"),
                    "background_tasks": data.get("background_tasks"),
                }) + "\n")
        except Exception:
            pass

    # on session start, bring up this session's pet if one isn't already there
    # (verified by handshake, so a stale port file can't suppress the launch)
    launched_fresh = False
    if event == "SessionStart":
        try:
            # capture BEFORE pet_alive(), which unlinks the file on a refused
            # connect. Only a brand-new session (never had a port file) is safe
            # to skip sending to: there's provably nothing to send to yet. If a
            # port file DID exist, pet_alive()'s False can also mean "our own
            # pet, alive, just slow to answer the ping" (busy Qt event loop) —
            # not necessarily dead — so still attempt the send below rather than
            # dropping this event on a timing coincidence.
            had_port = hostinfo.read_session_port(session_id) is not None
            if not hostinfo.pet_alive(session_id):
                _launch_pet(session_id, hostinfo.detect_host(), agent)
                launched_fresh = not had_port
        except Exception:
            pass

    if not launched_fresh:
        try:
            # Read the tab title on EVERY event, not once at SessionStart: the
            # title tracks the conversation and changes as work goes on, and the
            # events that matter most for click-to-focus (Notification, i.e.
            # Claude is asking) are exactly when it must be current.
            _send(hostinfo.read_session_port(session_id),
                  build_message(sys.argv, data, _win_console_title(os.getpid()))
                  .encode())
        except Exception:
            pass  # pet not running / not ready — ignore silently

    say_reply(event, session_id, data)
    deliver_outbox(event, session_id, agent)


# 펫이 말할 수 있는 유일한 경계. 에이전트가 일하는 중이면 PostToolUse 에서,
# 놀고 있었으면 다음 UserPromptSubmit 에서 도착한다. 두 이벤트만 stdout 의
# additionalContext 를 이런 형태로 받는다 (Claude Code 2.1.278 의 훅 출력
# 스키마를 바이너리에서 직접 확인했다).
OUTBOX_EVENTS = ("UserPromptSubmit", "PostToolUse")


def say_reply(event, session_id, data):
    """턴이 끝났다고 펫에게 알린다. 읽는 일은 펫이 한다.

    여기서 transcript 를 읽었더니 이번 턴 답이 아직 파일에 없어서 지난 턴
    대사를 물어왔다(말풍선이 한 턴씩 늦었다). 훅은 기다릴 수 없고 — 기다리면
    턴 종료가 그만큼 늦어진다 — 펫은 기다릴 수 있다. 그래서 경로만 넘긴다."""
    if outbox is None or event not in ("Stop", "SubagentStop"):
        return
    path = data.get("transcript_path")
    if not path:
        return
    try:
        _send(hostinfo.read_session_port(session_id),
              (json.dumps({"cmd": "turn_end", "transcript": str(path),
                           "session": session_id}) + "\n").encode())
    except Exception:
        pass


def deliver_outbox(event, session_id, agent=None):
    """펫이 쌓아둔 쪽지를 에이전트에게 실어 보낸다. 없으면 한 글자도 쓰지 않는다.

    훅의 stdout 은 에이전트가 파싱하므로, 여기서 나는 어떤 사고도 밖으로
    나가면 안 된다 — 늦게 배달되는 쪽지가 깨진 훅보다 싸다."""
    if outbox is None or event not in OUTBOX_EVENTS:
        return
    # Claude Code 와 Codex 는 이 부분의 와이어 포맷이 같다. 둘 다 바이너리에
    # 박힌 스키마로 확인했다 (Codex 0.1xx 의 UserPromptSubmitHookSpecificOutputWire
    # / PostToolUseHookSpecificOutputWire 가 {hookEventName, additionalContext}
    # 를 hookSpecificOutput 아래에 그대로 받는다). 그래서 에이전트를 가르지 않는다.
    try:
        payload = outbox.payload(event, outbox.take(session_id))
        if payload:
            sys.stdout.write(json.dumps(payload, ensure_ascii=False))
    except Exception:
        pass


def _cli():
    """console-script entry point — hooks must always succeed (exit 0)."""
    try:
        main()
    except Exception:
        pass
    sys.exit(0)


if __name__ == "__main__":
    _cli()
