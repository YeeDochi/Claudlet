"""Shared helpers: detect the Claude Code host app, and per-session socket paths.

Pure and dependency-free so both `bin/claudlet-hook` (runs inside the Claude
Code session, sees its env) and `src/pet.py` can import it and agree.
"""
import os
import socket
import tempfile
import time

LOOPBACK = "127.0.0.1"

# Liveness handshake: a client sends PING and a real pet answers with a line
# containing BANNER_MARK. A bare TCP connect can't tell our pet apart from an
# unrelated process that the OS happened to hand the same (stale) port number,
# so every liveness check goes through this round-trip instead. Same on every
# OS — the whole project speaks one loopback-TCP protocol.
PING = b'{"cmd": "ping"}\n'
BANNER_MARK = "claudlet"

# host -> window-class / app-name substrings used to match/focus that host's
# window. On Linux these match KWin resourceClass; on macOS the frontmost app
# name (from AppleScript) is matched against the same substrings.
HOST_CLASSES = {
    "vscode": ["code"],
    "jetbrains": ["jetbrains"],
    "konsole": ["konsole"],
    "apple_terminal": ["terminal"],
    "iterm": ["iterm"],
    "unknown": [],
}

# host -> macOS application name, for `osascript ... to activate` (click-to-focus).
# None where we can't name it reliably (varies per JetBrains IDE).
MAC_APP = {
    "vscode": "Visual Studio Code",
    "apple_terminal": "Terminal",
    "iterm": "iTerm",
}

# host -> Win32 window-class substrings, for the click-to-focus fallback when
# no pid-pinned host window was found. Win32 class names are unrelated to the
# KWin resourceClass / macOS app names above, so this needs its own table
# rather than reusing HOST_CLASSES. Only hosts with a class distinctive
# enough to trust a blind substring match against every top-level window on
# the desktop are listed: native Windows terminals (Windows Terminal's
# "cascadia_hosting_window_class", classic conhost's "consolewindowclass").
# VS Code's real Win32 class is "chrome_widgetwin_1" — shared with every
# other Electron/Chromium app (Discord, Slack, Teams, a plain Chrome/Edge
# window, even a second unrelated VS Code window) — so it's deliberately
# NOT listed here: guessing would risk click-to-focus raising the wrong
# window entirely. detect_host() has no env-var signal for native Windows
# terminals (cmd.exe/PowerShell/Windows Terminal all come back "unknown"),
# so that's the one host that gets the generic terminal-class fallback; any
# other/unmapped host gets no fallback classes and find_window_by_class
# safely no-ops instead of guessing.
WIN_CLASSES = {
    "unknown": ["cascadia_hosting_window_class", "consolewindowclass"],
}


def win_classes(host):
    """Win32 window-class substrings for a host's click-to-focus fallback, or
    [] if no class for this host is distinctive enough to trust a blind
    substring match (find_window_by_class then safely returns no match)."""
    return WIN_CLASSES.get(host, [])


def detect_host(env=None):
    """Best-effort identify the terminal/IDE hosting Claude Code, from env vars."""
    env = os.environ if env is None else env
    if env.get("TERM_PROGRAM") == "vscode" or env.get("VSCODE_PID"):
        return "vscode"
    if "jetbrains" in (env.get("TERMINAL_EMULATOR", "").lower()):
        return "jetbrains"
    if env.get("KONSOLE_VERSION"):
        return "konsole"
    tp = env.get("TERM_PROGRAM", "")
    if tp == "Apple_Terminal":
        return "apple_terminal"
    if tp == "iTerm.app":
        return "iterm"
    return "unknown"


def host_classes(host):
    """Window-class / app-name substrings for a host (empty list if unknown)."""
    return HOST_CLASSES.get(host, [])


def mac_app(host):
    """macOS application name to activate for a host, or None if unknown."""
    return MAC_APP.get(host)


def runtime_dir():
    """Base dir for per-session port files: $XDG_RUNTIME_DIR, else the OS temp dir.

    AF_UNIX sockets aren't available on stock Windows Python builds, so pets
    listen on a loopback TCP port instead and drop the assigned port in a
    small file here for hook/motion scripts to read.
    """
    return os.environ.get("XDG_RUNTIME_DIR") or tempfile.gettempdir()


def session_port_file(session_id):
    """Path to the file holding the loopback TCP port for a session's pet."""
    sid = session_id or "default"
    return os.path.join(runtime_dir(), "claudlet-{}.port".format(sid))


def read_port_file(path):
    """Port int from a .port file, or None if it's missing/empty/malformed."""
    try:
        with open(path) as f:
            return int(f.read().strip())
    except (OSError, ValueError):
        return None


def read_session_port(session_id):
    """Port of the pet attached to this session, or None if unknown/stale."""
    return read_port_file(session_port_file(session_id))


def write_session_port(session_id, port):
    """Publish the pet's port atomically. A plain open("w") truncates first and
    the bytes only land at close, so a hook/motion reader firing in that window
    sees an empty file (int("") -> dropped event). Write a sibling temp file and
    os.replace it in — atomic on both POSIX and Windows — so readers only ever
    see the old file or the whole new one, never a half-written one."""
    path = session_port_file(session_id)
    tmp = "{}.{}.tmp".format(path, os.getpid())
    with open(tmp, "w") as f:
        f.write(str(port))
    try:
        _replace_retrying(tmp, path)
    except OSError:
        # replace never happened -> the temp file would otherwise linger
        # forever (it doesn't match the claudlet-*.port glob, so nothing
        # else cleans it). Drop it before propagating.
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def _replace_retrying(src, dst, attempts=10, delay=0.02):
    """os.replace(src, dst) is atomic on POSIX even with a reader holding
    `dst` open, but on Windows a destination opened without FILE_SHARE_DELETE
    (the default for a plain `open()`) makes MoveFileExW raise PermissionError
    while that reader has it open. Every reader here (`read_port_file`'s
    `with open(path) as f: ...`) closes within microseconds, so a short retry
    loop clears the race instead of crashing the caller — this is the only
    caller of os.replace on the port file, so the loop belongs here rather
    than at each call site."""
    for i in range(attempts):
        try:
            os.replace(src, dst)
            return
        except OSError:
            if i == attempts - 1:
                raise
            time.sleep(delay)


def port_files():
    """Every published .port file — one per pet that has started, live or not."""
    import glob
    return glob.glob(os.path.join(runtime_dir(), "claudlet-*.port"))


def broadcast(line, timeout=0.3):
    """Send one JSON line to every live pet; return how many accepted it.

    The transport half of what `claudlet-motion` does, lifted here so the pet
    itself can talk to its siblings (dock offset changes) without importing a
    CLI module. Deliberately does NOT unlink stale files the way motion.send
    does: this runs inside a pet's event loop, where a refused connect is far
    more likely to be a sibling that is merely mid-startup than a dead one, and
    deleting a live pet's port file would sever it permanently.
    """
    n = 0
    payload = line.encode("utf-8")
    for path in port_files():
        port = read_port_file(path)
        if port is None:
            continue
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(timeout)
        try:
            s.connect((LOOPBACK, port))
            s.sendall(payload)
            n += 1
        except OSError:
            pass
        finally:
            s.close()
    return n


def pet_alive(session_id, timeout=0.3):
    """True only if THIS session's pet is really listening — proven by the
    liveness handshake, not a bare connect. Guards two failure modes a plain
    connect can't:
      * a stale .port file whose port the OS reassigned to an unrelated local
        process (that process accepts the connect but never answers PING), and
      * accumulating dead .port files (a refused connect means nothing is
        there, so the file is stale and gets removed here).
    Any non-refused error (busy pet, foreign listener that stays silent) counts
    as 'not our pet' but leaves the file alone."""
    path = session_port_file(session_id)
    port = read_port_file(path)
    if port is None:
        return False
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(timeout)
    start = time.monotonic()
    try:
        s.connect((LOOPBACK, port))
        s.sendall(PING)
        try:
            s.shutdown(socket.SHUT_WR)   # signal EOF so the pet answers now
        except OSError:
            pass
        # settimeout applies per blocking call, so connect+recv could each wait
        # the full `timeout` (~2x on a slow/foreign pet). Give recv only what's
        # left of the one budget so the whole check stays ~timeout.
        s.settimeout(max(0.05, timeout - (time.monotonic() - start)))
        reply = s.recv(256).decode("utf-8", "replace")
        return BANNER_MARK in reply
    except ConnectionRefusedError:
        try:
            os.unlink(path)              # nothing listening -> stale file
        except OSError:
            pass
        return False
    except OSError:
        return False
    finally:
        s.close()


# Claude Code names each session — the name shown on its tab — and records it in
# the session transcript as a JSON line {"type":"ai-title","aiTitle":...}. That
# name is what a person recognises a session BY, so it is what the pet's hover
# tooltip should say; the session id means nothing to anyone.
TRANSCRIPTS = os.path.expanduser("~/.claude/projects")
CODEX_SESSION_INDEX = os.path.expanduser("~/.codex/session_index.jsonl")
_TITLE_TAIL = 64 * 1024        # the title is re-emitted per prompt; the tail has it


def transcript_path(session_id, root=None):
    """This session's transcript file, or None.

    Found by GLOB rather than by building the directory name: Claude Code flattens
    the project path into that name by replacing separators with "-", which is
    not reversible and not worth re-deriving. Session ids are unique, so the
    file name alone finds it."""
    import glob
    if not session_id:
        return None
    root = TRANSCRIPTS if root is None else root
    hits = glob.glob(os.path.join(root, "*", "%s.jsonl" % session_id))
    return hits[0] if hits else None


def session_title(session_id, root=None, tail=_TITLE_TAIL):
    """The name Claude Code gave this session, or "" if it hasn't named it yet.

    Only the tail of the transcript is read: these files reach megabytes, the
    pet re-reads on hover, and the title is re-emitted on every prompt so the
    last one is always near the end. Any read problem -> "" (the caller falls
    back to the project name); never raises."""
    import json
    path = transcript_path(session_id, root)
    if not path:
        return ""
    try:
        with open(path, "rb") as f:
            f.seek(0, os.SEEK_END)
            f.seek(max(0, f.tell() - tail))
            chunk = f.read()
    except OSError:
        return ""
    title = ""
    for line in chunk.split(b"\n"):
        if b'"ai-title"' not in line:
            continue
        try:
            d = json.loads(line.decode("utf-8", "replace"))
        except ValueError:
            continue                      # a line cut in half by the tail seek
        if d.get("type") == "ai-title" and d.get("aiTitle"):
            title = str(d["aiTitle"]).strip()
        continue
    return title


def codex_session_title(session_id, path=None):
    """The latest title Codex recorded for this session, or ""."""
    import json
    path = CODEX_SESSION_INDEX if path is None else path
    if not session_id:
        return ""
    try:
        with open(path, encoding="utf-8") as f:
            lines = f.readlines()
    except OSError:
        return ""
    for line in reversed(lines):
        try:
            d = json.loads(line)
        except ValueError:
            continue
        if d.get("id") == session_id and d.get("thread_name"):
            return str(d["thread_name"]).strip()
    return ""
