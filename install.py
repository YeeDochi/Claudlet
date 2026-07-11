#!/usr/bin/env python3
"""claudlet quick installer — Linux, macOS, Windows.

  Linux / macOS:
    curl -fsSL https://raw.githubusercontent.com/YeeDochi/Claudlet/master/install.py | python3 -
  Windows (PowerShell):
    irm https://raw.githubusercontent.com/YeeDochi/Claudlet/master/install.py | python -

Clones (or updates) the repo, ensures dependencies (PyQt6, plus
pyobjc-framework-Quartz on macOS — the latter via bin/claudlet-install), and
registers the Claude Code hooks + skill. Re-run anytime to update.
Override the location with the CLAUDLET_DIR environment variable.
"""
import os
import shutil
import subprocess
import sys

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")

REPO = "https://github.com/YeeDochi/Claudlet.git"
DEST = os.environ.get("CLAUDLET_DIR") or os.path.join(os.path.expanduser("~"),
                                                        "claudlet")


def main():
    if not shutil.which("git"):
        sys.exit("error: git is required.")

    # 1) get the source (clone, or update an existing checkout)
    if os.path.isdir(os.path.join(DEST, ".git")):
        print("==> updating", DEST)
        subprocess.call(["git", "-C", DEST, "pull", "--ff-only"])
    else:
        print("==> cloning into", DEST)
        subprocess.check_call(["git", "clone", "--depth", "1", REPO, DEST])

    # 2) deps (PyQt6 + macOS Quartz), hooks, skill, PATH link, pretty summary —
    #    all handled by claudlet-install with the same interpreter (cross-OS).
    subprocess.check_call([sys.executable,
                           os.path.join(DEST, "bin", "claudlet-install")])

    print("\nsource at", DEST)


if __name__ == "__main__":
    main()
