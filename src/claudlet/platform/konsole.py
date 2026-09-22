"""Focus a Claude session's Konsole tab/window over Konsole's D-Bus API.

Click-to-focus maps a session to its host window by process id (see
`windows.find_host`). Konsole runs every window AND every tab in ONE process, so
all of its windows/tabs share that single pid: the window pid can't tell two
Claude sessions apart, and raising the window doesn't switch to the right *tab*.
That's the "two sessions -> only the first console's tab shows" bug.

Konsole's D-Bus API can distinguish them — each `/Sessions/N` reports its shell
`processId` (an ancestor of that session's Claude process), and each `/Windows/M`
can `setCurrentSession(N)` to bring a tab to the front. Given the pet's ancestor
pids we find our own tab and select it; the caller still raises the window (via
KWin) so it comes forward over other apps.

The parsing/decision logic here is pure and tested with a fake runner
(`tests/test_konsole.py`); `pet.py` injects a real `qdbus6` runner. Best-effort:
any missing method, non-Konsole host, or bus error returns None so the caller
falls back to the plain window raise.
"""
import os
import re

_SERVICE_PREFIX = "org.kde.konsole-"
_SESSION_PATH = re.compile(r"^/Sessions/(\d+)$")
_WINDOW_PATH = re.compile(r"^/Windows/\d+$")


def _service_pid(name):
    """pid embedded in an `org.kde.konsole-<pid>` bus name, or None."""
    if not name.startswith(_SERVICE_PREFIX):
        return None
    tail = name[len(_SERVICE_PREFIX):]
    return int(tail) if tail.isdigit() else None


def pick_service(service_names, ancestor_pids):
    """The `org.kde.konsole-<pid>` bus name whose pid is one of `ancestor_pids`
    (that Konsole process is an ancestor of our Claude process). None when no
    Konsole on the bus is ours — e.g. a different terminal, or another user's
    Konsole sharing the session bus."""
    for name in service_names:
        pid = _service_pid(name)
        if pid is not None and pid in ancestor_pids:
            return name
    return None


def pick_session(session_pids, ancestor_pids):
    """`session_pids`: iterable of (session_id, shell_pid). Return the session id
    whose shell pid is one of `ancestor_pids` — our own tab — or None."""
    for sid, pid in session_pids:
        if pid in ancestor_pids:
            return sid
    return None


def window_for_session(window_sessions, session_id):
    """`window_sessions`: iterable of (window_path, [session_id,...]). Return the
    window path whose session list contains `session_id`, or None."""
    for wpath, sids in window_sessions:
        if session_id in sids:
            return wpath
    return None


def focus(ancestor_pids, run):
    """Select this session's Konsole tab. `run(*args)` shells out to `qdbus6`:
    `run()` lists bus service names, `run(service)` lists its object paths, and
    `run(service, path, method, *args)` calls a method and returns its stdout;
    it may raise on failure.

    Returns `(service, window_path, session_id)` on success, or None when this
    isn't our Konsole host or the tab can't be resolved (caller then just raises
    the window). Does NOT raise the window itself — selecting a tab doesn't bring
    Konsole forward over other apps, so the caller keeps doing that via KWin."""
    if not ancestor_pids:
        return None
    try:
        # qdbus6 prefixes each service name with a space; strip before matching.
        services = [s.strip() for s in run().splitlines() if s.strip()]
        svc = pick_service(services, ancestor_pids)
        if not svc:
            return None
        paths = [p.strip() for p in run(svc).splitlines() if p.strip()]
    except Exception:
        return None

    session_pids = []
    for p in paths:
        m = _SESSION_PATH.match(p)
        if not m:
            continue
        try:
            pid = int(run(svc, p, "org.kde.konsole.Session.processId").strip())
        except Exception:
            continue
        session_pids.append((int(m.group(1)), pid))
    sid = pick_session(session_pids, ancestor_pids)
    if sid is None:
        return None

    window_sessions = []
    for p in paths:
        if not _WINDOW_PATH.match(p):
            continue
        try:
            sids = [int(x) for x in
                    run(svc, p, "org.kde.konsole.Window.sessionList").split()]
        except Exception:
            continue
        window_sessions.append((p, sids))
    wpath = window_for_session(window_sessions, sid)
    if wpath is None:
        return None

    try:
        run(svc, wpath, "org.kde.konsole.Window.setCurrentSession", str(sid))
    except Exception:
        return None
    return (svc, wpath, sid)


def submit_text(text, submit=True):
    """실제로 제출되는 한 줄로 다듬는다. 빈 메시지면 None. 순수.

    sendText 는 받은 문자열을 그대로 키 입력처럼 밀어 넣으므로, 줄바꿈이 든
    문장을 그대로 보내면 줄마다 프롬프트가 하나씩 제출된다. 줄바꿈은 공백으로
    접고 끝에 하나만 붙인다 — 그 하나가 "엔터"다.

    그 하나는 LF 가 아니라 **CR** 이다. 터미널에서 Enter 키가 보내는 것이 CR
    이고, raw 모드로 도는 TUI(Claude Code 가 그렇다)는 CR 만 제출로 읽는다.
    LF 를 보내면 글자는 찍히는데 엔터가 안 쳐진다(실측)."""
    one = " ".join((text or "").split())
    if not one:
        return None
    return one + "\r" if submit else one


def send_enter(ancestor_pids, run):
    """엔터만 따로 보낸다.

    코덱스 TUI 는 빠르게 들어온 입력을 붙여넣기로 판단하고(그래서
    `disable_paste_burst` 설정이 있다), 그 판단 안에서는 끝의 CR 이 제출이
    아니라 줄바꿈이 된다 — 글자는 찍히는데 엔터가 안 먹는다. 잠깐 뒤에 CR 만
    따로 보내면 붙여넣기 뭉치 밖이라 제출로 읽힌다."""
    got = focus(ancestor_pids, run)
    if not got:
        return False
    svc, _window, sid = got
    try:
        run(svc, "/Sessions/%d" % sid, "org.kde.konsole.Session.sendText", "\r")
    except Exception:
        return False
    return True


def send_text(ancestor_pids, run, text, submit=True):
    """이 세션의 Konsole 탭 프롬프트에 직접 써 넣고 제출한다.

    탭을 고르는 일은 focus() 가 이미 한다 — 여기서 새로 푸는 것은 없다.
    우리 Konsole 이 아니거나 보낼 것이 없으면 False (호출자는 귓속말로
    강등한다)."""
    payload = submit_text(text, submit)
    if payload is None:
        return False
    got = focus(ancestor_pids, run)
    if not got:
        return False
    svc, _window, sid = got
    try:
        run(svc, "/Sessions/%d" % sid, "org.kde.konsole.Session.sendText", payload)
    except Exception:
        return False
    return True


# Konsole 은 sendText/runCommand 를 **기본으로 막아둔다**. introspection 에는
# 메서드가 그대로 보이는데 호출하면 AccessDenied
# ("보안에 민감한 DBus API가 비활성화되어 있습니다")가 돌아온다 — 있으니까
# 된다고 넘겨짚으면 안 되는 자리였다. 켜는 곳은
# 설정 -> Konsole 설정 -> 일반 -> "보안에 민감한 DBus API 활성화".
#
# 켜졌는지는 **찔러봐서** 안다. konsolerc 를 읽는 방법도 써 봤는데 틀린 답을
# 낸다: 사용자가 방금 체크해서 호출이 이미 되는데도 KDE 가 파일 쓰기를 미뤄
# 키가 없는 상태가 실제로 관찰됐다(2026-09-22). 빈 문자열을 보내는 것은 아무
# 것도 타이핑하지 않으므로, 이 probe 자체에는 부작용이 없다.
def can_send_text(ancestor_pids, run):
    """이 Konsole 이 sendText 를 받아주나. 빈 문자열을 실제로 보내 확인한다."""
    if not ancestor_pids:
        return False
    try:
        services = [x.strip() for x in run().splitlines() if x.strip()]
        svc = pick_service(services, ancestor_pids)
        if not svc:
            return False
        for path in (x.strip() for x in run(svc).splitlines()):
            if _SESSION_PATH.match(path or ""):
                run(svc, path, "org.kde.konsole.Session.sendText", "")
                return True
    except Exception:
        return False
    return False
