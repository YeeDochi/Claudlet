"""The ask flow through a real Pet: bubble, question, answer.

Drives the public entry points (`say`, `ask_about`, `_poll_answer`) rather than
poking at widgets, so a refactor of how the bubble is painted doesn't break
these. Uses the shared `pet` fixture from harness.py.
"""
import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import pytest

from claudlet import pet as P
from claudlet.core import ask as askbox
from claudlet.core import outbox


def _posted(pet):
    """세션에 닿은 질문. 배달은 아웃박스로 하고 훅이 다음 경계에서 실어 보낸다
    — 우편함과 달리 세션이 스스로 집어가지 않아도 도착한다."""
    notes = outbox.take(pet.session_id)
    return {"prompt": notes[0]["text"]} if notes else None
from claudlet.core import bubble as bubblegeom
from claudlet.platform.geom import Win

from harness import pet  # noqa: F401  (`pet` used as a fixture)


@pytest.fixture(autouse=True)
def _clean(pet):  # noqa: F811
    yield
    askbox.clear(pet.session_id)
    outbox.drop(pet.session_id)


def _win(**kw):
    base = dict(wid=1, x=100, y=100, w=400, h=300, title="Notepad", pid=7,
                caption="notepad")
    base.update(kw)
    return Win(**base)


def test_say_shows_a_bubble_with_the_text(pet):  # noqa: F811
    b = pet.say("hello there")
    assert b is not None
    assert "hello there" in b.text()
    assert b.isVisible()


def test_saying_again_replaces_the_previous_bubble(pet):  # noqa: F811
    first = pet.say("one")
    second = pet.say("two")
    assert not first.isVisible()
    assert "two" in second.text()
    assert pet._bubble is second


def test_empty_text_shows_nothing(pet):  # noqa: F811
    assert pet.say("") is None
    assert pet._bubble is None


def test_dismissing_clears_the_bubble(pet):  # noqa: F811
    pet.say("hi")
    pet._dismiss_bubble()
    assert pet._bubble is None


def test_clicking_the_bubble_dismisses_it(pet):  # noqa: F811
    b = pet.say("hi")
    b.mousePressEvent(None)
    assert pet._bubble is None


def test_a_long_answer_is_wrapped_not_dropped(pet):  # noqa: F811
    b = pet.say("한국어로 아주 긴 답변입니다. " * 12)
    assert b.text().count("\n") >= 1


def test_asking_posts_a_question_for_the_session(pet, monkeypatch):  # noqa: F811
    monkeypatch.setattr(pet, "_ask_windows", lambda: [_win()])
    monkeypatch.setattr(pet, "_ask_backend", lambda: None)
    ctx = pet.ask_about((200, 200), "what is this?")
    assert ctx is not None
    posted = _posted(pet)
    assert posted is not None
    assert "what is this?" in posted["prompt"]
    assert "Notepad" in posted["prompt"]


def test_asking_confirms_in_a_bubble(pet, monkeypatch):  # noqa: F811
    monkeypatch.setattr(pet, "_ask_windows", lambda: [_win()])
    monkeypatch.setattr(pet, "_ask_backend", lambda: None)
    pet.ask_about((200, 200), "q")
    assert pet._bubble is not None


def test_a_point_with_no_window_posts_nothing(pet, monkeypatch):  # noqa: F811
    monkeypatch.setattr(pet, "_ask_windows", lambda: [_win()])
    assert pet.ask_about((9999, 9999), "q") is None
    assert _posted(pet) is None


def test_no_enumerable_windows_posts_nothing(pet, monkeypatch):  # noqa: F811
    monkeypatch.setattr(pet, "_ask_windows", lambda: [])
    assert pet.ask_about((10, 10), "q") is None
    assert _posted(pet) is None


def test_secrets_read_off_the_window_never_reach_the_payload(pet, monkeypatch):  # noqa: F811
    class Backend:
        @staticmethod
        def read_window(_w):
            return ["Inbox", "password: hunter2", "token ghp_abcdefghij1234567890abcd"]
    monkeypatch.setattr(pet, "_ask_windows", lambda: [_win()])
    monkeypatch.setattr(pet, "_ask_backend", lambda: Backend)
    pet.ask_about((200, 200), "q")
    posted = _posted(pet)
    assert "hunter2" not in posted["prompt"]
    assert "ghp_abcdefghij" not in posted["prompt"]
    assert "Inbox" in posted["prompt"]


def test_a_posted_answer_appears_in_a_bubble(pet):  # noqa: F811
    askbox.post_answer(pet.session_id, "it is a text editor")
    pet._poll_answer()
    assert pet._bubble is not None
    assert "text editor" in pet._bubble.text()


def test_an_answer_is_shown_once(pet):  # noqa: F811
    askbox.post_answer(pet.session_id, "once")
    pet._poll_answer()
    pet._dismiss_bubble()
    pet._poll_answer()
    assert pet._bubble is None


def test_polling_an_empty_mailbox_shows_nothing(pet):  # noqa: F811
    pet._poll_answer()
    assert pet._bubble is None


def test_the_tick_loop_picks_up_an_answer(pet):  # noqa: F811
    askbox.post_answer(pet.session_id, "from the tick")
    for _ in range(P_FPS := 25):
        pet._tick()
    assert pet._bubble is not None
    assert "from the tick" in pet._bubble.text()


# ---------- follow-up from the bubble ----------

def _click(bubble, y):
    """Synthesize a click at local y -- the widget only reads position().y()."""
    class _Pos:
        def y(self):
            return y
    class _Ev:
        def position(self):
            return _Pos()
    bubble.mousePressEvent(_Ev())


def _answer(pet, text="it is a text editor"):  # noqa: F811
    askbox.post_answer(pet.session_id, text)
    pet._poll_answer()
    return pet._bubble


def test_an_answer_bubble_offers_a_follow_up(pet, monkeypatch):  # noqa: F811
    monkeypatch.setattr(pet, "_ask_backend", lambda: None)
    pet.ask_window(_win(), "q")
    _posted(pet)
    assert _answer(pet).has_reply()


def test_a_plain_bubble_offers_no_follow_up(pet):  # noqa: F811
    assert not pet.say("just talking").has_reply()


def test_the_sent_confirmation_offers_no_follow_up(pet, monkeypatch):  # noqa: F811
    # it is not an answer; re-asking from it would be re-asking the same thing
    monkeypatch.setattr(pet, "_ask_backend", lambda: None)
    pet.ask_window(_win(), "q")
    assert not pet._bubble.has_reply()


def test_no_follow_up_when_no_window_was_ever_resolved(pet, monkeypatch):  # noqa: F811
    monkeypatch.setattr(pet, "_ask_windows", lambda: [])
    pet.ask_about((10, 10), "q")
    assert not _answer(pet).has_reply()


def test_clicking_the_footer_re_asks_about_the_same_window(pet, monkeypatch):  # noqa: F811
    monkeypatch.setattr(pet, "_ask_backend", lambda: None)
    pet.ask_window(_win(title="Ledger"), "first")
    _posted(pet)
    bubble = _answer(pet)
    monkeypatch.setattr(P.Pet, "_ask_text",
                        lambda self, label=None: 'second')
    _click(bubble, bubble.height() - 6)
    posted = _posted(pet)
    assert posted is not None
    assert "second" in posted["prompt"]
    assert "Ledger" in posted["prompt"]        # same window, never re-picked


def test_the_follow_up_does_not_re_enumerate_windows(pet, monkeypatch):  # noqa: F811
    monkeypatch.setattr(pet, "_ask_backend", lambda: None)
    pet.ask_window(_win(), "first")
    _posted(pet)
    bubble = _answer(pet)
    called = []
    monkeypatch.setattr(pet, "_ask_windows", lambda: called.append(1) or [])
    monkeypatch.setattr(P.Pet, "_ask_text",
                        lambda self, label=None: 'second')
    _click(bubble, bubble.height() - 6)
    assert called == []


def test_cancelling_the_follow_up_posts_nothing(pet, monkeypatch):  # noqa: F811
    monkeypatch.setattr(pet, "_ask_backend", lambda: None)
    pet.ask_window(_win(), "first")
    _posted(pet)
    bubble = _answer(pet)
    monkeypatch.setattr(P.Pet, "_ask_text",
                        lambda self, label=None: '')
    _click(bubble, bubble.height() - 6)
    assert _posted(pet) is None


def test_an_empty_follow_up_posts_nothing(pet, monkeypatch):  # noqa: F811
    monkeypatch.setattr(pet, "_ask_backend", lambda: None)
    pet.ask_window(_win(), "first")
    _posted(pet)
    bubble = _answer(pet)
    monkeypatch.setattr(P.Pet, "_ask_text",
                        lambda self, label=None: '   ')
    _click(bubble, bubble.height() - 6)
    assert _posted(pet) is None


def test_clicking_the_text_still_dismisses(pet, monkeypatch):  # noqa: F811
    monkeypatch.setattr(pet, "_ask_backend", lambda: None)
    pet.ask_window(_win(), "q")
    _posted(pet)
    bubble = _answer(pet)
    _click(bubble, 2)
    assert pet._bubble is None
    assert _posted(pet) is None


def test_follow_up_answers_also_offer_a_follow_up(pet, monkeypatch):  # noqa: F811
    # the loop has to keep working, not just the first round
    monkeypatch.setattr(pet, "_ask_backend", lambda: None)
    pet.ask_window(_win(), "first")
    _posted(pet)
    monkeypatch.setattr(P.Pet, "_ask_text",
                        lambda self, label=None: 'second')
    _click(_answer(pet), 9999)
    _posted(pet)
    assert _answer(pet, "still here").has_reply()


def test_secrets_stay_masked_on_the_follow_up(pet, monkeypatch):  # noqa: F811
    class Backend:
        @staticmethod
        def read_window(_w):
            return ["password: hunter2"]
    monkeypatch.setattr(pet, "_ask_backend", lambda: Backend)
    pet.ask_window(_win(), "first")
    _posted(pet)
    monkeypatch.setattr(P.Pet, "_ask_text",
                        lambda self, label=None: 'second')
    _click(_answer(pet), 9999)
    posted = _posted(pet)
    assert "hunter2" not in posted["prompt"]


def test_the_follow_up_label_is_actually_painted(pet, monkeypatch):  # noqa: F811
    """A hit target over blank pixels is a silent failure -- check for ink."""
    from claudlet.core import bubble as B
    monkeypatch.setattr(pet, "_ask_backend", lambda: None)
    pet.ask_window(_win(), "q")
    _posted(pet)
    bubble = _answer(pet)
    img = bubble.grab().toImage()
    top = int(B.footer_top(bubble._lines))
    ink = 0
    for y in range(top, img.height()):
        for x in range(img.width()):
            c = img.pixelColor(x, y)
            if c.alpha() > 0 and min(c.red(), c.green(), c.blue()) < 200:
                ink += 1
    assert ink > 0


# ---------- pointer mode: drag a region ----------

def _rect(x=150, y=150, w=100, h=80):
    return {"x": float(x), "y": float(y), "w": float(w), "h": float(h)}


class _RegionBackend:
    """Records which read path was taken, so tests can assert on it."""
    def __init__(self, region_text=None, window_text=None):
        self.calls = []
        self._region_text = region_text or ["region text"]
        self._window_text = window_text or ["whole window text"]

    def read_region(self, _win, box):
        self.calls.append(("region", box))
        return list(self._region_text)

    def read_window(self, _win):
        self.calls.append(("window", None))
        return list(self._window_text)


def test_pointer_mode_arms_an_overlay_per_screen(pet):  # noqa: F811
    overlays = pet.enter_pointer()
    try:
        assert len(overlays) == len(pet._screens)
    finally:
        pet.exit_pointer()


def test_pointer_mode_uses_the_crosshair_cursor(pet):  # noqa: F811
    overlays = pet.enter_pointer()
    try:
        assert overlays[0].cursor().shape() == P.Qt.CursorShape.CrossCursor
    finally:
        pet.exit_pointer()


def test_arming_twice_does_not_stack_overlays(pet):  # noqa: F811
    pet.enter_pointer()
    try:
        assert pet.enter_pointer() is None
        assert len(pet._pointer_overlays) == len(pet._screens)
    finally:
        pet.exit_pointer()


def test_exiting_pointer_mode_clears_the_overlays(pet):  # noqa: F811
    pet.enter_pointer()
    pet.exit_pointer()
    assert pet._pointer_overlays == []


def test_exiting_twice_is_harmless(pet):  # noqa: F811
    pet.enter_pointer()
    pet.exit_pointer()
    pet.exit_pointer()
    assert pet._pointer_overlays == []


def test_a_region_resolves_to_the_window_under_its_centre(pet, monkeypatch):  # noqa: F811
    monkeypatch.setattr(pet, "_ask_windows", lambda: [_win()])
    assert pet._region_target(_rect()).title == "Notepad"


def test_a_region_off_every_window_resolves_to_nothing(pet, monkeypatch):  # noqa: F811
    monkeypatch.setattr(pet, "_ask_windows", lambda: [_win()])
    assert pet._region_target(_rect(9000, 9000, 10, 10)) is None


def test_a_region_whose_centre_misses_falls_back_to_most_overlap(pet, monkeypatch):  # noqa: F811
    # centre lands outside the window, but the region still covers part of it
    monkeypatch.setattr(pet, "_ask_windows", lambda: [_win()])
    assert pet._region_target(_rect(480, 380, 200, 200)).title == "Notepad"


def test_asking_about_a_region_reads_only_that_region(pet, monkeypatch):  # noqa: F811
    backend = _RegionBackend()
    monkeypatch.setattr(pet, "_ask_windows", lambda: [_win()])
    monkeypatch.setattr(pet, "_ask_backend", lambda: backend)
    ctx = pet.ask_region(_rect(), "what is this?")
    assert backend.calls == [("region", (150.0, 150.0, 100.0, 80.0))]
    assert "region text" in ctx["text"]
    assert "whole window text" not in ctx["text"]


def test_a_region_question_is_posted(pet, monkeypatch):  # noqa: F811
    monkeypatch.setattr(pet, "_ask_windows", lambda: [_win()])
    monkeypatch.setattr(pet, "_ask_backend", lambda: None)
    pet.ask_region(_rect(), "what is this?")
    posted = _posted(pet)
    assert posted is not None and "what is this?" in posted["prompt"]


def test_a_region_with_no_window_posts_nothing(pet, monkeypatch):  # noqa: F811
    monkeypatch.setattr(pet, "_ask_windows", lambda: [_win()])
    assert pet.ask_region(_rect(9000, 9000, 10, 10), "q") is None
    assert _posted(pet) is None


def test_secrets_in_the_region_are_masked(pet, monkeypatch):  # noqa: F811
    backend = _RegionBackend(region_text=["password: hunter2", "Ledger"])
    monkeypatch.setattr(pet, "_ask_windows", lambda: [_win()])
    monkeypatch.setattr(pet, "_ask_backend", lambda: backend)
    pet.ask_region(_rect(), "q")
    posted = _posted(pet)
    assert "hunter2" not in posted["prompt"]
    assert "Ledger" in posted["prompt"]


def test_the_follow_up_reuses_the_same_region(pet, monkeypatch):  # noqa: F811
    backend = _RegionBackend()
    monkeypatch.setattr(pet, "_ask_windows", lambda: [_win()])
    monkeypatch.setattr(pet, "_ask_backend", lambda: backend)
    pet.ask_region(_rect(), "first")
    _posted(pet)
    backend.calls.clear()
    monkeypatch.setattr(P.Pet, "_ask_text",
                        lambda self, label=None: 'second')
    bubble = _answer(pet)
    _click(bubble, bubble.height() - 6)
    assert backend.calls == [("region", (150.0, 150.0, 100.0, 80.0))]


def test_a_backend_without_region_support_falls_back_to_the_window(pet, monkeypatch):  # noqa: F811
    class WindowOnly:
        calls = []
        @staticmethod
        def read_window(_w):
            WindowOnly.calls.append("window")
            return ["whole window"]
    monkeypatch.setattr(pet, "_ask_windows", lambda: [_win()])
    monkeypatch.setattr(pet, "_ask_backend", lambda: WindowOnly)
    ctx = pet.ask_region(_rect(), "q")
    assert WindowOnly.calls == ["window"]
    assert "whole window" in ctx["text"]


def test_cancelling_pointer_mode_posts_nothing(pet):  # noqa: F811
    overlays = pet.enter_pointer()
    overlays[0]._finish()
    assert pet._pointer_overlays == []
    assert _posted(pet) is None


# ---------- order: select first, then ask ----------

def _dialog(monkeypatch, answer="what is this?", ok=True, seen=None):
    """Stub the question input, recording the label it was shown with.

    가로채는 자리가 QInputDialog 가 아니라 `_ask_text` 다 — pip 로 깔린 Qt 에는
    한글이 안 써져서, 입력은 입력기가 붙어 있는 kdialog/zenity 로 나간다.
    테스트에서 그 프로세스를 실제로 띄우면 안 되므로 이 한 곳만 막는다."""
    def fake(_self, label=None):
        if seen is not None:
            seen.append(label)
        # `_ask_text` 의 계약은 "다듬은 문자열, 아니면 빈 문자열" 이다
        return (answer or "").strip() if ok else ""
    monkeypatch.setattr(P.Pet, "_ask_text", fake)


def test_the_pointer_arms_before_anything_is_typed(pet, monkeypatch):  # noqa: F811
    seen = []
    _dialog(monkeypatch, seen=seen)
    pet.enter_pointer()
    try:
        assert seen == []              # nothing asked yet -- the user selects first
        assert pet._pointer_overlays
    finally:
        pet.exit_pointer()


def test_the_question_is_asked_after_the_region_is_picked(pet, monkeypatch):  # noqa: F811
    seen = []
    monkeypatch.setattr(pet, "_ask_windows", lambda: [_win()])
    monkeypatch.setattr(pet, "_ask_backend", lambda: None)
    _dialog(monkeypatch, seen=seen)
    pet.enter_pointer()[0].on_region(_rect())
    assert len(seen) == 1
    posted = _posted(pet)
    assert posted is not None and "what is this?" in posted["prompt"]


def test_the_prompt_names_what_was_selected(pet, monkeypatch):  # noqa: F811
    seen = []
    monkeypatch.setattr(pet, "_ask_windows", lambda: [_win(title="Ledger")])
    monkeypatch.setattr(pet, "_ask_backend", lambda: None)
    _dialog(monkeypatch, seen=seen)
    pet.enter_pointer()[0].on_region(_rect())
    assert "Ledger" in seen[0]


def test_a_region_hitting_nothing_never_asks_the_question(pet, monkeypatch):  # noqa: F811
    # the point of selecting first: don't make someone type before finding out
    seen = []
    monkeypatch.setattr(pet, "_ask_windows", lambda: [_win()])
    _dialog(monkeypatch, seen=seen)
    pet.enter_pointer()[0].on_region(_rect(9000, 9000, 10, 10))
    assert seen == []
    assert _posted(pet) is None


def test_cancelling_the_question_after_selecting_posts_nothing(pet, monkeypatch):  # noqa: F811
    monkeypatch.setattr(pet, "_ask_windows", lambda: [_win()])
    monkeypatch.setattr(pet, "_ask_backend", lambda: None)
    _dialog(monkeypatch, answer="", ok=False)
    pet.enter_pointer()[0].on_region(_rect())
    assert _posted(pet) is None
    assert pet._bubble is not None          # told the user it was cancelled


def test_an_empty_question_after_selecting_posts_nothing(pet, monkeypatch):  # noqa: F811
    monkeypatch.setattr(pet, "_ask_windows", lambda: [_win()])
    monkeypatch.setattr(pet, "_ask_backend", lambda: None)
    _dialog(monkeypatch, answer="   ", ok=True)
    pet.enter_pointer()[0].on_region(_rect())
    assert _posted(pet) is None


def test_picking_a_region_disarms_the_pointer(pet, monkeypatch):  # noqa: F811
    monkeypatch.setattr(pet, "_ask_windows", lambda: [_win()])
    monkeypatch.setattr(pet, "_ask_backend", lambda: None)
    _dialog(monkeypatch)
    pet.enter_pointer()[0].on_region(_rect())
    assert pet._pointer_overlays == []


def test_the_region_survives_into_the_posted_question(pet, monkeypatch):  # noqa: F811
    backend = _RegionBackend()
    monkeypatch.setattr(pet, "_ask_windows", lambda: [_win()])
    monkeypatch.setattr(pet, "_ask_backend", lambda: backend)
    _dialog(monkeypatch)
    pet.enter_pointer()[0].on_region(_rect())
    assert backend.calls == [("region", (150.0, 150.0, 100.0, 80.0))]


def test_the_menu_entry_arms_the_pointer_directly(pet, monkeypatch):  # noqa: F811
    seen = []
    _dialog(monkeypatch, seen=seen)
    pet._start_ask()
    try:
        assert pet._pointer_overlays        # armed
        assert seen == []                   # and asked nothing yet
    finally:
        pet.exit_pointer()


# ---------- macOS: the bubble must survive the app being deactivated ----------

def _offscreen():
    """True when Qt is on a platform with no real NSWindow.

    The suite forces offscreen at import (harness.py), so these two checks only
    run when someone deliberately runs them against a display. They are kept
    because the bug they cover -- an answer bubble that is invisible in normal
    use -- is invisible to every offscreen test by construction.
    """
    from PyQt6.QtWidgets import QApplication
    return QApplication.platformName() in ("offscreen", "minimal", "vnc")


def _hides_on_deactivate(widget):
    """NSPanel.hidesOnDeactivate for a shown widget, or None off macOS."""
    if sys.platform != "darwin":
        return None
    try:
        import objc
        return bool(objc.objc_object(
            c_void_p=int(widget.winId())).window().hidesOnDeactivate())
    except Exception:
        return None


@pytest.mark.skipif(
    sys.platform != "darwin" or _offscreen(),
    reason="needs a real NSWindow; the offscreen platform has none")
def test_the_bubble_does_not_hide_when_another_app_is_frontmost(pet):  # noqa: F811
    """Qt.Tool is an NSPanel and hidesOnDeactivate defaults to YES.

    Left alone, the bubble vanishes the moment the user's own terminal is
    frontmost -- which is always, because that is where they asked from. This
    is the regression that made the first real answer invisible.
    """
    bubble = pet.say("answer text")
    assert _hides_on_deactivate(bubble) is False


@pytest.mark.skipif(
    sys.platform != "darwin" or _offscreen(),
    reason="needs a real NSWindow; the offscreen platform has none")
def test_the_pointer_overlay_does_not_hide_either(pet):  # noqa: F811
    overlays = pet.enter_pointer()
    try:
        assert _hides_on_deactivate(overlays[0]) is False
    finally:
        pet.exit_pointer()


# ---------- the bubble follows the creature ----------

def _centre_offset(pet, bubble):  # noqa: F811
    pr, br = pet.geometry(), bubble.geometry()
    return (br.x() + br.width() // 2) - (pr.x() + pr.width() // 2)


def _move(pet, x, y):  # noqa: F811
    """Move the pet the way the running app does.

    moveEvent is the live path, but Qt does not deliver it to a hidden widget
    (the fixture never show()s one), so the reposition that actually guarantees
    correctness is the one on the tick. Driving both here keeps the test honest
    about which mechanism it is relying on.
    """
    pet.setGeometry(x, y, 120, 105)
    pet._reposition_bubble()


def _inner(pet, frac_x, frac_y):  # noqa: F811
    """A point well inside the screen, so nothing is clamped.

    Coordinates have to come from the actual screen: the offscreen platform
    reports 800x800, and hard-coded points outside it made the bubble clamp --
    correct behaviour that looked like a following bug.
    """
    sx, sy, sw, sh = pet._screen_rect()
    return int(sx + sw * frac_x), int(sy + sh * frac_y)


def test_the_bubble_moves_with_the_pet(pet):  # noqa: F811
    _move(pet, *_inner(pet, 0.3, 0.5))
    bubble = pet.say("follow me")
    _move(pet, *_inner(pet, 0.6, 0.3))
    assert _centre_offset(pet, bubble) == 0


def test_the_bubble_follows_repeated_moves(pet):  # noqa: F811
    _move(pet, *_inner(pet, 0.3, 0.5))
    bubble = pet.say("follow me")
    for fx, fy in ((0.6, 0.3), (0.2, 0.7), (0.5, 0.4)):
        _move(pet, *_inner(pet, fx, fy))
        assert _centre_offset(pet, bubble) == 0


def test_the_bubble_follows_while_the_pet_roams(pet):  # noqa: F811
    """The real case: the pet moves on its own every tick, not just on drag."""
    bubble = pet.say("follow me")
    pet._docked = False
    pet.mode = "roam"
    drifted = []
    for _ in range(40):
        pet._tick()
        br = bubble.geometry()
        # Centred, unless the bubble had to clamp to stay on screen -- both are
        # correct; what would be wrong is the bubble trailing a tick behind,
        # which is what happened when the reposition ran before the pet moved.
        centred = _centre_offset(pet, bubble) == 0
        sx, _, sw, _ = pet._screen_rect()
        clamped = (br.x() <= sx + bubblegeom.MARGIN
                   or br.x() + br.width() >= sx + sw - bubblegeom.MARGIN)
        if not (centred or clamped):
            drifted.append((pet.geometry().x(), br.x()))
    assert drifted == []


def test_the_bubble_does_not_lag_a_tick_behind(pet):  # noqa: F811
    """The reposition must run after the pet's own move within the tick."""
    bubble = pet.say("follow me")
    pet._docked = False
    pet.mode = "roam"
    lagging = 0
    for _ in range(40):
        pet._tick()
        if _centre_offset(pet, bubble) != 0:
            br = bubble.geometry()
            sx, _, sw, _ = pet._screen_rect()
            if not (br.x() <= sx + bubblegeom.MARGIN
                    or br.x() + br.width() >= sx + sw - bubblegeom.MARGIN):
                lagging += 1
    assert lagging == 0


def test_following_keeps_the_bubble_on_screen(pet):  # noqa: F811
    sx, sy, sw, sh = pet._screen_rect()
    bubble = pet.say("a fairly long answer so the bubble is wide enough to clamp")
    for x, y in ((sx, 400), (sx + sw - 120, 400), (700, sy)):
        _move(pet, x, y)
        b = bubble.geometry()
        assert b.x() >= sx and b.x() + b.width() <= sx + sw
        assert b.y() >= sy and b.y() + b.height() <= sy + sh


def test_the_bubble_flips_below_when_the_pet_is_at_the_top(pet):  # noqa: F811
    sx, sy, sw, sh = pet._screen_rect()
    bubble = pet.say("hi")
    _move(pet, *_inner(pet, 0.5, 0.5))
    assert not bubble._below
    _move(pet, _inner(pet, 0.5, 0.0)[0], sy)
    assert bubble._below


def test_following_does_not_resize_the_bubble(pet):  # noqa: F811
    bubble = pet.say("some answer text here")
    before = (bubble.width(), bubble.height())
    _move(pet, *_inner(pet, 0.6, 0.3))
    assert (bubble.width(), bubble.height()) == before


def test_moving_without_a_bubble_is_harmless(pet):  # noqa: F811
    assert pet._bubble is None
    _move(pet, *_inner(pet, 0.6, 0.3))       # must not raise
    assert pet._bubble is None


def test_a_dismissed_bubble_is_not_followed(pet):  # noqa: F811
    bubble = pet.say("hi")
    pet._dismiss_bubble()
    _move(pet, *_inner(pet, 0.6, 0.3))       # must not raise on the dead widget
    assert pet._bubble is None


def test_the_tail_tracks_the_pet_when_clamped(pet):  # noqa: F811
    """At a screen edge the bubble stops moving but the tail must keep pointing."""
    sx, _, _, _ = pet._screen_rect()
    bubble = pet.say("a long enough answer that the bubble gets clamped at the edge")
    _move(pet, sx + 200, 400)
    far = bubble._tail
    _move(pet, sx, 400)
    assert bubble._tail != far


# ---------- the creature acts busy while the question is in flight ----------

def test_asking_starts_the_thinking_motion(pet, monkeypatch):  # noqa: F811
    monkeypatch.setattr(pet, "_ask_backend", lambda: None)
    assert pet._motion is None
    pet.ask_window(_win(), "q")
    assert pet._motion == "thinking"
    assert pet._ask_waiting


def test_the_thinking_motion_does_not_expire_on_its_own(pet, monkeypatch):  # noqa: F811
    """There is no telling how long the session takes; a timer would go still."""
    monkeypatch.setattr(pet, "_ask_backend", lambda: None)
    pet.ask_window(_win(), "q")
    assert pet._motion_expiry is None


def test_the_answer_stops_the_thinking_motion(pet, monkeypatch):  # noqa: F811
    monkeypatch.setattr(pet, "_ask_backend", lambda: None)
    pet.ask_window(_win(), "q")
    _posted(pet)
    _answer(pet)
    assert pet._motion is None
    assert not pet._ask_waiting


def test_a_user_chosen_motion_survives_the_answer(pet, monkeypatch):  # noqa: F811
    """Picking a motion from the menu while waiting must not be undone."""
    monkeypatch.setattr(pet, "_ask_backend", lambda: None)
    pet.ask_window(_win(), "q")
    _posted(pet)
    pet._play_motion("jump", 2.5)
    _answer(pet)
    assert pet._motion == "jump"


def test_the_creature_gives_up_waiting_eventually(pet, monkeypatch):  # noqa: F811
    """A question nobody pulls is dropped by the mailbox; stop acting busy."""
    import time as _time
    monkeypatch.setattr(pet, "_ask_backend", lambda: None)
    pet.ask_window(_win(), "q")
    pet._ask_waiting_since = _time.monotonic() - P.ASK_WAIT_TIMEOUT - 1
    pet._tick()
    assert not pet._ask_waiting
    assert pet._motion is None


def test_waiting_survives_an_ordinary_tick(pet, monkeypatch):  # noqa: F811
    monkeypatch.setattr(pet, "_ask_backend", lambda: None)
    pet.ask_window(_win(), "q")
    for _ in range(5):
        pet._tick()
    assert pet._ask_waiting
    assert pet._motion == "thinking"


def test_a_question_that_never_posts_does_not_start_thinking(pet, monkeypatch):  # noqa: F811
    monkeypatch.setattr(pet, "_ask_windows", lambda: [_win()])
    pet.ask_region(_rect(9000, 9000, 10, 10), "q")   # misses every window
    assert not pet._ask_waiting
    assert pet._motion is None


def test_ending_thinking_twice_is_harmless(pet, monkeypatch):  # noqa: F811
    monkeypatch.setattr(pet, "_ask_backend", lambda: None)
    pet.ask_window(_win(), "q")
    pet._end_thinking()
    pet._end_thinking()
    assert not pet._ask_waiting


# ---------- the exchange is logged, not just delivered ----------

@pytest.fixture
def _hist(tmp_path, monkeypatch):
    """History in a tmp dir so tests never touch the real log."""
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    return tmp_path


def test_asking_records_the_question(pet, monkeypatch, _hist):  # noqa: F811
    from claudlet.core import history as H
    monkeypatch.setattr(pet, "_ask_backend", lambda: None)
    pet.ask_window(_win(title="Ledger"), "what is this?")
    rec = H.load(pet.session_id)[0]
    assert rec["question"] == "what is this?"
    assert "Ledger" in rec["target"]


def test_the_answer_lands_on_the_same_exchange(pet, monkeypatch, _hist):  # noqa: F811
    from claudlet.core import history as H
    monkeypatch.setattr(pet, "_ask_backend", lambda: None)
    pet.ask_window(_win(), "q")
    _posted(pet)
    _answer(pet, "the reply")
    recs = H.load(pet.session_id)
    assert len(recs) == 1
    assert recs[0]["answer"] == "the reply"


def test_an_unanswered_question_stays_pending_in_the_log(pet, monkeypatch, _hist):  # noqa: F811
    from claudlet.core import history as H
    monkeypatch.setattr(pet, "_ask_backend", lambda: None)
    pet.ask_window(_win(), "q")
    _posted(pet)     # session read it but never replied
    assert H.load(pet.session_id, pending_only=True)


def test_the_logged_screen_text_is_still_redacted(pet, monkeypatch, _hist):  # noqa: F811
    """Secrets must not reach disk just because we started keeping a log."""
    from claudlet.core import history as H
    class Backend:
        @staticmethod
        def read_window(_w):
            return ["Ledger", "password: hunter2"]
    monkeypatch.setattr(pet, "_ask_backend", lambda: Backend)
    pet.ask_window(_win(), "q")
    rec = H.load(pet.session_id)[0]
    assert "hunter2" not in rec["text"]
    assert "Ledger" in rec["text"]


def test_the_selected_region_is_recorded(pet, monkeypatch, _hist):  # noqa: F811
    from claudlet.core import history as H
    monkeypatch.setattr(pet, "_ask_windows", lambda: [_win()])
    monkeypatch.setattr(pet, "_ask_backend", lambda: None)
    pet.ask_region(_rect(), "q")
    assert H.load(pet.session_id)[0]["region"]["w"] == 100.0


def test_a_broken_history_never_loses_the_question(pet, monkeypatch, _hist):  # noqa: F811
    """Logging is a side benefit; delivery is the job."""
    from claudlet.core import history as H
    monkeypatch.setattr(pet, "_ask_backend", lambda: None)
    monkeypatch.setattr(H, "record_question",
                        lambda *a, **k: (_ for _ in ()).throw(OSError("disk full")))
    pet.ask_window(_win(), "q")
    assert _posted(pet) is not None


# ---------- the pointer's cursor is configurable ----------

def _pixmap(w=32, h=32):
    from PyQt6.QtGui import QPixmap, QColor
    pm = QPixmap(w, h)
    pm.fill(QColor("red"))
    return pm


def test_the_default_cursor_is_a_crosshair():
    assert P.pointer_cursor({}).shape() == P.Qt.CursorShape.CrossCursor


@pytest.mark.parametrize("name,shape", [
    ("pointing", "PointingHandCursor"),
    ("arrow", "ArrowCursor"),
    ("open-hand", "OpenHandCursor"),
])
def test_a_named_cursor_is_used(name, shape):
    assert P.pointer_cursor({"cursor": name}).shape().name == shape


def test_an_unknown_name_falls_back_to_the_crosshair():
    assert P.pointer_cursor({"cursor": "wobble"}).shape() == P.Qt.CursorShape.CrossCursor


def test_a_custom_image_becomes_the_cursor():
    cur = P.pointer_cursor({"image": "x.png"}, load=lambda _p: _pixmap())
    assert cur.shape() == P.Qt.CursorShape.BitmapCursor


def test_an_image_is_centred_by_default():
    cur = P.pointer_cursor({"image": "x.png"}, load=lambda _p: _pixmap(32, 32))
    assert (cur.hotSpot().x(), cur.hotSpot().y()) == (16, 16)


def test_an_explicit_hotspot_is_used():
    cur = P.pointer_cursor({"image": "x.png", "hotspot": [0, 0]},
                           load=lambda _p: _pixmap())
    assert (cur.hotSpot().x(), cur.hotSpot().y()) == (0, 0)


def test_an_out_of_range_hotspot_is_clamped():
    """An un-aimable cursor is worse than a slightly wrong hotspot."""
    cur = P.pointer_cursor({"image": "x.png", "hotspot": [999, 999]},
                           load=lambda _p: _pixmap(32, 32))
    assert (cur.hotSpot().x(), cur.hotSpot().y()) == (31, 31)


def test_an_oversized_image_is_scaled_down():
    cur = P.pointer_cursor({"image": "x.png"}, load=lambda _p: _pixmap(512, 512))
    from claudlet.core import petconfig as PC
    assert cur.pixmap().width() <= PC.POINTER_IMAGE_MAX


def test_a_missing_image_falls_back_to_the_named_cursor():
    from PyQt6.QtGui import QPixmap
    cur = P.pointer_cursor({"image": "gone.png", "cursor": "arrow"},
                           load=lambda _p: QPixmap())
    assert cur.shape() == P.Qt.CursorShape.ArrowCursor


def test_a_loader_that_raises_falls_back():
    def boom(_p):
        raise OSError("unreadable")
    cur = P.pointer_cursor({"image": "x.png", "cursor": "pointing"}, load=boom)
    assert cur.shape() == P.Qt.CursorShape.PointingHandCursor


def test_the_overlay_uses_the_configured_cursor(pet, monkeypatch):  # noqa: F811
    monkeypatch.setattr(pet, "_pointer_cfg", lambda: {"cursor": "pointing"})
    overlays = pet.enter_pointer()
    try:
        assert overlays[0].cursor().shape() == P.Qt.CursorShape.PointingHandCursor
    finally:
        pet.exit_pointer()


def test_a_broken_pointer_config_still_arms_the_pointer(pet, monkeypatch):  # noqa: F811
    def boom():
        raise OSError("unreadable config")
    monkeypatch.setattr(pet.__class__, "_pointer_cfg", lambda self: {})
    monkeypatch.setattr(P.petconfig, "load_config", boom)
    overlays = pet.enter_pointer()
    try:
        assert overlays
    finally:
        pet.exit_pointer()


# ---------- pointer settings in the right-click menu ----------

def _menu_tree(pet):  # noqa: F811
    """Build the context menu without showing it, as a plain data tree.

    The QMenu and its QActions are destroyed the moment _menu() returns, so
    anything held across that boundary is a dangling C++ pointer. Snapshot what
    we need while it is still alive.
    """
    from PyQt6.QtWidgets import QMenu

    def snap(menu):
        out = []
        for act in menu.actions():
            if act.isSeparator():
                continue
            out.append({"text": act.text(),
                        "checked": act.isChecked(),
                        "sub": snap(act.menu()) if act.menu() else None})
        return out

    captured = {}
    original = QMenu.exec
    QMenu.exec = lambda self, pos=None: captured.__setitem__("tree", snap(self))
    try:
        pet._menu(None)
    finally:
        QMenu.exec = original
    return captured.get("tree") or []


def _find(items, prefix):
    for item in items:
        if item["text"].startswith(prefix):
            return item
    return None


@pytest.fixture
def _pcfg(tmp_path, monkeypatch):
    import os as _os
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    _os.makedirs(str(tmp_path / "claudlet"), exist_ok=True)
    return tmp_path


def test_the_menu_has_a_pointer_settings_submenu(pet, _pcfg):  # noqa: F811
    sub = _find(_menu_tree(pet), "🎯 포인터 설정")
    assert sub is not None and sub["sub"]


def test_every_cursor_shape_is_offered(pet, _pcfg):  # noqa: F811
    from claudlet.core import petconfig as PC
    sub = _find(_menu_tree(pet), "🎯 포인터 설정")["sub"]
    shapes = _find(sub, "커서 모양")["sub"]
    assert [i["text"] for i in shapes] == list(PC.POINTER_CURSORS)


def test_the_active_cursor_is_ticked(pet, _pcfg):  # noqa: F811
    pet._save_pointer({"cursor": "arrow"}, notify=False)
    sub = _find(_menu_tree(pet), "🎯 포인터 설정")["sub"]
    shapes = _find(sub, "커서 모양")["sub"]
    assert [i["text"] for i in shapes if i["checked"]] == ["arrow"]


def test_no_shape_is_ticked_while_an_image_is_set(pet, _pcfg):  # noqa: F811
    """The image wins, so ticking a shape as well would misreport what is used."""
    pet._save_pointer({"image": "/tmp/x.png"}, notify=False)
    sub = _find(_menu_tree(pet), "🎯 포인터 설정")["sub"]
    shapes = _find(sub, "커서 모양")["sub"]
    assert not any(i["checked"] for i in shapes)


def test_clear_entries_appear_only_when_there_is_something_to_clear(pet, _pcfg):  # noqa: F811
    sub = _find(_menu_tree(pet), "🎯 포인터 설정")["sub"]
    assert _find(sub, "커서 이미지 지우기") is None
    pet._save_pointer({"image": "/tmp/x.png"}, notify=False)
    sub = _find(_menu_tree(pet), "🎯 포인터 설정")["sub"]
    assert _find(sub, "커서 이미지 지우기") is not None


def test_the_profile_clear_entry_is_conditional_too(pet, _pcfg):  # noqa: F811
    sub = _find(_menu_tree(pet), "🎯 포인터 설정")["sub"]
    assert _find(sub, "세션 프로필 해제") is None
    pet._save_pointer({"claude_config_dir": "/profiles/dev"}, notify=False)
    sub = _find(_menu_tree(pet), "🎯 포인터 설정")["sub"]
    assert _find(sub, "세션 프로필 해제") is not None


def test_saving_a_setting_keeps_the_others(pet, _pcfg):  # noqa: F811
    from claudlet.core import petconfig as PC
    pet._save_pointer({"claude_config_dir": "/profiles/dev"}, notify=False)
    pet._save_pointer({"cursor": "arrow"}, notify=False)
    saved = PC.load_config()["pointer"]
    assert saved["claude_config_dir"] == "/profiles/dev"
    assert saved["cursor"] == "arrow"


def test_saving_confirms_in_a_bubble(pet, _pcfg):  # noqa: F811
    pet._save_pointer({"cursor": "arrow"})
    assert pet._bubble is not None


def test_a_failed_save_does_not_crash(pet, _pcfg, monkeypatch):  # noqa: F811
    from claudlet.core import petconfig as PC
    monkeypatch.setattr(PC, "save_keys",
                        lambda *a, **k: (_ for _ in ()).throw(OSError("read-only")))
    assert pet._save_pointer({"cursor": "arrow"}, notify=False) is None


def test_picking_an_image_that_is_not_one_is_refused(pet, _pcfg, monkeypatch):  # noqa: F811
    from claudlet.core import petconfig as PC
    bad = _pcfg / "notreally.png"
    bad.write_text("this is not a png")
    monkeypatch.setattr(P.QFileDialog, "getOpenFileName",
                        staticmethod(lambda *a, **k: (str(bad), "")))
    assert pet._pick_pointer_image() is None
    assert PC.load_config()["pointer"]["image"] is None


def test_cancelling_the_image_picker_changes_nothing(pet, _pcfg, monkeypatch):  # noqa: F811
    from claudlet.core import petconfig as PC
    monkeypatch.setattr(P.QFileDialog, "getOpenFileName",
                        staticmethod(lambda *a, **k: ("", "")))
    assert pet._pick_pointer_image() is None
    assert PC.load_config()["pointer"]["image"] is None


def test_picking_a_real_image_saves_it(pet, _pcfg, monkeypatch):  # noqa: F811
    from PyQt6.QtGui import QPixmap, QColor
    from claudlet.core import petconfig as PC
    good = _pcfg / "cur.png"
    pm = QPixmap(16, 16)
    pm.fill(QColor("red"))
    pm.save(str(good))
    monkeypatch.setattr(P.QFileDialog, "getOpenFileName",
                        staticmethod(lambda *a, **k: (str(good), "")))
    pet._pick_pointer_image()
    assert PC.load_config()["pointer"]["image"] == str(good)


def test_cancelling_the_profile_picker_changes_nothing(pet, _pcfg, monkeypatch):  # noqa: F811
    from claudlet.core import petconfig as PC
    monkeypatch.setattr(P.QFileDialog, "getExistingDirectory",
                        staticmethod(lambda *a, **k: ""))
    assert pet._pick_pointer_dir() is None
    assert PC.load_config()["pointer"]["claude_config_dir"] is None


def test_picking_a_profile_saves_it(pet, _pcfg, monkeypatch):  # noqa: F811
    from claudlet.core import petconfig as PC
    monkeypatch.setattr(P.QFileDialog, "getExistingDirectory",
                        staticmethod(lambda *a, **k: "/profiles/dev"))
    pet._pick_pointer_dir()
    assert PC.load_config()["pointer"]["claude_config_dir"] == "/profiles/dev"


# ---------- the pet's own conversation log ----------

def test_the_menu_offers_the_conversation_log(pet, _pcfg):  # noqa: F811
    assert _find(_menu_tree(pet), "🗒 대화 내역") is not None


def test_the_log_shows_this_pets_exchanges(pet, _hist):  # noqa: F811
    from claudlet.core import history as H
    H.record_question(pet.session_id, "what is this?", "Safari")
    H.record_answer(pet.session_id, "a wiki page")
    win = pet.show_history()
    try:
        assert "what is this?" in win.html()
        assert "a wiki page" in win.html()
    finally:
        win.close()


def test_the_log_excludes_other_sessions(pet, _hist):  # noqa: F811
    """Each pet is paired with one session; this answers "what did I ask THIS one"."""
    from claudlet.core import history as H
    H.record_question(pet.session_id, "mine")
    H.record_question("someone-else", "theirs")
    win = pet.show_history()
    try:
        assert [r["question"] for r in win.records()] == ["mine"]
        assert "theirs" not in win.html()
    finally:
        win.close()


def test_an_empty_log_says_so_rather_than_showing_nothing(pet, _hist):  # noqa: F811
    win = pet.show_history()
    try:
        assert "아직" in win.html()
    finally:
        win.close()


def test_the_screen_text_is_behind_a_toggle(pet, _hist):  # noqa: F811
    from claudlet.core import history as H
    H.record_question(pet.session_id, "q", "Safari", "PAGE BODY TEXT")
    win = pet.show_history()
    try:
        assert "PAGE BODY TEXT" not in win.html()
        win._toggle.setChecked(True)
        assert "PAGE BODY TEXT" in win.html()
    finally:
        win.close()


def test_clearing_only_drops_this_pets_records(pet, _hist):  # noqa: F811
    from claudlet.core import history as H
    H.record_question(pet.session_id, "mine")
    H.record_question("someone-else", "theirs")
    win = pet.show_history()
    try:
        win._clear_history()
        assert win.records() == []
        assert len(H.load("someone-else")) == 1
    finally:
        win.close()


def test_clearing_is_disabled_with_nothing_to_clear(pet, _hist):  # noqa: F811
    win = pet.show_history()
    try:
        assert not win._clear.isEnabled()
    finally:
        win.close()


def test_reopening_reuses_the_same_window(pet, _hist):  # noqa: F811
    first = pet.show_history()
    try:
        assert pet.show_history() is first
    finally:
        first.close()


def test_the_window_refreshes_on_reopen(pet, _hist):  # noqa: F811
    from claudlet.core import history as H
    win = pet.show_history()
    try:
        H.record_question(pet.session_id, "asked after opening")
        pet.show_history()
        assert "asked after opening" in win.html()
    finally:
        win.close()


def test_a_broken_log_does_not_take_the_window_down(pet, _hist, monkeypatch):  # noqa: F811
    from claudlet.core import history as H
    monkeypatch.setattr(H, "load",
                        lambda *a, **k: (_ for _ in ()).throw(OSError("bad disk")))
    win = pet.show_history()
    try:
        assert win.records() == []
    finally:
        win.close()


# ---------- the log's two views ----------

def test_the_window_opens_on_the_pet_conversation(pet, _hist):  # noqa: F811
    win = pet.show_history()
    try:
        assert win.view() == "pet"
    finally:
        win.close()


def test_switching_to_session_activity(pet, _hist):  # noqa: F811
    win = pet.show_history()
    try:
        win._tabs.setCurrentIndex(1)
        assert win.view() == "session"
    finally:
        win.close()


def test_session_activity_shows_the_transcript(pet, _hist, tmp_path, monkeypatch):  # noqa: F811
    import json
    from claudlet.core import transcript as T
    proj = tmp_path / "proj"
    proj.mkdir()
    (proj / ("%s.jsonl" % pet.session_id)).write_text("\n".join([
        json.dumps({"type": "user",
                    "message": {"role": "user", "content": "build the thing"}}),
        json.dumps({"type": "assistant", "message": {"role": "assistant",
                    "content": [{"type": "text", "text": "on it"},
                                {"type": "tool_use", "name": "Bash",
                                 "input": {"description": "run the build"}}]}}),
    ]))
    monkeypatch.setattr(T, "transcript_roots", lambda *a, **k: [str(tmp_path)])
    win = pet.show_history()
    try:
        win._tabs.setCurrentIndex(1)
        html = win.html()
        assert "build the thing" in html      # the user's own request
        assert "on it" in html                # what the agent said
        assert "run the build" in html        # what the agent did
    finally:
        win.close()


def test_a_task_list_appears_in_session_activity(pet, _hist, tmp_path, monkeypatch):  # noqa: F811
    import json
    from claudlet.core import transcript as T
    proj = tmp_path / "proj"
    proj.mkdir()
    (proj / ("%s.jsonl" % pet.session_id)).write_text(json.dumps(
        {"type": "assistant", "message": {"role": "assistant", "content": [
            {"type": "tool_use", "name": "TodoWrite", "input": {"todos": [
                {"content": "first step", "status": "completed"},
                {"content": "second step", "status": "in_progress"}]}}]}}))
    monkeypatch.setattr(T, "transcript_roots", lambda *a, **k: [str(tmp_path)])
    win = pet.show_history()
    try:
        win._tabs.setCurrentIndex(1)
        assert "first step" in win.html() and "second step" in win.html()
    finally:
        win.close()


def test_write_controls_are_off_for_the_transcript(pet, _hist):  # noqa: F811
    """It is Claude Code's file; we only read it."""
    win = pet.show_history()
    try:
        win._tabs.setCurrentIndex(1)
        assert not win._clear.isEnabled()
        assert not win._toggle.isEnabled()
    finally:
        win.close()


def test_write_controls_come_back_on_the_pet_tab(pet, _hist):  # noqa: F811
    from claudlet.core import history as H
    H.record_question(pet.session_id, "q")
    win = pet.show_history()
    try:
        win._tabs.setCurrentIndex(1)
        win._tabs.setCurrentIndex(0)
        assert win._clear.isEnabled() and win._toggle.isEnabled()
    finally:
        win.close()


def test_a_missing_transcript_says_so(pet, _hist, monkeypatch):  # noqa: F811
    from claudlet.core import transcript as T
    monkeypatch.setattr(T, "transcript_roots", lambda *a, **k: ["/no/such/root"])
    win = pet.show_history()
    try:
        win._tabs.setCurrentIndex(1)
        assert "찾지 못했" in win.html()
    finally:
        win.close()


def test_an_unreadable_transcript_does_not_break_the_window(pet, _hist, monkeypatch):  # noqa: F811
    from claudlet.core import transcript as T
    monkeypatch.setattr(T, "load",
                        lambda *a, **k: (_ for _ in ()).throw(OSError("bad")))
    win = pet.show_history()
    try:
        assert win.timeline() == []
    finally:
        win.close()


def test_the_pointer_uses_the_windows_the_pet_already_tracks(pet, monkeypatch):  # noqa: F811
    # 리눅스엔 창을 한 번에 열거해주는 백엔드가 없다 — 대신 펫이 퍼치·포커스를
    # 위해 이미 KWin 피드로 창 목록을 들고 있다. 포인터가 그걸 쓰면 된다.
    monkeypatch.setattr(P.sys, "platform", "linux")
    pet._on_geom("7;konsole;100,100,800,600;4242;Konsole")
    wins = pet._ask_windows()
    assert [w.title for w in wins] == ["konsole"]
    assert P.geom.window_at(200, 200, wins) is not None
