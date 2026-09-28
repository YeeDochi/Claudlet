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
        # 이 이벤트들 옆에 asyncRewake waiter 를 하나 더 건다 — 놀고 있는
        # 세션을 펫이 깨울 수 있는 통로(프롬프트에 쳐 넣을 수 없는 호스트용).
        # SessionStart 가 있어야 첫 프롬프트 전에도 깨운다(Stop 만 걸었더니
        # 막 띄운 IDE 세션에 건 말이 첫 프롬프트까지 묵었다). 빈 목록 = 이
        # 에이전트에는 그런 훅이 없다.
        "rewake": ["SessionStart", "Stop"],
        # 포인터 캡처(runtime_dir 의 PNG)는 작업 폴더 밖이라 Read 가 권한을
        # 묻는다 — 설치기가 그 파일만 읽게 허용 규칙을 넣는다. 코덱스는
        # view_image 가 샌드박스와 상관없이 읽어서 필요 없다(둘 다 실측).
        "allow_shots": True,
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
        # 코덱스 훅에는 asyncRewake 가 없다. 코덱스 앱은 앱이 여는 도구
        # 파이프로 대신 보낸다(platform/codexapp.py).
        "rewake": [],
        # 전역 지침 파일. 앱이 넣은 펫의 말은 도구 출력(위임)이라 모델이 그
        # 안의 지시를 안 따른다 — 규칙은 모델이 믿는 이 자리에 둔다.
        "instructions": os.path.join(".codex", "AGENTS.md"),
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
