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
        "proc": "claude",                    # the reaper's ancestor needle
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
        "proc": "codex",
        # Codex fires no SessionEnd / Notification / SubagentStop, and adds
        # PermissionRequest (its "may I?" prompt).
        "events": ["SessionStart", "UserPromptSubmit", "PreToolUse",
                   "PostToolUse", "PermissionRequest", "Stop"],
        "tool_events": ["PreToolUse", "PostToolUse"],
        "avatar": "codex",
        # Codex's own tool names -> display states. Filled from REAL captured
        # payloads in the last task; anything unmapped falls back to
        # work_computer inside StateEngine.
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


def detected(home=None):
    """Agents that look installed on this machine, in registry order. This is
    what the installer targets by default and what the settings page lists."""
    h = _home(home)
    return [n for n, a in AGENTS.items()
            if os.path.isdir(os.path.join(h, a["marker"]))]
