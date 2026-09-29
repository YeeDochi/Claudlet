#!/usr/bin/env python3
"""claudlet-window — find a window and pull it out from behind the others.

Usage:
  claudlet-window list          every window, topmost first, as JSON
                                ({"id", "app", "title", "state": shown|min|desk})
  claudlet-window raise <id>    bring that window to the front (restoring it,
                                and on KDE fetching it from another desktop);
                                the pet then heads into it

The pet does the work — it already holds the window feed and owns the
platform raise — so this only talks to it: this session's pet
($CLAUDE_CODE_SESSION_ID) when there is one, else any running pet.
"""
import json
import os
import socket
import sys

from claudlet.cli import utf8_output
from claudlet.core import hostinfo


def _ports():
    sid = os.environ.get("CLAUDE_CODE_SESSION_ID")
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


def main(argv):
    if argv[:1] == ["list"]:
        reply = _talk(json.dumps({"cmd": "windows"}) + "\n", True)
        if reply is None:
            print("no running claudlet pet", file=sys.stderr)
            return 1
        try:
            wins = json.loads(reply.splitlines()[0])["windows"]
        except (ValueError, KeyError, IndexError):
            print("the pet gave no window list (older version?)", file=sys.stderr)
            return 1
        print(json.dumps(wins, ensure_ascii=False, indent=1))
        return 0
    if argv[:1] == ["raise"] and len(argv) == 2:
        if _talk(json.dumps({"cmd": "raise", "id": argv[1]}) + "\n", False) is None:
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
