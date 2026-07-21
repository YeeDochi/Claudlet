#!/usr/bin/env python3
"""Print the auto English changelog for a commit range — the seed/fallback for
a release's notes. Thin git wrapper around `claudlet.relnotes` (all logic +
tests live there).

    scripts/release_notes.py <prev_ref> <cur_ref>   # e.g. v0.3.0 HEAD
    scripts/release_notes.py <prev_ref>             # <prev>..HEAD

Emits Markdown to stdout. release.sh uses it to seed the tag annotation when no
hand-written bilingual notes file is supplied.
"""
import os
import subprocess
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))
from claudlet.core import relnotes


def _subjects(prev, cur):
    rng = f"{prev}..{cur}" if prev else cur
    out = subprocess.run(["git", "log", "--no-merges", "--pretty=%s", rng],
                         capture_output=True, text=True, check=True)
    return [ln for ln in out.stdout.splitlines() if ln.strip()]


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if not argv:
        print("usage: release_notes.py <prev_ref> [cur_ref]", file=sys.stderr)
        return 2
    prev = argv[0]
    cur = argv[1] if len(argv) > 1 else "HEAD"
    print(relnotes.render_notes(_subjects(prev, cur)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
