"""크리처 머리가 생각하는 동안 대화창에 "•••" 이 뜬다.

진짜 머리 대신, 답을 테스트가 내줄 때까지 붙잡고 있는 가짜 머리를 끼운다 — 펫 쪽
코드는 진짜 그대로 돌고, 테스트는 대화창에 *보이는 것*만 본다. 가짜 실행 파일이 필요
없어 윈도우에서도 돈다.
"""
import json
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import pytest
from PyQt6.QtCore import QObject, pyqtSignal

from claudlet import brainproc

from harness import pet  # noqa: F401  (`pet` used as a fixture)

DOTS = "•••"


class _HeldBrain(QObject):
    """말을 받아 두기만 한다. 테스트가 `reply()` 로 답을 내준다."""
    answered = pyqtSignal(object, object)
    failed = pyqtSignal(object)

    def __init__(self, *_a, **_k):
        super().__init__()
        self.timeout_s = 60
        self.held = []

    def busy(self):
        return bool(self.held)

    def pending(self):
        return list(self.held)

    def ask(self, token, compose):
        self.held.append(token)

    def stop(self):
        pass

    def reply(self, says, relay=None):
        token = self.held.pop(0)
        self.answered.emit(token, {"says": says, "relay": relay})

    def fail(self):
        self.failed.emit(self.held.pop(0))


@pytest.fixture
def held(pet, tmp_path, monkeypatch):  # noqa: F811
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    from claudlet.core import petconfig
    os.makedirs(os.path.dirname(petconfig.config_path()), exist_ok=True)
    with open(petconfig.config_path(), "w", encoding="utf-8") as f:
        json.dump({"pointer": {"brain": True}}, f)
    monkeypatch.setattr(brainproc, "CreatureBrain", _HeldBrain)
    monkeypatch.setattr("shutil.which", lambda name: "/bin/" + name)
    monkeypatch.setattr(pet, "_konsole_send", lambda t: False)
    win = pet.show_history()
    yield win
    win.close()
    pet._brain = None


def _dots(win):
    return win.html().count(DOTS)


def test_dots_show_while_the_creature_thinks_and_go_with_its_answer(pet, held):  # noqa: F811
    pet._talk(immediate=True, text="안녕")
    assert _dots(held) == 1
    assert "답을 기다리는 중" not in held.html()
    pet._brain.reply(["응 안녕~"])
    assert _dots(held) == 0
    assert "응 안녕~" in held.html()


def test_dots_stay_while_more_lines_are_coming(pet, held):  # noqa: F811
    pet._talk(immediate=True, text="뭐해")
    pet._brain.reply(["하나", "둘"])
    assert "하나" in held.html()
    assert _dots(held) == 1                   # 둘째 줄이 아직 남았다


def test_a_failed_brain_drops_the_dots_and_waits_for_the_session(pet, held):  # noqa: F811
    pet._talk(immediate=True, text="빌드 돌려줘")
    pet._brain.fail()
    assert _dots(held) == 0
    assert "답을 기다리는 중" in held.html()


def test_speaking_up_on_its_own_shows_no_dots(pet, held):  # noqa: F811
    # 먼저 말 걸기는 SKIP 이 흔하다 — 떴다가 말없이 사라지면 안 된다
    pet._brain_link().ask({"kind": "event"}, lambda first: "")
    held.refresh()
    assert _dots(held) == 0
