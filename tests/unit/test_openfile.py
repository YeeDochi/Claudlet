"""IDE 창은 '무엇을 열어놨는지' 를 제목으로 말한다.

에디터 본문은 접근성 트리에 안 나온다 — IntelliJ 를 깊이 30까지 1243 노드
훑어도 텍스트 인터페이스가 하나도 없었다(실측). 그렇다고 DLL 을 붙이고 픽셀을
긁는 건 과한 길이다: 에이전트는 파일을 디스크에서 직접 읽으면 되고, 어떤 파일인지는
창 제목에 이미 적혀 있다.
"""
from claudlet.core import inspect as I
from claudlet.platform.geom import Win


def _win(title, caption=""):
    return Win("1", 0, 0, 800, 600, title, 4242, caption)


def test_intellij_tells_project_and_file():
    got = I.open_file(_win("jetbrains-idea", "openstackit-java – AuthService.java"))
    assert got == {"project": "openstackit-java", "file": "AuthService.java"}


def test_intellij_with_a_plain_hyphen_too():
    # 제목의 구분자가 en dash 일 때도 하이픈일 때도 있다.
    got = I.open_file(_win("jetbrains-idea", "myproj - Main.kt"))
    assert got["file"] == "Main.kt"


def test_the_idle_ide_window_has_no_file():
    # "project - IntelliJ IDEA" 는 열린 파일이 아니라 앱 이름이다.
    assert I.open_file(_win("jetbrains-idea", "openstackit-java - IntelliJ IDEA")) is None


def test_vscode_puts_the_file_first():
    got = I.open_file(_win("code", "outbox.py - claudlet - Visual Studio Code"))
    assert got == {"project": "claudlet", "file": "outbox.py"}


def test_a_terminal_is_not_an_ide():
    # 터미널은 화면 글자가 그대로 읽히므로 이 추측이 끼어들 이유가 없다.
    assert I.open_file(_win("konsole", "claude-pet : claude — Konsole")) is None


def test_the_prompt_says_to_read_the_file_from_disk():
    ctx = I.build_context(
        _win("jetbrains-idea", "openstackit-java – AuthService.java"), "이거 뭐야?")
    out = I.render_prompt(ctx)
    assert "AuthService.java" in out
    assert "openstackit-java" in out
    assert "직접" in out or "열어" in out          # 디스크에서 읽으라는 안내


def test_a_window_with_readable_text_does_not_get_the_hint():
    # 글자가 읽히면 추측할 필요가 없다.
    ctx = I.build_context(_win("konsole", "Konsole"), "뭐야?",
                          read_text=lambda w: ["실제 화면 글자"])
    assert "실제 화면 글자" in I.render_prompt(ctx)
