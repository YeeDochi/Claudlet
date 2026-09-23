"""Inspect the app under a point the user picked, and build a redacted,
reviewable context for a question about it.

Two layers, deliberately separated:

  * METADATA -- window title/app/pid/bounds. Comes from `platform.geom`, which
    every OS backend already fills, and needs no extra permission.
  * TEXT -- the accessibility tree of that window, which is the only way to
    read what is actually on screen without capturing pixels. Optional: the
    backend may be missing (see `platform/axtree.py`) and the user may not have
    granted the permission, in which case we degrade to metadata rather than
    failing the question.

Nothing here sends anything. `build_context()` returns what WOULD be sent so a
caller can show it to the user first; that ordering is the whole point -- the
user is agreeing to a specific payload, not to a capability.

Pure and Qt-free: the AX reader is injected, so the redaction and shaping logic
is testable without a display or an accessibility grant.
"""
import re

# Lines longer than this are almost never a label the user meant to ask about;
# they're log spew or a serialized blob. Truncating keeps the payload readable
# in the preview, which is what makes review feasible at all.
MAX_LINE = 200
MAX_LINES = 120
MAX_CHARS = 8000

# Patterns whose VALUE is dropped before the payload is ever shown. This is not
# a security boundary -- the user reviews the payload and the real boundary is
# that review. It exists so the common accidents (a token sitting in a terminal
# scrollback, a password field read back as text) don't reach the preview and
# get waved through out of habit.
_REDACTIONS = (
    (re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"), "<email>"),
    (re.compile(r"\b(?:sk|pk|ghp|gho|ghs|glpat|xox[abps])[-_][A-Za-z0-9_-]{8,}"), "<token>"),
    (re.compile(r"\b[A-Fa-f0-9]{32,}\b"), "<hex>"),
    (re.compile(r"(?i)\b(pass(?:word|wd)?|secret|token|api[-_ ]?key|bearer)\b"
                r"\s*[:=]\s*\S+"), r"\1: <redacted>"),
    (re.compile(r"\b\d{1,3}(?:\.\d{1,3}){3}\b"), "<ip>"),
    (re.compile(r"\b(?:\d[ -]?){13,19}\b"), "<card>"),
)


def redact(text):
    """Strip the obvious secrets out of one string."""
    for pat, repl in _REDACTIONS:
        text = pat.sub(repl, text)
    return text


def _clean_lines(lines):
    """Normalize, redact and bound a list of extracted strings."""
    out, seen = [], set()
    for raw in lines:
        if not raw:
            continue
        line = " ".join(str(raw).split())
        if not line:
            continue
        if len(line) > MAX_LINE:
            line = line[:MAX_LINE] + "…"
        line = redact(line)
        # The AX tree repeats a label once per nesting level it appears at;
        # deduping is what turns it from a dump into something readable.
        if line in seen:
            continue
        seen.add(line)
        out.append(line)
        if len(out) >= MAX_LINES:
            out.append("… (truncated)")
            break
    return out


def describe_window(win):
    """One-line human description of a geom.Win."""
    if win is None:
        return "no window at that point"
    name = win.title or win.caption or "(untitled)"
    return "%s — %dx%d at (%d,%d), pid %d" % (
        name, win.w, win.h, win.x, win.y, win.pid)


# 창 제목이 "무엇을 열어놨는지" 를 말해주는 앱들. 에디터 본문은 접근성 트리에
# 나오지 않는다 — IntelliJ 를 깊이 30까지 1243 노드 훑어도 텍스트 인터페이스가
# 하나도 없었다(실측). 그렇다고 DLL 을 붙이고 픽셀을 긁는 것은 과하다: 에이전트는
# 파일을 디스크에서 직접 읽으면 되고, 어떤 파일인지는 제목에 이미 적혀 있다.
IDE_CLASSES = ("jetbrains", "idea", "pycharm", "webstorm", "goland", "clion",
               "rubymine", "phpstorm", "android-studio", "code", "vscodium",
               "sublime_text")
# 제목에 적히는 앱 이름들 — 이것은 파일이 아니다.
_APP_NAMES = ("IntelliJ IDEA", "PyCharm", "WebStorm", "GoLand", "CLion",
              "RubyMine", "PhpStorm", "Android Studio", "Visual Studio Code",
              "VSCodium", "Sublime Text")
_SEPS = ("\u2013", "\u2014", " - ")        # en dash, em dash, 하이픈


def _is_ide(win):
    cls = (getattr(win, "title", "") or "").lower()
    return any(k in cls for k in IDE_CLASSES)


def open_file(win):
    """이 IDE 창이 열어놓은 {project, file}, 알 수 없으면 None. 순수.

    제목 형식이 두 갈래다:
      JetBrains  "<프로젝트> – <파일>"
      VS Code    "<파일> - <폴더> - Visual Studio Code"
    끝이 앱 이름이면 열린 파일이 아니라 그냥 IDE 가 떠 있는 것이다."""
    if win is None or not _is_ide(win):
        return None
    caption = (getattr(win, "caption", "") or "").strip()
    if not caption:
        return None
    parts = [p.strip() for p in re.split(r"\s+[\u2013\u2014]\s+|\s+-\s+", caption)
             if p.strip()]
    app = next((a for a in _APP_NAMES if parts and parts[-1] == a), None)
    if app:
        parts = parts[:-1]
        if len(parts) < 2:
            return None                # "<프로젝트> - IntelliJ IDEA": 파일 없음
        return {"file": parts[0], "project": parts[1]}
    if len(parts) < 2:
        return None
    return {"project": parts[0], "file": parts[-1]}


def build_context(win, question, read_text=None):
    """What we would send, as a reviewable dict. Sends nothing itself.

    `read_text(win)` is the injected accessibility reader: it returns a list of
    strings, or None when the backend or the permission is unavailable. Any
    failure degrades to metadata -- a question about a window we can only see
    the frame of still beats refusing to answer.
    """
    target = describe_window(win)
    lines, note = [], None
    if win is not None and read_text is not None:
        try:
            got = read_text(win)
        except Exception as e:                      # backend/permission/timeout
            got, note = None, "text unavailable (%s)" % type(e).__name__
        if got is None and note is None:
            note = "text unavailable (no accessibility access)"
        elif got:
            lines = _clean_lines(got)
    body = "\n".join(lines)
    if len(body) > MAX_CHARS:
        body = body[:MAX_CHARS] + "\n… (truncated)"
    return {
        "question": question,
        "target": target,
        "open": open_file(win),
        "pid": None if win is None else win.pid,
        "text": body,
        "note": note,
        "chars": len(body),
        "lines": len(lines),
    }


def render_preview(ctx):
    """Exactly what the user is approving, as plain text."""
    parts = ["대상: " + ctx["target"], "질문: " + ctx["question"]]
    if ctx["note"]:
        parts.append("참고: " + ctx["note"])
    if ctx["text"]:
        parts.append("")
        parts.append("보낼 내용 (%d줄, %d자):" % (ctx["lines"], ctx["chars"]))
        parts.append(ctx["text"])
    else:
        parts.append("")
        parts.append("보낼 화면 내용 없음 — 창 정보만 전송합니다.")
    return "\n".join(parts)


def render_prompt(ctx):
    """The message handed to the attached Claude session once approved."""
    parts = ["다음은 사용자가 화면에서 고른 창입니다.",
             "창: " + ctx["target"]]
    if ctx["text"]:
        parts += ["", "창에서 읽은 내용:", ctx["text"]]
    elif ctx.get("open"):
        # IDE 는 에디터 본문을 접근성 트리에 내놓지 않는다. 대신 무엇을 열어놨는지는
        # 알 수 있으니, 내용은 디스크에서 직접 읽으라고 알려준다 — 화면을 긁는 것보다
        # 정확하다.
        parts += ["", "이 창은 편집기이고 본문은 읽을 수 없습니다."
                      " 열려 있는 것은 아래와 같으니, 필요하면 파일을 직접 열어"
                      " 확인하세요.",
                  "프로젝트: %s" % ctx["open"]["project"],
                  "열린 파일: %s" % ctx["open"]["file"]]
    elif ctx["note"]:
        parts += ["", "(" + ctx["note"] + ")"]
    parts += ["", "질문: " + ctx["question"]]
    return "\n".join(parts)
