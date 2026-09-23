"""무엇이 꺼져 있어서 무엇이 안 되는지 말해준다.

이 프로젝트에서 되풀이해 물린 자리는 언제나 같은 모양이었다: 기능은 멀쩡한데
**바깥의 스위치 하나가 꺼져 있어** 조용히 아무 일도 안 일어나고, 사용자는 왜
그런지 알 방법이 없다. Konsole 의 DBus 스위치, pip Qt 의 입력컨텍스트, 리눅스
툴킷 접근성, 자바 Access Bridge — 전부 그랬다.

그래서 진단을 기능에 붙인다. 이 모듈은 **순수**하다: 바깥을 찔러보는 일은
`cli/doctorcli.py` 가 하고, 여기서는 그 결과(사실)를 받아 "무엇이 안 되는지"와
"어떻게 켜는지"로 옮긴다. 그래야 문구와 판정이 데스크톱 없이 테스트된다.

사실 하나는 `(id, ok, detail)` 이고, 이 모듈이 아는 것은 그 id 가 **어떤 기능을
막는가** 뿐이다.
"""
from collections import namedtuple

Check = namedtuple("Check", "id feature fix")

# id -> (그것이 없으면 못 하는 일, 켜는 법). 언어별 문구는 아래 TEXT 에 있다.
CHECKS = {
    "hooks": Check("hooks", "reactive", "install_hooks"),
    "skill": Check("skill", "slash_command", "reinstall_skill"),
    "konsole_send": Check("konsole_send", "ask_now", "konsole_switch"),
    "input_dialog": Check("input_dialog", "hangul_input", "install_kdialog"),
    "atspi_daemon": Check("atspi_daemon", "read_screen", "start_atspi"),
    "atspi_gi": Check("atspi_gi", "read_screen", "install_gi"),
    "atspi_toolkit": Check("atspi_toolkit", "read_screen", "enable_toolkit"),
    "java_bridge": Check("java_bridge", "read_java", "enable_java_bridge"),
    "uia": Check("uia", "read_screen", "need_powershell"),
    "ax_trusted": Check("ax_trusted", "read_screen", "grant_ax"),
}

TEXT = {
    "ko": {
        "title": "claudlet 점검",
        "all_ok": "전부 켜져 있습니다.",
        "ok": "정상",
        "off": "꺼짐",
        "affected": "안 되는 것",
        "offer": ("%(feature)s 를 하려면 설정을 하나 켜야 합니다.\n\n"
                  "  실행할 명령: %(run)s\n"
                  "  되돌리려면:  %(undo)s\n\n"
                  "켤까요?"),
        "howto": "켜는 법",
        "file_append": "%(path)s 에 `%(line)s` 한 줄 추가",
        "file_remove": "%(path)s 에서 그 한 줄 삭제",
        "feature": {
            "reactive": "펫이 에이전트 활동에 반응하기",
            "slash_command": "/claudlet 스킬 (띄우기·설정·크리처 만들기·점검)",
            "ask_now": "💬 지금 물어보기 (프롬프트에 바로 제출)",
            "hangul_input": "펫 입력창에 한글 치기",
            "read_screen": "🎯 포인터로 가리킨 창의 **글자** 읽기 (창 제목·크기는 읽힘)",
            "read_java": "자바 창(IntelliJ 등)의 글자 읽기",
        },
        "fix": {
            "install_hooks": "claudlet-install-hooks 를 실행한 뒤 세션을 다시 여세요.",
            "reinstall_skill": "스킬 링크가 끊어져 있습니다(설치 방식이 바뀌면"
                               " 생깁니다). claudlet-install 을 다시 실행하세요.",
            "konsole_switch": "Konsole 설정 → 일반 → '보안에 민감한 DBus API 활성화'"
                              " 를 켜세요 (창마다 따로 적용되니 이미 열려 있던 창은"
                              " 새로 여세요).",
            "install_kdialog": "kdialog 또는 zenity 를 설치하세요."
                               " 없으면 Qt 대화상자로 떨어지는데, pip 으로 깔린"
                               " PyQt6 에는 한글 입력기가 없습니다.",
            "start_atspi": "접근성 데몬(at-spi2)이 돌고 있지 않습니다."
                           " at-spi2-core 를 설치하고 로그인을 다시 하세요.",
            "install_gi": "sudo apt install python3-gi gir1.2-atspi-2.0",
            "enable_toolkit": "툴킷 접근성이 꺼져 있어 앱들이 트리를 내놓지 않습니다:"
                              " gsettings set org.gnome.desktop.interface"
                              " toolkit-accessibility true"
                              " (켜면 Qt·GTK 앱이 접근성 정보를 만들기 시작합니다).",
            "enable_java_bridge": "자바 앱이 글자를 내놓게 하려면 Access Bridge 를"
                                  " 켜야 합니다. 리눅스는 ~/.accessibility.properties 에"
                                  " assistive_technologies=org.GNOME.Accessibility.AtkWrapper"
                                  " 를, 윈도우는 jabswitch.exe -enable 을 쓰고,"
                                  " 그 뒤 해당 앱을 다시 켜세요.",
            "need_powershell": "PowerShell 을 찾을 수 없습니다 — UI Automation 읽기가"
                               " 그것을 통해 돕니다.",
            "grant_ax": "시스템 설정 → 개인정보 보호 및 보안 → 손쉬운 사용에서"
                        " 이 앱(터미널/claudlet)을 허용하세요.",
        },
    },
    "en": {
        "title": "claudlet check-up",
        "all_ok": "Everything is on.",
        "ok": "ok",
        "off": "off",
        "affected": "what stops working",
        "offer": ("%(feature)s needs one setting turned on.\n\n"
                  "  will run: %(run)s\n"
                  "  undo it:  %(undo)s\n\n"
                  "Turn it on?"),
        "howto": "how to turn it on",
        "file_append": "add the line `%(line)s` to %(path)s",
        "file_remove": "remove that line from %(path)s",
        "feature": {
            "reactive": "the pet reacting to agent activity",
            "slash_command": "the /claudlet skill (launch, configure, make a creature, check up)",
            "ask_now": "💬 Ask now (typed straight into the prompt)",
            "hangul_input": "typing non-ASCII into the pet's input box",
            "read_screen": "reading the **text** of the window you point at"
                           " (title and size still work)",
            "read_java": "reading text out of Java windows (IntelliJ and friends)",
        },
        "fix": {
            "install_hooks": "Run claudlet-install-hooks, then restart the session.",
            "reinstall_skill": "The skill link is dangling (this happens when the"
                               " install method changes). Run claudlet-install again.",
            "konsole_switch": "Konsole → Settings → General → 'Enable the security"
                              " sensitive parts of the DBus API'. It applies per"
                              " running Konsole, so reopen windows that were"
                              " already up.",
            "install_kdialog": "Install kdialog or zenity. Without one we fall back"
                               " to a Qt dialog, and pip-installed PyQt6 carries no"
                               " input-method plugin.",
            "start_atspi": "The accessibility daemon (at-spi2) is not running."
                           " Install at-spi2-core and log in again.",
            "install_gi": "sudo apt install python3-gi gir1.2-atspi-2.0",
            "enable_toolkit": "Toolkit accessibility is off, so apps publish no"
                              " tree: gsettings set org.gnome.desktop.interface"
                              " toolkit-accessibility true",
            "enable_java_bridge": "Java apps only publish text through Access"
                                  " Bridge. On Linux put"
                                  " assistive_technologies=org.GNOME.Accessibility.AtkWrapper"
                                  " in ~/.accessibility.properties; on Windows run"
                                  " jabswitch.exe -enable. Restart the app after.",
            "need_powershell": "PowerShell was not found — the UI Automation read"
                               " goes through it.",
            "grant_ax": "System Settings → Privacy & Security → Accessibility, and"
                        " allow this app (your terminal / claudlet).",
        },
    },
}


# 우리가 **켜줘도 되는 것**: 사용자 자기 설정이고, 되돌리기 쉽고, 관리자 권한이
# 필요 없는 것만. apt 설치(sudo)와 Konsole 의 보안 스위치는 뺐다 — 전자는 시스템을
# 건드리는 일이고, 후자는 "아무 프로세스나 내 터미널에 타이핑할 수 있게" 여는
# 스위치라 사용자가 직접 결정해야 한다.
JAVA_PROP = "assistive_technologies=org.GNOME.Accessibility.AtkWrapper"
_GS = ["gsettings", "set", "org.gnome.desktop.interface", "toolkit-accessibility"]

FIXES = {
    "atspi_toolkit": (_GS + ["true"], _GS + ["false"]),
    "java_bridge": (["__append__", "~/.accessibility.properties", JAVA_PROP],
                    ["__remove__", "~/.accessibility.properties", JAVA_PROP]),
    "hooks": (["claudlet-install-hooks"], ["claudlet-install-hooks", "--remove"]),
    "skill": (["claudlet-install"], ["claudlet-uninstall"]),
}


def fix_command(check_id):
    """이 항목을 켜는 명령, 우리가 켜면 안 되는 것이면 None. 순수."""
    pair = FIXES.get(check_id)
    return list(pair[0]) if pair else None


def undo_command(check_id):
    """되돌리는 명령. 켜주기 전에 이것을 같이 보여준다. 순수."""
    pair = FIXES.get(check_id)
    return list(pair[1]) if pair else None


def describe_command(cmd, lang="ko"):
    """실행할 일을 사람 말로. 순수.

    파일 한 줄을 더하고 빼는 것은 셸 명령이 아니라서 argv 를 그대로 보여주면
    `__append__` 같은 내부 표기가 사용자 눈에 나온다."""
    t = TEXT[lang_of(lang)]
    if not cmd:
        return ""
    if cmd[0] in ("__append__", "__remove__"):
        return t["file_" + cmd[0].strip("_")] % {"path": cmd[1], "line": cmd[2]}
    return " ".join(cmd)


def offer_text(check_id, lang="ko"):
    """켜도 되겠냐고 물을 때 보여줄 글. 실행할 명령을 숨기지 않는다. 순수."""
    t = TEXT[lang_of(lang)]
    check = CHECKS.get(check_id)
    if check is None or check_id not in FIXES:
        return ""
    run = describe_command(fix_command(check_id), lang)
    undo = describe_command(undo_command(check_id), lang)
    return t["offer"] % {"feature": t["feature"][check.feature],
                         "run": run, "undo": undo}


def lang_of(value):
    return "en" if str(value or "ko").startswith("en") else "ko"


def problems(facts):
    """켜져 있지 않은 것만 추린다. `facts` 는 (id, ok, detail) 의 나열. 순수."""
    out = []
    for fid, ok, detail in facts:
        if ok or fid not in CHECKS:
            continue
        out.append((CHECKS[fid], detail))
    return out


def blocked_features(facts):
    """지금 못 쓰는 기능 id 들, 중복 없이 순서대로. 순수."""
    seen = []
    for check, _detail in problems(facts):
        if check.feature not in seen:
            seen.append(check.feature)
    return seen


def render(facts, lang="ko"):
    """사람이 읽을 점검 결과. 순수 — 화면도 OS 도 필요 없다."""
    t = TEXT[lang_of(lang)]
    lines = [t["title"], "=" * len(t["title"]), ""]
    for fid, ok, detail in facts:
        mark = "  ✔ " if ok else "  ✘ "
        lines.append("%s%-16s %s%s" % (mark, fid, t["ok"] if ok else t["off"],
                                       (" — " + detail) if detail else ""))
    bad = problems(facts)
    if not bad:
        lines += ["", t["all_ok"]]
        return "\n".join(lines)
    lines.append("")
    for check, _detail in bad:
        lines += ["%s: %s" % (t["affected"], t["feature"][check.feature]),
                  "  %s: %s" % (t["howto"], t["fix"][check.fix]), ""]
    return "\n".join(lines).rstrip() + "\n"
