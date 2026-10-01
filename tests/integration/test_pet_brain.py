"""크리처 머리: 말 걸기를 본 세션 대신 크리처가 먼저 받는다.

진짜 `claude` 대신 PATH 앞에 둔 가짜 실행 파일로 머리를 흉내 낸다. 가짜는 진짜처럼
띄워 둔 채 stream-json 한 줄씩 받고 답한다 — 무엇을 답할지는 테스트가 정하고, 테스트는
펫이 *보여주는 것*(snapshot 의 말풍선)과 본 세션에 *남은 것*(아웃박스 쪽지)만 본다.
"""
import json
import os
import stat
import sys
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import pytest

from claudlet import pet as P
from claudlet.core import outbox

from harness import pet, send_hook  # noqa: F401  (`pet` used as a fixture)

pytestmark = pytest.mark.skipif(os.name == "nt", reason="가짜 실행 파일이 shebang 스크립트")


@pytest.fixture
def world(pet, tmp_path, monkeypatch):  # noqa: F811
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "cfg"))
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path / "run"))
    (tmp_path / "run").mkdir(exist_ok=True)
    (tmp_path / "bin").mkdir(exist_ok=True)
    monkeypatch.setenv("PATH", str(tmp_path / "bin") + os.pathsep + os.environ["PATH"])
    monkeypatch.setattr(pet, "_konsole_send", lambda t: False)   # 본 세션 = 쪽지
    yield tmp_path
    pet._brain_stop()
    outbox.drop(pet.session_id)


def _brain_on(tmp_path, on=True, chatty=False):
    from claudlet.core import petconfig
    with open(petconfig.config_path(), "w", encoding="utf-8") as f:
        json.dump({"pointer": {"brain": on, "brain_chatty": chatty}}, f)


_FAKE = """#!{py}
import json, re, sys, time
count = 0
for line in sys.stdin:
    msg = json.loads(line)["message"]["content"]
    count += 1
    with open({log!r}, "a", encoding="utf-8") as f:
        f.write(msg + "\\n<<END>>\\n")
    m = re.search(r"## The user says\\n(.*)", msg)
    user = m.group(1) if m else ""
{body}
    print(json.dumps({{"type": "result", "subtype": "success", "result": out}}), flush=True)
"""


def _fake_claude(tmp_path, body):
    """`body` 는 받은 말(msg, user, count)로 `out` 을 정하는 파이썬 몇 줄."""
    exe = tmp_path / "bin" / "claude"
    exe.write_text(_FAKE.format(py=sys.executable, log=str(tmp_path / "stdin.txt"),
                                body="\n".join("    " + l for l in body.splitlines())))
    exe.chmod(exe.stat().st_mode | stat.S_IEXEC)
    return exe


def _seen(tmp_path):
    """가짜 머리가 받은 말들."""
    p = tmp_path / "stdin.txt"
    return p.read_text(encoding="utf-8").split("\n<<END>>\n")[:-1] if p.exists() else []


def _wait(cond, secs=5.0):
    end = time.monotonic() + secs
    while time.monotonic() < end:
        P.QApplication.processEvents()
        if cond():
            return True
        time.sleep(0.02)
    return False


def _notes(pet):  # noqa: F811
    """본 세션에 넘어간 말 (말투 쪽지는 빼고)."""
    return [n["text"] for n in outbox.take(pet.session_id) if n.get("text")]


def test_small_talk_is_answered_by_the_creature_and_never_reaches_the_session(pet, world):  # noqa: F811
    _brain_on(world)
    _fake_claude(world, 'out = "SAY: 응 지금 테스트 돌리는 중~"')
    pet._talk(immediate=True, text="지금 뭐 해?")
    assert _wait(lambda: pet.snapshot()["saying"])
    assert pet.snapshot()["saying"] == "응 지금 테스트 돌리는 중~"
    assert _notes(pet) == []


def test_work_is_relayed_to_the_session(pet, world, monkeypatch):  # noqa: F811
    monkeypatch.setattr(pet, "session_id", "sess-1")      # 세션에 붙은 펫
    _brain_on(world)
    _fake_claude(world, 'out = "SAY: 알았어 전할게\\nRELAY: 로그인 테스트 고쳐줘"')
    pet._talk(immediate=True, text="로그인 테스트 좀 고쳐달라고 해줘")
    assert _wait(lambda: pet.snapshot()["saying"])
    assert pet.snapshot()["saying"] == "알았어 전할게"
    assert _notes(pet) == ["로그인 테스트 고쳐줘"]


def test_the_creature_sees_what_the_user_said(pet, world):  # noqa: F811
    _brain_on(world)
    _fake_claude(world, 'out = "SAY: 들었어"')
    pet._talk(immediate=True, text="오늘 점심 뭐 먹지")
    assert _wait(lambda: pet.snapshot()["saying"])
    assert "오늘 점심 뭐 먹지" in _seen(world)[0]


def test_a_failing_brain_hands_the_words_to_the_session(pet, world):  # noqa: F811
    _brain_on(world)
    _fake_claude(world, 'sys.exit(3)')
    pet._talk(immediate=True, text="들리나?")
    assert _wait(lambda: not pet._brain_busy())
    assert _notes(pet) == ["들리나?"]


def test_no_agent_cli_hands_the_words_to_the_session(pet, world, monkeypatch):  # noqa: F811
    _brain_on(world)
    monkeypatch.setattr(P.shutil, "which", lambda name: None)
    pet._talk(immediate=True, text="거기 있어?")
    assert _notes(pet) == ["거기 있어?"]


def test_a_hung_brain_times_out_to_the_session(pet, world, monkeypatch):  # noqa: F811
    _brain_on(world)
    monkeypatch.setattr(pet, "BRAIN_TIMEOUT_S", 0.3)
    _fake_claude(world, 'time.sleep(30)')
    pet._talk(immediate=True, text="왜 대답이 없어")
    assert _wait(lambda: not pet._brain_busy(), secs=5)
    assert _notes(pet) == ["왜 대답이 없어"]


def test_speaking_again_answers_both(pet, world):  # noqa: F811
    # 앞의 생각을 죽였더니 앞의 말이 답도 못 받고 본 세션에도 안 가서 사라졌다.
    from claudlet.core import history as H
    _brain_on(world)
    _fake_claude(world, 'time.sleep(0.2)\nout = "SAY: " + user + " 들었어"')
    pet._talk(immediate=True, text="첫번째")
    pet._talk(immediate=True, text="두번째")
    assert _wait(lambda: not pet._brain_busy())
    got = {r["question"]: r["answer"] for r in H.load(pet.session_id)}
    assert got == {"첫번째": "첫번째 들었어", "두번째": "두번째 들었어"}


def test_the_sessions_own_reply_does_not_take_the_creatures_question(pet, world):  # noqa: F811
    # 크리처가 생각하는 동안 본 세션이 자기 턴을 끝내도, 그 답이 크리처에게 한
    # 질문에 붙거나 말풍선으로 뜨면 안 된다.
    from claudlet.core import history as H
    _brain_on(world)
    _fake_claude(world, 'time.sleep(0.3)\nout = "SAY: 내 답"')
    pet._talk(immediate=True, text="안녕")
    assert H.load(pet.session_id, pending_only=True) == []   # 본 세션 몫이 아니다
    H.record_answer(pet.session_id, "본 세션이 한 말")         # turn_end 가 하는 일
    assert _wait(lambda: not pet._brain_busy())
    mine = [r for r in H.load(pet.session_id) if r["question"] == "안녕"]
    assert mine and mine[0]["answer"] == "내 답"


def test_a_failed_brain_question_waits_for_the_sessions_answer(pet, world):  # noqa: F811
    from claudlet.core import history as H
    _brain_on(world)
    _fake_claude(world, 'sys.exit(1)')
    pet._talk(immediate=True, text="넘어가라")
    assert _wait(lambda: not pet._brain_busy())
    assert [r["question"] for r in H.load(pet.session_id, pending_only=True)] == ["넘어가라"]


def test_a_blank_answer_hands_the_words_to_the_session(pet, world):  # noqa: F811
    _brain_on(world)
    _fake_claude(world, 'out = "SAY:"')
    pet._talk(immediate=True, text="뭐라고?")
    assert _wait(lambda: not pet._brain_busy())
    assert _notes(pet) == ["뭐라고?"]


def test_brain_off_keeps_the_old_path(pet, world):  # noqa: F811
    _brain_on(world, on=False)
    _fake_claude(world, 'out = "SAY: 나오면 안 됨"')
    pet._talk(immediate=True, text="그냥 세션에")
    assert _notes(pet) == ["그냥 세션에"]


def test_a_note_skips_the_brain(pet, world):  # noqa: F811
    _brain_on(world)
    _fake_claude(world, 'out = "SAY: 나오면 안 됨"')
    pet._talk(immediate=False, text="나중에 봐")
    assert _notes(pet) == ["나중에 봐"]
    assert not pet._brain_busy()


def test_pointing_at_a_window_asks_the_creature_with_what_it_reads(pet, world, monkeypatch):  # noqa: F811
    from claudlet.platform.geom import Win
    _brain_on(world)
    _fake_claude(world, 'out = "SAY: 그건 원장 창이야"')
    monkeypatch.setattr(pet, "_ask_backend", lambda: None)
    pet.ask_window(Win(wid=1, x=100, y=100, w=400, h=300, title="Ledger", pid=7,
                       caption="ledger"), "이거 뭐야?")
    assert _wait(lambda: pet.snapshot()["saying"])
    assert pet.snapshot()["saying"] == "그건 원장 창이야"
    assert "Ledger" in _seen(world)[0] and "이거 뭐야?" in _seen(world)[0]
    assert _notes(pet) == []


def test_a_failed_pointer_question_still_carries_the_window(pet, world, monkeypatch):  # noqa: F811
    from claudlet.platform.geom import Win
    _brain_on(world)
    _fake_claude(world, 'sys.exit(1)')
    monkeypatch.setattr(pet, "_ask_backend", lambda: None)
    pet.ask_window(Win(wid=1, x=100, y=100, w=400, h=300, title="Ledger", pid=7,
                       caption="ledger"), "이거 뭐야?")
    assert _wait(lambda: not pet._brain_busy())
    notes = _notes(pet)
    assert notes and "Ledger" in notes[0] and "이거 뭐야?" in notes[0]


def _point_with_shot(pet, monkeypatch, question="이거 뭐야?"):
    from claudlet.core import shot as shotmod
    from claudlet.platform.geom import Win
    monkeypatch.setattr(pet, "_ask_backend", lambda: None)
    monkeypatch.setattr(shotmod, "save", lambda sid, png: "/tmp/shot-1.png")
    pet._ask_shot = b"PNG"
    pet.ask_window(Win(wid=1, x=100, y=100, w=400, h=300, title="Ledger", pid=7,
                       caption="ledger"), question)


def test_a_captured_pointer_question_still_goes_to_the_creature_first(pet, world, monkeypatch):  # noqa: F811
    # 캡처를 켜 둔 윈도우에서 포인터가 머리를 한 번도 안 거쳤다(실사용).
    _brain_on(world)
    _fake_claude(world, 'out = "SAY: 그건 원장 창이야"')
    _point_with_shot(pet, monkeypatch)
    assert _wait(lambda: pet.snapshot()["saying"])
    assert pet.snapshot()["saying"] == "그건 원장 창이야"
    assert "cannot see images" in _seen(world)[0]
    assert _notes(pet) == []


def test_a_relayed_pointer_question_carries_the_window_and_the_shot(pet, world, monkeypatch):  # noqa: F811
    monkeypatch.setattr(pet, "session_id", "sess-1")
    _brain_on(world)
    _fake_claude(world, 'out = "SAY: 잠깐, 볼게\\nRELAY: 이 창 그림 설명해줘"')
    _point_with_shot(pet, monkeypatch, "이 그림 뭐야?")
    assert _wait(lambda: pet.snapshot()["saying"] == "잠깐, 볼게")
    notes = _notes(pet)
    assert len(notes) == 1
    assert "Ledger" in notes[0] and "/tmp/shot-1.png" in notes[0]
    assert "이 창 그림 설명해줘" in notes[0]


def test_a_standalone_pet_answers_but_has_nowhere_to_relay(pet, world):  # noqa: F811
    # 세션 없이 뜬 펫: 크리처가 답은 하지만, 넘길 세션이 없으니 쪽지로 물지 않는다
    assert pet._standalone()
    _brain_on(world)
    _fake_claude(world, 'out = "SAY: 넘길 데가 없네\\nRELAY: 고쳐줘"')
    pet._talk(immediate=True, text="이거 고쳐줘")
    assert _wait(lambda: pet.snapshot()["saying"])
    assert pet.snapshot()["saying"] == "넘길 데가 없네"
    assert _notes(pet) == []
    assert "standalone" in _seen(world)[0]


# --- 띄워 둔 머리 ---------------------------------------------------------------

def test_the_brain_stays_up_between_messages(pet, world):  # noqa: F811
    # 매번 새로 띄우면 4~6초였다. 한 프로세스가 계속 듣고, 지시는 처음에 한 번만 간다.
    _brain_on(world)
    _fake_claude(world, 'out = "SAY: %d번째" % count')
    pet._talk(immediate=True, text="하나")
    assert _wait(lambda: pet.snapshot()["saying"] == "1번째")
    pet._talk(immediate=True, text="둘")
    assert _wait(lambda: pet.snapshot()["saying"] == "2번째")
    first, second = _seen(world)
    assert "# Instructions" in first and "# Instructions" not in second
    assert "둘" in second


def test_a_brain_that_dies_is_brought_back_fresh(pet, world):  # noqa: F811
    _brain_on(world)
    _fake_claude(world, 'if user == "죽어":\n    sys.exit(1)\nout = "SAY: " + user')
    pet._talk(immediate=True, text="안녕")
    assert _wait(lambda: pet.snapshot()["saying"] == "안녕")
    pet._talk(immediate=True, text="죽어")
    assert _wait(lambda: not pet._brain_busy())
    assert _notes(pet) == ["죽어"]                       # 죽은 머리가 삼킨 말은 세션으로
    pet._talk(immediate=True, text="살아났니")
    assert _wait(lambda: pet.snapshot()["saying"] == "살아났니")
    assert "# Instructions" in _seen(world)[-1]          # 새 머리는 처음부터 다시 배운다


def test_the_creature_can_say_more_than_one_line(pet, world, monkeypatch):  # noqa: F811
    from claudlet.core import history as H
    _brain_on(world)
    monkeypatch.setattr(pet, "BRAIN_SAY_GAP_MS", 100)
    _fake_claude(world, 'out = "SAY: 하나\\nSAY: 둘"')
    pet._talk(immediate=True, text="말해봐")
    assert _wait(lambda: pet.snapshot()["saying"] == "하나")
    assert _wait(lambda: pet.snapshot()["saying"] == "둘")
    answers = [r["answer"] for r in H.load(pet.session_id)]
    assert "하나" in answers and "둘" in answers
    assert [r["answer"] for r in H.load(pet.session_id) if r["question"] == "말해봐"] == ["하나"]


def test_a_relayed_turn_does_not_wipe_what_the_creature_just_said(pet, world, monkeypatch):  # noqa: F811
    monkeypatch.setattr(pet, "session_id", "sess-1")
    _brain_on(world)
    _fake_claude(world, 'out = "SAY: 알았어 전할게\\nRELAY: 빌드 돌려줘"')
    pet._talk(immediate=True, text="빌드 돌려달라고 해")
    assert _wait(lambda: pet.snapshot()["saying"] == "알았어 전할게")
    send_hook(pet, "UserPromptSubmit", session="sess-1")   # 넘긴 일로 본 세션 턴이 시작됐다
    assert _wait(lambda: False, secs=0.3) is False
    assert pet.snapshot()["saying"] == "알았어 전할게"


# --- 먼저 말 걸기 --------------------------------------------------------------

def test_the_creature_speaks_up_when_the_session_finishes(pet, world, monkeypatch):  # noqa: F811
    monkeypatch.setattr(pet, "session_id", "sess-1")
    _brain_on(world, chatty=True)
    _fake_claude(world, 'out = "SAY: 수고했어~"')
    send_hook(pet, "Stop", session="sess-1")
    assert _wait(lambda: pet.snapshot()["saying"] == "수고했어~")
    assert "## Event" in _seen(world)[0]


def test_speaking_up_is_rare(pet, world, monkeypatch):  # noqa: F811
    monkeypatch.setattr(pet, "session_id", "sess-1")
    _brain_on(world, chatty=True)
    _fake_claude(world, 'out = "SKIP"')
    send_hook(pet, "Stop", session="sess-1")
    assert _wait(lambda: len(_seen(world)) == 1 and not pet._brain_busy())
    send_hook(pet, "StopFailure", session="sess-1")
    _wait(lambda: False, secs=0.3)
    assert len(_seen(world)) == 1                        # 간격 안이라 또 부르지 않았다
    assert pet.snapshot()["saying"] == ""                # SKIP 이면 아무 말 안 한다
    assert _notes(pet) == []


def test_no_speaking_up_unless_switched_on(pet, world, monkeypatch):  # noqa: F811
    monkeypatch.setattr(pet, "session_id", "sess-1")
    _brain_on(world, chatty=False)
    _fake_claude(world, 'out = "SAY: 나오면 안 됨"')
    send_hook(pet, "Stop", session="sess-1")
    _wait(lambda: False, secs=0.3)
    assert _seen(world) == []



def test_a_relay_is_never_typed_into_the_prompt(pet, world, monkeypatch):  # noqa: F811
    # 쳐 넣었더니 사용자 말이 존댓말로 바뀌어 터미널에 다시 찍혔다 — 쪽지로만 간다.
    monkeypatch.setattr(pet, "session_id", "sess-1")
    typed = []
    monkeypatch.setattr(pet, "_konsole_send", lambda t: typed.append(t) or True)
    _brain_on(world)
    _fake_claude(world, 'out = "SAY: 전할게\\nRELAY: 빌드 돌려줘"')
    pet._talk(immediate=True, text="빌드 돌려달라고 해")
    assert _wait(lambda: pet.snapshot()["saying"] == "전할게")
    assert typed == []
    assert outbox.wants_wake(pet.session_id)
    assert _notes(pet) == ["빌드 돌려줘"]


# --- codex: 띄워 둔 app-server ---------------------------------------------------

_FAKE_CODEX = """#!{py}
import json, re, sys
turns = 0
def out(m):
    print(json.dumps(m), flush=True)
for line in sys.stdin:
    m = json.loads(line)
    meth = m.get("method")
    if meth == "initialize":
        out({{"id": m["id"], "result": {{"userAgent": "fake"}}}})
    elif meth == "thread/start":
        out({{"id": m["id"], "result": {{"thread": {{"id": "t1"}}}}}})
    elif meth == "turn/start":
        turns += 1
        msg = m["params"]["input"][0]["text"]
        with open({log!r}, "a", encoding="utf-8") as f:
            f.write(msg + "\\n<<END>>\\n")
        mm = re.search(r"## The user says\\n(.*)", msg)
        user = mm.group(1) if mm else ""
        out({{"id": m["id"], "result": {{}}}})
{body}
"""


def _fake_codex(tmp_path, body):
    """`body` 는 턴마다(turns, user) 무엇을 내보낼지 정하는 파이썬 몇 줄 (out(...) 호출)."""
    exe = tmp_path / "bin" / "codex"
    exe.write_text(_FAKE_CODEX.format(py=sys.executable, log=str(tmp_path / "stdin.txt"),
                                      body="\n".join("        " + l for l in body.splitlines())))
    exe.chmod(exe.stat().st_mode | stat.S_IEXEC)


_SAY = ('out({"method": "item/completed", "params": {"item": {"type": "agentMessage", '
        '"text": "SAY: %d번째 " % turns + user}}})\n'
        'out({"method": "turn/completed", "params": {"turn": {"status": "completed"}}})')


def test_codex_creature_stays_up_and_answers_in_order(pet, world, monkeypatch):  # noqa: F811
    monkeypatch.setattr(pet, "agent", "codex")
    _brain_on(world)
    _fake_codex(world, _SAY)
    pet._talk(immediate=True, text="하나")
    pet._talk(immediate=True, text="둘")        # 첫 턴이 도는 중 — 줄을 서야 한다
    assert _wait(lambda: not pet._brain_busy())
    from claudlet.core import history as H
    got = {r["question"]: r["answer"] for r in H.load(pet.session_id)}
    assert got == {"하나": "1번째 하나", "둘": "2번째 둘"}   # 한 서버, 차례대로
    first, second = _seen(world)
    assert "# Instructions" in first and "# Instructions" not in second


def test_a_failed_codex_turn_goes_to_the_session(pet, world, monkeypatch):  # noqa: F811
    monkeypatch.setattr(pet, "agent", "codex")
    _brain_on(world)
    _fake_codex(world, 'out({"method": "turn/completed", "params": {"turn": {"status": "failed"}}})')
    pet._talk(immediate=True, text="안 되면 세션으로")
    assert _wait(lambda: not pet._brain_busy())
    assert _notes(pet) == ["안 되면 세션으로"]
