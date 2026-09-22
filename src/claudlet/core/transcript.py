"""Read a session's transcript into a timeline the pet can show.

`core/history.py` records what was asked THROUGH THE PET. This is the other
half: what the user typed into the session directly and everything the agent did
in response -- prompts, replies, tool calls, todo lists. Together they answer
"what has this creature's session actually been doing".

The transcript is Claude Code's own JSONL, so this module only ever reads it.
Its shape is observed, not specified, which drives two rules:

  * every record type we don't recognise is skipped rather than guessed at;
  * a record missing a field we expect costs that entry, never the read.

Pure and dependency-free: the file path is resolved by the caller, so the
parsing is testable from a fixture without a real session.
"""
import glob
import json
import os

# Entry kinds the timeline can contain. Deliberately coarse -- the point is a
# readable history, not a faithful replay of the protocol.
USER = "user"           # what the person asked
AGENT = "agent"         # what the agent said back
TOOL = "tool"           # a tool the agent ran
TODO = "todo"           # a task list the agent wrote

MAX_TEXT = 2000
MAX_ENTRIES = 500

# Wrappers Claude Code puts around text that is not really the user talking.
# Showing them verbatim would fill the timeline with machinery.
_NOISE_PREFIXES = (
    "<local-command-caveat>", "<command-name>", "<command-message>",
    "<command-args>", "<local-command-stdout>", "<system-reminder>",
    "Caveat: The messages below",
)


def find_transcript(session_id, roots=None):
    """The transcript file for `session_id`, or None.

    Searched by glob across every known root: a session started under a
    CLAUDE_CONFIG_DIR profile lives under THAT profile, not ~/.claude, and
    looking only in the default location silently finds nothing.
    """
    if not session_id:
        return None
    for root in (roots if roots is not None else transcript_roots()):
        hits = glob.glob(os.path.join(root, "*", "%s.jsonl" % session_id))
        if hits:
            return hits[0]
    return None


def transcript_roots(env=None):
    """Directories that may hold transcripts, most specific first."""
    env = os.environ if env is None else env
    roots = []
    cfg = env.get("CLAUDE_CONFIG_DIR")
    if cfg:
        roots.append(os.path.join(os.path.expanduser(cfg), "projects"))
    roots.append(os.path.expanduser("~/.claude/projects"))
    # A pet may have been started against a profile the current shell knows
    # nothing about, so the configured one counts too.
    try:
        from claudlet.core import petconfig
        chosen = petconfig.pointer_config_dir()
        if chosen:
            path = os.path.join(os.path.expanduser(chosen), "projects")
            if path not in roots:
                roots.insert(0, path)
    except Exception:
        pass
    return [r for i, r in enumerate(roots) if r not in roots[:i]]


def _clip(text):
    text = " ".join(str(text or "").split())
    return text if len(text) <= MAX_TEXT else text[:MAX_TEXT] + " …"


def _is_noise(text):
    stripped = str(text or "").lstrip()
    return any(stripped.startswith(p) for p in _NOISE_PREFIXES)


def _text_of(content):
    """Plain text out of a content field that may be a string or block list."""
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return ""
    parts = []
    for block in content:
        if isinstance(block, dict) and block.get("type") == "text":
            parts.append(str(block.get("text") or ""))
    return "\n".join(parts)


def _todo_entry(block, ts):
    """A TodoWrite call rendered as a task list, or None."""
    todos = (block.get("input") or {}).get("todos")
    if not isinstance(todos, list):
        return None
    items = []
    for todo in todos:
        if not isinstance(todo, dict):
            continue
        items.append({"text": _clip(todo.get("content")
                                    or todo.get("activeForm") or ""),
                      "status": str(todo.get("status") or "")})
    if not items:
        return None
    return {"kind": TODO, "ts": ts, "items": items}


def _tool_entry(block, ts):
    """One tool call, summarised by whichever input field names it best."""
    name = str(block.get("name") or "?")
    data = block.get("input") or {}
    detail = ""
    if isinstance(data, dict):
        for key in ("description", "command", "file_path", "pattern",
                    "query", "prompt", "path", "url"):
            if data.get(key):
                detail = _clip(data[key])
                if key == "command":
                    detail = _command_gist(detail)
                break
    return {"kind": TOOL, "ts": ts, "name": name, "detail": detail}


def _command_gist(command):
    """A shell command trimmed to the part worth reading.

    A Bash call without a description falls back to the command itself, and
    those routinely open with env assignments and absolute paths -- so the
    first 70 characters are all prefix and the timeline shows six identical
    rows. Drop leading VAR=... assignments so the actual verb leads.
    """
    text = str(command or "").strip()
    while True:
        head = text.split(" ", 1)
        if len(head) == 2 and "=" in head[0] and not head[0].startswith("-"):
            name = head[0].split("=", 1)[0]
            if name and all(c.isalnum() or c == "_" for c in name):
                text = head[1].lstrip()
                continue
        break
    return text or str(command or "").strip()


def parse(lines):
    """A timeline from transcript lines (an iterable of JSON strings).

    Returns oldest-first entries. Unknown record types and malformed lines are
    skipped: this file belongs to another program and may grow shapes we have
    never seen.
    """
    out = []
    for line in lines:
        line = (line or "").strip()
        if not line:
            continue
        try:
            rec = json.loads(line)
        except ValueError:
            continue
        if not isinstance(rec, dict):
            continue
        kind = rec.get("type")
        if kind not in ("user", "assistant"):
            continue
        message = rec.get("message")
        if not isinstance(message, dict):
            continue
        ts = rec.get("timestamp") or rec.get("ts")

        if kind == "user":
            text = _text_of(message.get("content"))
            if text.strip() and not _is_noise(text):
                out.append({"kind": USER, "ts": ts, "text": _clip(text)})
            continue

        content = message.get("content")
        text = _text_of(content)
        if text.strip():
            out.append({"kind": AGENT, "ts": ts, "text": _clip(text)})
        if isinstance(content, list):
            for block in content:
                if not isinstance(block, dict):
                    continue
                if block.get("type") != "tool_use":
                    continue
                if block.get("name") == "TodoWrite":
                    entry = _todo_entry(block, ts)
                    if entry:
                        out.append(entry)
                    continue
                out.append(_tool_entry(block, ts))
    return out[-MAX_ENTRIES:]


def load(session_id, roots=None):
    """The timeline for a session, or [] when there is no readable transcript."""
    path = find_transcript(session_id, roots)
    if not path:
        return []
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            return parse(f)
    except OSError:
        return []


# --- rendering (pure, like history.render_html) -----------------------------

_KIND_STYLE = {
    USER:  ("#1f5fa9", "나" , "You"),
    AGENT: ("#2f7d4f", "펫" , "Claude"),
    TOOL:  ("#8a6a3b", "도구", "Tool"),
}


def _esc(text):
    return (str(text or "").replace("&", "&amp;")
            .replace("<", "&lt;").replace(">", "&gt;"))


_TODO_MARK = {"completed": "✓", "in_progress": "▶", "pending": "·"}


def render_html(entries, lang="ko"):
    """The session timeline as HTML for a QTextBrowser.

    Everything is escaped: these entries are the user's own prompts and file
    contents, which are full of angle brackets.
    """
    if not entries:
        return ("<p style='color:#888'>%s</p>"
                % ("No session activity found" if lang == "en"
                   else "이 세션의 기록을 찾지 못했어요"))
    out = []
    for e in entries:
        kind = e.get("kind")
        if kind == TODO:
            out.append("<div style='margin:8px 0 10px 0'>")
            out.append("<div style='color:#8a6a3b;font-size:11px'>%s</div>"
                       % ("Task list" if lang == "en" else "작업 목록"))
            for item in e.get("items") or []:
                mark = _TODO_MARK.get(item.get("status"), "·")
                done = item.get("status") == "completed"
                style = "color:#999;text-decoration:line-through" if done else ""
                out.append("<div style='margin-left:10px;%s'>%s %s</div>"
                           % (style, mark, _esc(item.get("text"))))
            out.append("</div>")
            continue
        colour, ko, en = _KIND_STYLE.get(kind, ("#666", "?", "?"))
        label = en if lang == "en" else ko
        if kind == TOOL:
            body = "<b>%s</b>" % _esc(e.get("name"))
            if e.get("detail"):
                body += " <span style='color:#777'>%s</span>" % _esc(e["detail"])
        else:
            body = _esc(e.get("text"))
        out.append(
            "<div style='margin:6px 0'>"
            "<span style='color:%s;font-size:11px'>%s</span> %s</div>"
            % (colour, label, body))
    return "".join(out)
