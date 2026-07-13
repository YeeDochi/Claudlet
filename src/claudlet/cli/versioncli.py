#!/usr/bin/env python3
"""claudlet-version — show the installed version vs the latest PyPI release.

Read-only: queries PyPI over HTTPS with a short timeout and degrades gracefully
offline. The /claudlet skill runs this to show current-vs-latest before handing
the user an update command.
"""
import json
import sys
import urllib.request

from claudlet import __version__

PYPI_JSON = "https://pypi.org/pypi/claudlet/json"


def _parse(v):
    """A version string -> tuple of ints for comparison ("0.10.0" -> (0,10,0)).
    Non-numeric parts become 0 so a malformed value never raises."""
    out = []
    for part in str(v).split("."):
        num = ""
        for ch in part:
            if ch.isdigit():
                num += ch
            else:
                break
        out.append(int(num) if num else 0)
    return tuple(out)


def compare(installed, latest):
    """State of `installed` relative to `latest`: 'unknown' (latest is None,
    e.g. offline), 'up-to-date', 'update-available', or 'ahead'. Pure."""
    if not latest:
        return "unknown"
    a, b = _parse(installed), _parse(latest)
    n = max(len(a), len(b))
    a += (0,) * (n - len(a))
    b += (0,) * (n - len(b))
    if a == b:
        return "up-to-date"
    return "update-available" if a < b else "ahead"


def latest_pypi_version(timeout=2.0):
    """Latest claudlet version on PyPI, or None if it can't be fetched."""
    try:
        with urllib.request.urlopen(PYPI_JSON, timeout=timeout) as r:
            return json.load(r)["info"]["version"]
    except Exception:
        return None


_STATUS_MSG = {
    "up-to-date": "up to date",
    "update-available": "update available",
    "ahead": "installed build is ahead of the latest release (dev)",
    "unknown": "could not reach PyPI (offline?)",
}


def render(installed, latest):
    """Human-readable current-vs-latest summary."""
    state = compare(installed, latest)
    return ("claudlet %s (installed)\nlatest release: %s   -> %s"
            % (installed, latest or "unknown", _STATUS_MSG[state]))


def main(argv=None):
    print(render(__version__, latest_pypi_version()))
    return 0


def _cli():
    try:
        sys.exit(main(sys.argv[1:]))
    except Exception:
        sys.exit(0)


if __name__ == "__main__":
    _cli()
