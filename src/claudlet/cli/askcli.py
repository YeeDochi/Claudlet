"""`claudlet-ask` -- ask the creature about the app under a point.

    claudlet-ask --at 1200,400 "이 창 뭐 하는 앱이야?"
    claudlet-ask --window            # list windows, pick by number
    claudlet-ask --pull              # (session side) take the pending question
    claudlet-ask --answer "..."      # (session side) send the answer back

The flow is preview-then-approve on purpose: `build_context` assembles what
WOULD be sent, we print it, and nothing leaves until the user types y. The
approval is of a specific payload, not of a standing capability -- so a later
question re-asks, and a window that turned out to hold something private can be
refused after the user has seen exactly what we read.
"""
import argparse
import sys

from claudlet.cli import utf8_output
from claudlet.core import ask, history, inspect as inspect_mod
from claudlet.core import hostinfo
from claudlet.platform.geom import parse_dump, window_at


def _windows():
    """Current window list, or [] where no backend can enumerate."""
    if sys.platform == "darwin":
        from claudlet.platform.geom import macos
        if macos.available():
            return parse_dump(macos.dump())
    elif sys.platform.startswith("win"):
        from claudlet.platform.geom import win32
        if win32.available():
            return parse_dump(win32.dump())
    return []


def text_backend(platform=None):
    """The text reader for this OS, or None where there isn't one.

    Returned rather than called so the caller can ask it for an install hint
    before deciding what to tell the user. Import is lazy per branch: neither
    backend is importable-and-useful on the other's OS.
    """
    platform = sys.platform if platform is None else platform
    if platform == "darwin":
        from claudlet.platform import axtree
        return axtree
    if platform.startswith("win"):
        from claudlet.platform import uiatree
        return uiatree
    return None


def _pick_interactive(wins, out):
    for i, w in enumerate(wins, 1):
        out.write("%2d. %s\n" % (i, inspect_mod.describe_window(w)))
    out.write("번호: ")
    out.flush()
    try:
        n = int(sys.stdin.readline().strip())
    except (ValueError, TypeError):
        return None
    return wins[n - 1] if 1 <= n <= len(wins) else None


def _confirm(prompt, out):
    out.write(prompt)
    out.flush()
    return sys.stdin.readline().strip().lower() in ("y", "yes", "ㅛ")


def main(argv=None, out=None):
    out = out or sys.stdout
    ap = argparse.ArgumentParser(prog="claudlet-ask", add_help=True)
    ap.add_argument("question", nargs="?", default="")
    ap.add_argument("--at", help="화면 좌표 'x,y'")
    ap.add_argument("--window", action="store_true", help="창 목록에서 고르기")
    ap.add_argument("--session", default=None, help="대상 세션 id")
    ap.add_argument("--yes", action="store_true", help="미리보기 확인 생략")
    ap.add_argument("--pull", action="store_true", help="(세션) 대기 중인 질문 꺼내기")
    ap.add_argument("--answer", help="(세션) 답변 보내기")
    ap.add_argument("--history", action="store_true", help="주고받은 내역 보기")
    ap.add_argument("--full", action="store_true", help="--history: 화면에서 읽은 본문까지")
    ap.add_argument("--pending", action="store_true", help="--history: 답 못 받은 것만")
    ap.add_argument("--limit", type=int, default=20, help="--history: 개수 (기본 20)")
    ap.add_argument("--all-sessions", action="store_true", help="--history: 전 세션")
    ap.add_argument("--clear-history", action="store_true", help="내역 삭제")
    args = ap.parse_args(argv)

    sid = args.session or "default"

    # --- history ------------------------------------------------------
    if args.history:
        return _show_history(args, sid, out)
    if args.clear_history:
        scope = None if args.all_sessions else sid
        n = history.clear(scope)
        where = "전체" if scope is None else "세션 %s" % scope
        out.write("내역 %d건을 지웠습니다 (%s)\n" % (n, where))
        return 0

    # --- session side -------------------------------------------------
    if args.pull:
        q = ask.take_question(sid)
        if not q:
            out.write("대기 중인 질문 없음\n")
            return 1
        out.write(q.get("prompt", "") + "\n")
        return 0
    if args.answer is not None:
        ask.post_answer(sid, args.answer)
        # The PET logs the answer, when it shows it. Logging here too would
        # double-count every reply -- both halves run for the same exchange.
        # If no pet is listening the answer is never shown, and an answer
        # nobody saw is not one the log should claim was delivered.
        out.write("답변을 펫에게 보냈습니다\n")
        return 0

    # --- pet side -----------------------------------------------------
    if not args.question:
        ap.error("질문을 입력하세요")

    wins = _windows()
    if not wins:
        out.write("창 목록을 읽을 수 없습니다 (지원되지 않는 환경)\n")
        return 2

    if args.window:
        win = _pick_interactive(wins, out)
    elif args.at:
        try:
            px, py = (int(v) for v in args.at.split(",", 1))
        except ValueError:
            ap.error("--at 형식은 'x,y' 입니다")
        win = window_at(px, py, wins)
    else:
        ap.error("--at 또는 --window 중 하나가 필요합니다")

    if win is None:
        out.write("그 지점에 창이 없습니다\n")
        return 2

    backend = text_backend()
    hint = backend.install_hint() if backend else None
    reader = backend.read_window if backend else None
    ctx = inspect_mod.build_context(win, args.question, read_text=reader)

    out.write("\n" + inspect_mod.render_preview(ctx) + "\n")
    if hint:
        out.write("\n(" + hint + ")\n")

    if not args.yes and not _confirm("\n이대로 보낼까요? [y/N] ", out):
        out.write("취소했습니다 — 아무것도 전송하지 않았습니다\n")
        return 1

    if hostinfo.read_session_port(sid) is None:
        out.write("경고: 세션 %s 에 붙은 펫을 찾지 못했습니다. "
                  "질문은 저장되니 세션에서 --pull 로 꺼내세요.\n" % sid)
    ask.post_question(sid, inspect_mod.render_prompt(ctx), ctx["target"])
    try:
        history.record_question(sid, args.question, ctx["target"], ctx["text"])
    except Exception:
        pass
    out.write("질문을 보냈습니다. 세션에서 `claudlet-ask --pull` 로 확인합니다.\n")
    return 0


def _ago(ts, now=None):
    """Human gap, coarse on purpose -- "3분 전" is what you want, not a clock."""
    import time as _t
    secs = max(0.0, (now if now is not None else _t.time()) - float(ts or 0))
    if secs < 60:
        return "방금"
    if secs < 3600:
        return "%d분 전" % (secs // 60)
    if secs < 86400:
        return "%d시간 전" % (secs // 3600)
    return "%d일 전" % (secs // 86400)


def _show_history(args, sid, out):
    """Print the exchange log. Returns an exit code."""
    scope = None if args.all_sessions else sid
    records = history.load(scope, limit=args.limit, pending_only=args.pending)
    if not records:
        out.write("기록된 대화가 없습니다\n")
        return 1
    for i, rec in enumerate(records):
        if i:
            out.write("\n")
        out.write("─" * 60 + "\n")
        head = _ago(rec.get("ts"))
        if args.all_sessions:
            head += "  [%s]" % rec.get("session", "?")
        out.write("%s\n" % head)
        if rec.get("target"):
            out.write("  대상: %s\n" % rec["target"])
        if rec.get("question"):
            out.write("  질문: %s\n" % rec["question"])
        answer = rec.get("answer")
        if answer:
            out.write("  답변: %s\n" % answer)
        else:
            out.write("  답변: (아직 없음)\n")
        if args.full and rec.get("text"):
            out.write("  ── 보낸 화면 내용 ──\n")
            for line in rec["text"].splitlines():
                out.write("  │ %s\n" % line)
    out.write("─" * 60 + "\n")
    shown = "%d건" % len(records)
    if args.pending:
        shown += " (답 못 받은 것만)"
    out.write("%s · 본문까지 보려면 --full\n" % shown)
    return 0


def _cli():
    utf8_output()
    raise SystemExit(main())
