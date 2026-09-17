"""claudlet's console entry points.

Only one thing lives here: the stream fix every one of them needs before it
prints anything.
"""
import sys


def utf8_streams(*streams):
    """Make these streams speak UTF-8 whatever the locale says.

    Windows only writes a console directly as UTF-16; the moment a stream is
    REDIRECTED it falls back to the locale codepage (cp949 on a Korean
    machine), so every Korean line these commands print comes out mojibake to
    whoever is reading the pipe. That reader is usually Claude: the /claudlet
    skill's own instructions are to run `claudlet-config` and read the path,
    the current values and the `ignored:` list back out of its output.

    Passing the console's own streams is harmless -- they are UTF-8 already --
    so callers need not ask which they got. Never raises: a closed or detached
    stream (a hook runs with no console at all) must not take a command down
    over an encoding.
    """
    for s in streams:
        try:
            if hasattr(s, "reconfigure"):
                s.reconfigure(encoding="utf-8", errors="replace")
        except (OSError, ValueError):
            pass


def utf8_output():
    """The common case: this command only PRINTS non-ASCII."""
    utf8_streams(sys.stdout, sys.stderr)
