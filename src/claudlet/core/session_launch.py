"""Start a fresh agent session for a pet, and pair the two.

The pet has always been a passenger: something else started a Claude session and
the pet attached to it. This turns it around -- launching a pet can start the
session it belongs to, one new session per new pet.

The pairing is not guesswork. `claude --session-id <uuid>` takes the id we
choose, so we mint one, bind the pet to it, and hand the same id to the agent;
there is no window where we have to hunt for "the newest transcript" and hope.

Everything that decides WHAT to run is here and pure -- the command line, the
shell quoting, the session id. Actually opening a terminal is the platform's
job (`platform/termlaunch.py`), because that is the part that cannot be tested
off a desktop.
"""
import os
import uuid


def new_session_id():
    """A fresh session id. `claude --session-id` requires a valid UUID."""
    return str(uuid.uuid4())


def shell_quote(arg):
    """POSIX single-quote one argument. Pure, so the quoting is testable.

    The command goes through AppleScript into a shell, so a directory with a
    quote or a space in it would otherwise split the command apart.
    """
    return "'" + str(arg).replace("'", "'\\''") + "'"


def build_command(session_id, cwd=None, agent_bin="claude", extra=(),
                  session_flag="--session-id", config_dir=None):
    """The shell line that starts the agent in `cwd` with our session id.

    `cd` is part of the line rather than a terminal setting: a new Terminal
    window opens in the user's home, and a session started in the wrong
    directory is a session that cannot see the project they are working on.

    `session_flag=None` means this agent cannot be told which id to use; the
    command still starts it, and the caller has to fall back to pairing the pet
    afterwards rather than up front.

    `config_dir` sets CLAUDE_CONFIG_DIR for the started session, so a pet can
    open sessions against a specific agent profile instead of whichever one the
    pet's own shell happened to have.
    """
    parts = []
    if cwd:
        parts.append("cd %s &&" % shell_quote(cwd))
    if config_dir:
        # Prefixed rather than exported so it applies to this command only --
        # the new terminal is the user's shell and we should not leave a
        # setting behind in it.
        parts.append("CLAUDE_CONFIG_DIR=%s" % shell_quote(config_dir))
    parts.append(shell_quote(agent_bin))
    if session_flag and session_id:
        parts.append("%s %s" % (session_flag, shell_quote(session_id)))
    parts.extend(str(x) for x in extra)
    return " ".join(parts)


def resolve_cwd(cwd=None):
    """Where the new session should start. Falls back to the user's home."""
    if cwd and os.path.isdir(cwd):
        return cwd
    here = os.getcwd()
    return here if os.path.isdir(here) else os.path.expanduser("~")
