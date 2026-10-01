"""크리처 머리 — 말 걸기를 본 세션 대신 받는 1회짜리 에이전트.

말 걸기는 원래 사용자 말을 본 세션 프롬프트에 그대로 넣었다. 그러면 잡담 한
마디가 일하던 세션의 턴 하나가 되고, 말투 지시가 그 맥락에 쌓인다. 크리처의
머리가 본 세션 안에 있었던 것이 원인이라, 머리를 밖으로 뺐다: 말할 때마다
`claude -p` / `codex exec` 를 한 번 띄워 크리처가 직접 답하고, 본 세션이 할
일일 때만 RELAY 로 넘긴다.

이 모듈은 순수하다 — 맥락 자르기, 프롬프트, 응답 파싱, 띄울 argv. 프로세스를
띄우고 기다리는 일은 펫(QProcess)이 한다.

크리처 에이전트에서는 훅이 하나도 돌면 안 된다. 그대로 띄웠더니 사용자의
SessionStart 훅들이 돌다가 멈췄고(실측), claudlet 훅이 돌면 펫이 하나 더 뜬다.
그래서 플래그로 끄고, 환경변수(CREATURE_ENV)로 한 번 더 막는다.
"""
import re

from claudlet.core import inspect

CREATURE_ENV = "CLAUDLET_CREATURE"   # claudlet-hook 이 이걸 보면 아무것도 안 한다
TIMEOUT_S = 60
HISTORY_PAIRS = 5

_SYSTEM = """\
You are {name}, a tiny pixel creature living on a developer's desktop while their \
coding agent works in another session. You are NOT that agent. You cannot run \
tools, read files or change anything — you only talk.
{voice}
You get a glimpse of what the agent session has been doing lately, and your \
recent chat with the user. Use it to answer small talk and questions yourself.

When the user asks for real work — editing, running, fixing, investigating code — \
hand it to the agent: write the request on a RELAY line, clear and self-contained, \
as the user would ask the agent. Otherwise never write a RELAY line.

Write everything — SAY and RELAY — in the language the user wrote in. Output exactly:
SAY: <one short line, under 60 characters, in your voice>
RELAY: <request for the agent>   (only when handing work over)"""

_NO_RELAY = {"", "-", "none", "n/a", "없음"}
_LABEL = re.compile(r"^[\s*_`>#-]*(say|relay)[\s*_`]*:[\s*_`]*(.*)$", re.I)


def _entry_line(e):
    kind = e.get("kind")
    if kind == "tool":
        return "[tool] {} {}".format(e.get("name") or "?", e.get("detail") or "").strip()
    if kind == "todo":
        items = "; ".join("{} ({})".format(i.get("text", ""), i.get("status", ""))
                          for i in e.get("items") or [])
        return "[todo] " + items
    return "[{}] {}".format(kind or "?", e.get("text") or "")


def recent_context(entries, budget=6000, per=400):
    """세션 타임라인(`transcript.load`)의 최근 몫을 글자 예산 안에서.

    최신부터 거슬러 담고, 항목마다 `per` 자로 자르고, 비밀값을 가린다.
    돌려줄 때는 오래된 것부터 — 읽히는 순서가 일어난 순서여야 한다."""
    picked, used = [], 0
    for e in reversed(entries or []):
        line = " ".join(inspect.redact(_entry_line(e)).split())[:per]
        if used + len(line) > budget:
            break
        picked.append(line)
        used += len(line) + 1
    return "\n".join(reversed(picked))


_ALONE = """
No agent session is attached to you right now (you are a standalone pet), so you \
cannot hand work over. If the user asks for real work, say kindly that there is no \
agent session to pass it to, and never write a RELAY line."""


def build_prompt(persona, name, history, recent, text, pointed="", alone=False):
    """(시스템 프롬프트, 사용자 메시지). `history` 는 history.load 순서(최신 먼저).
    `alone`: 세션 없이 뜬 펫 — 넘길 곳이 없다."""
    voice = "Your voice: {}".format(persona) if persona else ""
    system = _SYSTEM.format(name=name or "the creature", voice=voice)
    if alone:
        system += _ALONE
    pairs = [r for r in (history or []) if r.get("answer")][:HISTORY_PAIRS]
    parts = []
    if recent:
        parts.append("## What the agent session has been doing\n" + recent)
    if pairs:
        chat = "\n".join("user: {}\nyou: {}".format(
            inspect.redact(r.get("question") or ""), inspect.redact(r["answer"]))
            for r in reversed(pairs))
        parts.append("## Your recent chat with the user\n" + chat)
    if pointed:
        parts.append("## What the user is pointing at on screen\n"
                     + inspect.redact(pointed))
    parts.append("## The user says\n" + text)
    # 지시가 메시지 앞머리에 있으면 언어 지시가 묻힌다 — RELAY 가 영어로 넘어갔다(실측).
    parts.append("(Write SAY and RELAY in the same language as the line above.)")
    return system, "\n\n".join(parts)


def parse_reply(out):
    """`{"say", "relay"}`, 또는 빈 출력이면 None. 형식을 안 지켰으면 첫 줄이 SAY."""
    lines = [l.strip() for l in (out or "").splitlines() if l.strip()]
    if not lines:
        return None
    say, relay = None, None
    for line in lines:
        m = _LABEL.match(line)
        if not m:
            continue
        label, value = m.group(1).lower(), m.group(2).strip()
        if label == "say" and say is None:
            say = value
        elif label == "relay" and relay is None and value.lower() not in _NO_RELAY:
            relay = value
    if say is None:
        first = lines[0]
        say = "" if _LABEL.match(first) else first
    if not say and not relay:
        return None            # 할 말도 넘길 일도 없다 — 실패로 보고 본 세션에 넘긴다
    return {"say": say or "…", "relay": relay}


# 띄울 때 인자로는 고정 문자열만 넘긴다. 말투는 크리처 패키지(남이 만든 것일 수도
# 있다)가 정하는데, 윈도우에서 `claude` 는 .cmd 심이라 cmd.exe 가 인자를 다시
# 해석한다 — 줄바꿈에서 잘리고 & | ^ % 가 명령이 된다. 그래서 진짜 시스템
# 프롬프트는 사용자 메시지와 함께 stdin 으로 간다.
_ARGV_SYSTEM = "You are a desktop pet creature. Follow the instructions at the top of the message."

# codex 는 도구를 하나씩 꺼야 한다. read-only 샌드박스도 셸로 아무 파일이나 읽을 수
# 있어서, 창에서 읽은 글자에 숨은 지시가 비밀을 읽어 RELAY 로 흘릴 수 있었다.
# 사용자 설정(MCP 서버들)도 싣지 않는다. 실측: 이 조합에서 셸을 시키면 못 한다고 답한다.
_CODEX_OFF = ("hooks", "shell_tool", "unified_exec", "apps", "browser_use",
              "browser_use_external", "computer_use")


def command(agent, exe, outfile=None):
    """크리처 에이전트를 띄울 argv. 프롬프트는 전부 stdin(`stdin_for`)으로."""
    if agent == "codex":
        argv = [exe, "exec", "--ephemeral", "--skip-git-repo-check",
                "--ignore-user-config", "-s", "read-only"]
        for feature in _CODEX_OFF:
            argv += ["-c", "features.%s=false" % feature]
        return argv + ["-c", "model_reasoning_effort=low", "-o", outfile or "", "-"]
    return [exe, "-p", "--model", "haiku", "--tools", "", "--strict-mcp-config",
            "--setting-sources", "", "--settings", '{"disableAllHooks":true}',
            "--no-session-persistence", "--system-prompt", _ARGV_SYSTEM]


def stdin_for(system, user):
    """시스템 프롬프트를 메시지 앞머리에 싣는다(위 _ARGV_SYSTEM 참고)."""
    return "# Instructions\n" + system + "\n\n" + user
