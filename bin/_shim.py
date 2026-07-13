#!/usr/bin/env python3
"""Shared launcher for the source-checkout bin/ shims.

Each bin/<cmd> is a 2-line wrapper calling run("module:attr"). Keeps the
path-insert + import + call in one place instead of duplicated 6-line files.
Installed users get pyproject [project.scripts]; these bin/ files are for
source checkouts (and hooks that reference them by full path)."""
import os
import sys


def run(target, swallow=False):
    """Import "module.path:callable" (with ../src on sys.path) and call it.
    swallow=True (hooks): never raise, always exit 0 so Claude is never blocked."""
    sys.path.insert(0, os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "..", "src"))
    try:
        mod_name, _, attr = target.partition(":")
        mod = __import__(mod_name, fromlist=[attr])
        getattr(mod, attr)()
    except Exception:
        if not swallow:
            raise
    if swallow:
        sys.exit(0)
