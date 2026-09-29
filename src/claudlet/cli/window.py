#!/usr/bin/env python3
"""claudlet-window — find a window and pull it out from behind the others.

Usage:
  claudlet-window list          every window, topmost first, as JSON
                                ({"id", "app", "title", "state": shown|min|desk})
  claudlet-window raise <id>    bring that window to the front (restoring it,
                                and on KDE fetching it from another desktop);
                                the pet then brings it back
  claudlet-window raise <id> --wait
                                ...and wait until it is really up front:
                                exit 0 when it is, 3 (with its last state on
                                stderr) when it never came up
  claudlet-window raise <id> --pull [--wait]
                                ...and haul it over even when it is maximized
                                (un-maximizing it; Windows) — for "끌고 와",
                                where plain raise leaves a maximized window
                                where it is and the pet goes to it
  claudlet-window chat         open (or bring back) the pet's own chat window,
                                which `list` never shows

The pet does the work — it already holds the window feed and owns the
platform raise — so this only talks to it: this session's pet
($CLAUDE_CODE_SESSION_ID / $CODEX_SESSION_ID) when there is one, else any
running pet.
"""
import json
import socket
import sys
import time

from claudlet.cli import utf8_output
from claudlet.core import agents, hostinfo


def _ports():
    current = agents.session_agent()
    sid = agents.session_id(current) if current else None
    own = hostinfo.read_session_port(sid) if sid else None
    rest = [hostinfo.read_port_file(p) for p in hostinfo.port_files()]
    return [p for p in [own] + rest if p is not None]


def _talk(line, want_reply, timeout=1.0):
    """Send `line` to the first pet that takes it; its reply (or "" when none
    is wanted), or None when no pet answered."""
    for port in _ports():
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(timeout)
        try:
            s.connect((hostinfo.LOOPBACK, port))
            s.sendall(line.encode("utf-8"))
            if not want_reply:
                return ""
            s.shutdown(socket.SHUT_WR)       # EOF -> the pet answers now
            buf = b""
            while True:
                chunk = s.recv(65536)
                if not chunk:
                    break
                buf += chunk
            if buf:
                return buf.decode("utf-8", "replace")
        except OSError:
            continue
        finally:
            s.close()
    return None


WAIT_SECS = 20.0    # the pet dashes over and tugs it back — a long drag takes ~10s
POLL_SECS = 0.4


def raised(rows, wid):
    """Is `wid` shown and topmost in a `windows` reply? A window it owns on top
    counts: an owned window always stacks above its owner, so the app is up
    front (KakaoTalk restores to exactly that). Pure."""
    if not rows:
        return False
    top = rows[0]
    if top.get("id") == wid:
        return top.get("state") == "shown"
    if top.get("owner") != wid:
        return False
    row = next((r for r in rows if r.get("id") == wid), None)
    return row is not None and row.get("state") == "shown"


def delivered(reply, wid):
    """Is `wid` up front AND done being brought over? An open window is up
    front the moment the pet starts dragging it, so the pet's own fetch has
    to have reached its window (ride) or ended too. A pet too old to say
    counts as done. Pure."""
    if not reply or not raised(reply.get("windows"), wid):
        return False
    return reply.get("fetching") != wid or reply.get("fetch_phase") == "ride"


def _windows():
    """The pet's whole `windows` reply (rows + what it is fetching), or None."""
    reply = _talk(json.dumps({"cmd": "windows"}) + "\n", True)
    if reply is None:
        return None
    try:
        return json.loads(reply.splitlines()[0])
    except (ValueError, IndexError):
        return None


def _wait_raised(wid, clock=time.monotonic, sleep=time.sleep):
    """0 once `wid` is up front and the pet has finished bringing it, 3 when
    WAIT_SECS pass without it."""
    end = clock() + WAIT_SECS
    reply = None
    while clock() < end:
        sleep(POLL_SECS)                  # first: let the pet take the raise in
        reply = _windows() or reply
        if delivered(reply, wid):
            return 0
    rows = (reply or {}).get("windows")
    row = next((r for r in rows or [] if r.get("id") == wid), None)
    where = "gone" if row is None else row.get("state")
    if row is not None and where == "shown":
        where = "shown but not in front"
    print("the window did not come up (%s)" % where, file=sys.stderr)
    return 3


def main(argv):
    if argv[:1] == ["list"]:
        reply = _talk(json.dumps({"cmd": "windows"}) + "\n", True)
        if reply is None:
            print("no running claudlet pet", file=sys.stderr)
            return 1
        try:
            wins = json.loads(reply.splitlines()[0])["windows"]
        except (ValueError, KeyError, IndexError, TypeError):
            print("the pet gave no window list (older version?)", file=sys.stderr)
            return 1
        print(json.dumps(wins, ensure_ascii=False, indent=1))
        return 0
    flags = set(argv[2:])
    if (argv[:1] == ["raise"] and len(argv) >= 2 and flags <= {"--wait", "--pull"}
            and len(flags) == len(argv) - 2):
        msg = {"cmd": "raise", "id": argv[1]}
        if "--pull" in flags:
            msg["pull"] = True
        if _talk(json.dumps(msg) + "\n", False) is None:
            print("no running claudlet pet", file=sys.stderr)
            return 1
        return _wait_raised(argv[1]) if "--wait" in flags else 0
    if argv == ["chat"]:
        if _talk(json.dumps({"cmd": "chat"}) + "\n", False) is None:
            print("no running claudlet pet", file=sys.stderr)
            return 1
        return 0
    print(__doc__.strip(), file=sys.stderr)
    return 2


def _cli():
    utf8_output()
    sys.exit(main(sys.argv[1:]))


if __name__ == "__main__":
    _cli()
