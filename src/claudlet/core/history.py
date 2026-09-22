"""A durable log of what was asked and what came back.

The mailbox in `core/ask.py` is deliberately transient -- a question is deleted
the moment it is read, an answer the moment it is shown. That is right for
delivery and wrong for everything else: there is no way to see what you asked an
hour ago, and no way to tell "the session never answered" from "the answer came
and went while you were looking at another screen".

So every exchange is appended here as well. JSON Lines, one record per line:
appending never rewrites what is already on disk, a half-written trailing line
costs one record rather than the file, and it stays readable with `tail`.

WHAT IS IN HERE IS WHAT WAS ON YOUR SCREEN. Records carry the text read from the
selected window, already redacted by core/inspect.py. That is the user's own
data on the user's own disk, but it is real content -- so the file is created
0600, the log is capped, and `claudlet-uninstall` removes it with the rest.
"""
import json
import os
import time

MAX_RECORDS = 200          # trimmed on write; see `_trim`
MAX_TEXT = 4000            # per-record cap on the captured screen text


def history_path():
    """`$XDG_CONFIG_HOME/claudlet/history.jsonl` (default `~/.config/...`).

    Beside config.json rather than in the runtime dir: the runtime dir is
    cleared on reboot, and a history that silently empties itself is worse than
    no history at all.
    """
    base = os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config")
    return os.path.join(base, "claudlet", "history.jsonl")


def _load_raw(path=None):
    """Every parseable record, oldest first. Never raises."""
    path = path or history_path()
    out = []
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except ValueError:
                    continue          # a torn line costs one record, not the log
                if isinstance(rec, dict):
                    out.append(rec)
    except OSError:
        return []
    return out


def _write_all(records, path=None):
    path = path or history_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = "{}.{}.tmp".format(path, os.getpid())
    with open(tmp, "w", encoding="utf-8") as f:
        for rec in records:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    os.replace(tmp, path)
    _chmod_private(path)


def _chmod_private(path):
    """0600. Best-effort: a failure here must not lose the record."""
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass


def _clip(text):
    if not text:
        return ""
    text = str(text)
    return text if len(text) <= MAX_TEXT else text[:MAX_TEXT] + "\n… (truncated)"


def record_question(session_id, question, target="", text="", region=None,
                    now=None):
    """Append an asked question and return its id.

    The id comes back so the answer can be attached to this exact exchange
    rather than to whatever happens to be last -- two questions can be in
    flight if the user asks again before the first is answered.
    """
    rec = {
        "id": "%d-%d" % (int((now or time.time()) * 1000), os.getpid()),
        "ts": now or time.time(),
        "session": session_id or "default",
        "question": str(question or ""),
        "target": str(target or ""),
        "text": _clip(text),
        "answer": None,
        "answered_ts": None,
    }
    if region:
        rec["region"] = {k: float(region[k]) for k in ("x", "y", "w", "h")
                         if k in region}
    append(rec)
    return rec["id"]


def record_answer(session_id, answer, rec_id=None, now=None):
    """Attach an answer to a pending question, or log it standalone.

    Without `rec_id` it attaches to the newest unanswered question in that
    session -- which is what the pet has, since the mailbox carries no id.
    """
    records = _load_raw()
    target = None
    if rec_id is not None:
        for rec in records:
            if rec.get("id") == rec_id:
                target = rec
                break
    else:
        for rec in reversed(records):
            if (rec.get("session") == (session_id or "default")
                    and rec.get("answer") is None):
                target = rec
                break
    if target is None:
        # An answer with nothing to attach to still belongs in the log: it is
        # evidence that something arrived, which is exactly what someone asking
        # "did it ever reply?" needs.
        append({
            "id": "%d-%d" % (int((now or time.time()) * 1000), os.getpid()),
            "ts": now or time.time(),
            "session": session_id or "default",
            "question": "", "target": "", "text": "",
            "answer": str(answer or ""),
            "answered_ts": now or time.time(),
        })
        return None
    target["answer"] = str(answer or "")
    target["answered_ts"] = now or time.time()
    _write_all(records)
    return target.get("id")


def append(rec, path=None):
    """Add one record, trimming the log if it has grown past MAX_RECORDS."""
    path = path or history_path()
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        new = not os.path.exists(path)
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        if new:
            _chmod_private(path)
    except OSError:
        return False
    _trim(path)
    return True


def _trim(path=None):
    """Keep the newest MAX_RECORDS. Rewrites only when over the cap."""
    path = path or history_path()
    records = _load_raw(path)
    if len(records) <= MAX_RECORDS:
        return
    _write_all(records[-MAX_RECORDS:], path)


def load(session_id=None, limit=None, pending_only=False):
    """Records newest first, optionally narrowed to one session."""
    records = _load_raw()
    if session_id:
        records = [r for r in records if r.get("session") == session_id]
    if pending_only:
        records = [r for r in records if r.get("answer") is None]
    records.reverse()
    return records[:limit] if limit else records


def clear(session_id=None):
    """Delete the log, or just one session's records. Returns how many went."""
    records = _load_raw()
    if not records:
        return 0
    if session_id is None:
        try:
            os.unlink(history_path())
        except OSError:
            pass
        return len(records)
    keep = [r for r in records if r.get("session") != session_id]
    _write_all(keep)
    return len(records) - len(keep)


# --- rendering (pure; the pet's window and the CLI both use it) -------------

def ago(ts, now=None, lang="ko"):
    """Coarse relative time. "3분 전" is what a reader wants, not a clock."""
    secs = max(0.0, (time.time() if now is None else now) - float(ts or 0))
    if lang == "en":
        if secs < 60:
            return "just now"
        if secs < 3600:
            return "%dm ago" % (secs // 60)
        if secs < 86400:
            return "%dh ago" % (secs // 3600)
        return "%dd ago" % (secs // 86400)
    if secs < 60:
        return "방금"
    if secs < 3600:
        return "%d분 전" % (secs // 60)
    if secs < 86400:
        return "%d시간 전" % (secs // 3600)
    return "%d일 전" % (secs // 86400)


def _esc(text):
    return (str(text or "").replace("&", "&amp;")
            .replace("<", "&lt;").replace(">", "&gt;"))


def render_html(records, lang="ko", full=False, now=None):
    """The exchange log as HTML for a QTextBrowser.

    HTML rather than plain text because the window has to make three things
    visually distinct at a glance -- who asked, what came back, and what was
    read off the screen -- and indentation alone does not carry that.

    Everything user-supplied goes through `_esc`: records hold text scraped
    from the user's own screen, which routinely contains angle brackets.
    """
    if not records:
        return ("<p style='color:#888'>%s</p>"
                % ("No conversations recorded yet" if lang == "en"
                   else "아직 기록된 대화가 없어요"))
    q_label = "Asked" if lang == "en" else "질문"
    a_label = "Answer" if lang == "en" else "답변"
    waiting = "waiting for an answer" if lang == "en" else "답을 기다리는 중"
    seen = "what was sent" if lang == "en" else "보낸 화면 내용"

    out = []
    for rec in records:
        out.append("<div style='margin:0 0 18px 0'>")
        head = _esc(ago(rec.get("ts"), now, lang))
        if rec.get("target"):
            head += " &middot; " + _esc(rec["target"])
        out.append("<div style='color:#888;font-size:11px'>%s</div>" % head)
        if rec.get("question"):
            out.append("<div style='margin:4px 0'><b>%s</b> %s</div>"
                       % (q_label, _esc(rec["question"])))
        answer = rec.get("answer")
        if answer:
            out.append("<div style='margin:4px 0'><b>%s</b> %s</div>"
                       % (a_label, _esc(answer)))
        else:
            out.append("<div style='margin:4px 0;color:#b06a3b'>%s</div>"
                       % waiting)
        if full and rec.get("text"):
            out.append("<div style='color:#888;font-size:11px;margin-top:6px'>"
                       "%s</div>" % seen)
            out.append("<pre style='margin:2px 0;padding:6px;background:#f3f1ee;"
                       "color:#444;font-size:11px;white-space:pre-wrap'>%s</pre>"
                       % _esc(rec["text"]))
        out.append("</div>")
    return "".join(out)
