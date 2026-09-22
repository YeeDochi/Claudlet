"""The coding agents a pet can be attached to.

One agent = one dict here. Everything else (the hook installer, the hook
bridge, the pet's state mapping, the settings page, which creature is worn)
reads this registry, so adding a third agent is one entry -- not a change
spread over five files.

Pure data plus three lookups: no IO beyond asking whether a marker directory
exists, no Qt, no imports from the rest of claudlet. Tested as data.
"""
import os

# Agent hook configs all share Claude Code's shape:
#   {"hooks": {"<Event>": [{"hooks": [{"type": "command", "command": "..."}]}]}}
# Only the file differs, which is why one installer serves them all.
AGENTS = {
    "claude": {
        "label": "Claude Code",
        "marker": ".claude",                 # ~/.claude -> Claude Code is installed
        "settings": os.path.join(".claude", "settings.json"),
        "skills": os.path.join(".claude", "skills"),
        "proc": "claude",                    # the reaper's ancestor needle
        # Flag that makes the agent adopt an id WE choose, so a pet and the
        # session it starts are paired exactly instead of racing to spot the
        # newest transcript. None = this agent can't be started that way.
        "session_id_flag": "--session-id",
        "events": ["PreToolUse", "PostToolUse", "UserPromptSubmit",
                   "Notification", "Stop", "StopFailure", "SubagentStop",
                   "SessionStart", "SessionEnd"],
        "tool_events": ["PreToolUse", "PostToolUse"],
        "avatar": "claudlet",
        "tools": {},          # state_engine's built-in TOOL_STATES already fit
        "raw_events": {},
    },
    "codex": {
        "label": "Codex",
        "marker": ".codex",
        "settings": os.path.join(".codex", "hooks.json"),
        "skills": os.path.join(".codex", "skills"),
        "proc": "codex",
        # Not set: codex was not installed on the machine this was written on,
        # so whether it accepts a caller-chosen session id is unverified. Left
        # None rather than guessed -- a wrong flag produces a command that fails
        # in a terminal window the user then has to close.
        "session_id_flag": None,
        # Measured from the codex 0.147.0 native binary's strings, corroborated
        # by Codex's own plugin hooks.json (which registers SessionEnd). No
        # Notification, no StopFailure. Adds PermissionRequest (its "may I?"
        # prompt). SubagentStop is kept (state_engine.handle branches on it),
        # but SubagentStart and PreCompact are deliberately left out: neither
        # reaches any branch in state_engine.handle, so registering them would
        # only spawn a Python process per event for nothing.
        "events": ["SessionStart", "SessionEnd", "UserPromptSubmit",
                   "PreToolUse", "PostToolUse", "PermissionRequest", "Stop",
                   "SubagentStop"],
        "tool_events": ["PreToolUse", "PostToolUse"],
        "avatar": "codex",
        # The only tool_name values evidenced on this version are "exec" (the
        # shell tool -- appears in session rollouts as a custom_tool_call
        # named "exec") and "apply_patch". Both already fall back to
        # work_computer via StateEngine's default, so no entries are needed
        # here yet. Add one only when a name shows up that deserves a
        # different state (e.g. a web tool).
        "tools": {},
        "raw_events": {"PermissionRequest": "attention"},
    },
}

DEFAULT = "claude"


def names():
    return list(AGENTS)


def get(name=None):
    """The agent's entry; an unknown or missing name resolves to the default,
    so a stale config or an old hook command can never crash a hook."""
    return AGENTS.get(name) or AGENTS[DEFAULT]


def _home(home=None):
    return home if home is not None else os.path.expanduser("~")


def settings_path(name, home=None):
    return os.path.join(_home(home), get(name)["settings"])


def skills_path(name, home=None):
    return os.path.join(_home(home), get(name)["skills"])


def detected(home=None):
    """Agents that look installed on this machine, in registry order. This is
    what the installer targets by default and what the settings page lists."""
    h = _home(home)
    return [n for n, a in AGENTS.items()
            if os.path.isdir(os.path.join(h, a["marker"]))]
