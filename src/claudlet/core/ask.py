"""Carry a question from the pet to the Claude session it is attached to, and
the answer back.

WHY A FILE AND NOT A PROMPT INJECTION
A running `claude` process owns its own stdin; nothing lets an outside process
push a turn into it, and faking keystrokes into the user's terminal would type
into whatever is focused. So the honest mechanism is a per-session mailbox:

    <runtime_dir>/claudlet-<sid>.ask.json     pet   -> session   (question)
    <runtime_dir>/claudlet-<sid>.answer.json  session -> pet     (answer)

The session picks the question up (a hook, a skill, or the user asking Claude to
read it) and writes the answer back. The pet polls for the answer and shows it
in a speech bubble. Both files are written atomically, same as the port file, so
a reader never sees half a message.

This keeps the trust story simple: the payload the user approved is what lands
in the file, and the session that reads it is the user's own.
"""
import json
import os
import time

from claudlet.core import hostinfo

ASK_SUFFIX = ".ask.json"
ANSWER_SUFFIX = ".answer.json"

# An unread question is stale after this long: the user asked, walked away, and
# the session never picked it up. Showing a stale answer later is worse than
# showing none, because it lands next to whatever is on screen NOW.
TTL = 600.0


def _path(session_id, suffix):
    # Same shape as hostinfo.session_port_file, so all of a session's runtime
    # files sort together and the uninstaller's glob finds them.
    sid = session_id or "default"
    return os.path.join(hostinfo.runtime_dir(), "claudlet-{}{}".format(sid, suffix))


def ask_path(session_id):
    return _path(session_id, ASK_SUFFIX)


def answer_path(session_id):
    return _path(session_id, ANSWER_SUFFIX)


def _write_atomic(path, obj):
    tmp = "{}.{}.tmp".format(path, os.getpid())
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False)
    try:
        os.replace(tmp, path)
    except OSError:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def _read_json(path, ttl=TTL, now=None):
    """Parse `path`, or None when missing/corrupt/stale. Never raises."""
    try:
        with open(path, encoding="utf-8") as f:
            obj = json.load(f)
    except (OSError, ValueError):
        return None
    if not isinstance(obj, dict):
        return None
    if ttl is not None:
        ts = obj.get("ts")
        now = time.time() if now is None else now
        if not isinstance(ts, (int, float)) or now - ts > ttl:
            return None
    return obj


def post_question(session_id, prompt, target="", now=None):
    """Publish an approved question for the session to pick up."""
    _write_atomic(ask_path(session_id), {
        "ts": time.time() if now is None else now,
        "prompt": prompt,
        "target": target,
        "answered": False,
    })


def take_question(session_id, now=None):
    """Read the pending question and clear it. None when there isn't one."""
    path = ask_path(session_id)
    obj = _read_json(path, now=now)
    try:
        os.unlink(path)
    except OSError:
        pass
    return obj


def post_answer(session_id, text, now=None):
    _write_atomic(answer_path(session_id), {
        "ts": time.time() if now is None else now,
        "text": text,
    })


def take_answer(session_id, now=None):
    """Read and clear the answer. None when there isn't a fresh one."""
    path = answer_path(session_id)
    obj = _read_json(path, now=now)
    if obj is None:
        return None
    try:
        os.unlink(path)
    except OSError:
        pass
    return obj.get("text")


def clear(session_id):
    """Drop both files -- session teardown, or a cancelled question."""
    for p in (ask_path(session_id), answer_path(session_id)):
        try:
            os.unlink(p)
        except OSError:
            pass
