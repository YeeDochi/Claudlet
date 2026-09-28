"""리눅스 fcitx 사용자에게 한글이 쳐지는 Qt 로 펫을 다시 띄운다.

pip/pipx 로 깔린 PyQt6 는 자기 Qt 를 안고 오는데, 그 안의 입력컨텍스트는
compose 와 ibus 뿐이다. fcitx 사용자는 우리 창의 입력칸에 한글을 한 글자도
못 친다(fcitx5 의 ibus 호환으로 우회해도 안 됐다 — 실측). 시스템 fcitx5
플러그인은 Qt private API 를 쓰므로 버전이 다른 wheel Qt 에는 끼울 수 없다.

배포판 PyQt6(python3-pyqt6)는 시스템 Qt 위에 있어서 그 플러그인이 그대로
붙는다. 그래서 그것이 있으면 펫을 시스템 파이썬으로 다시 띄운다. 판단은
순수 함수로, exec 는 얇게.
"""
import os
import subprocess
import sys

FCITX_PLUGIN = "libfcitx5platforminputcontextplugin.so"
SYSTEM_PYTHON = "/usr/bin/python3"
MARK = "CLAUDLET_SYSTEM_QT"        # 다시 띄운 쪽에 선다 — 두 번 돌지 않게

# 시스템 파이썬에 물어볼 한 줄: 그 PyQt6 의 플러그인 디렉터리.
_PROBE = ("from PyQt6.QtCore import QLibraryInfo as L;"
          "print(L.path(L.LibraryPath.PluginsPath))")


def has_fcitx(plugins_dir, listdir=os.listdir):
    """이 Qt 플러그인 디렉터리에 fcitx 입력컨텍스트가 있나. 순수(listdir 주입)."""
    try:
        return FCITX_PLUGIN in listdir(
            os.path.join(plugins_dir, "platforminputcontexts"))
    except OSError:
        return False


def should_switch(platform, xmodifiers, ours, theirs):
    """시스템 Qt 로 갈아탈까. 순수.

    fcitx 를 쓰는 리눅스이고, 우리 Qt 엔 플러그인이 없는데 시스템 쪽엔 있을
    때만. (venv 파이썬은 시스템 파이썬의 심볼릭 링크라 실행 파일로는 둘을
    못 가른다 — 가르는 것은 어느 PyQt6 가 올라왔느냐다.)"""
    return (platform.startswith("linux")
            and "fcitx" in (xmodifiers or "")
            and not ours and theirs)


def _system_plugins(python=SYSTEM_PYTHON):
    """시스템 PyQt6 의 플러그인 디렉터리, 없으면 None."""
    if not os.path.exists(python):
        return None
    try:
        out = subprocess.run([python, "-I", "-c", _PROBE], capture_output=True,
                             text=True, timeout=5)
    except Exception:
        return None
    return out.stdout.strip() if out.returncode == 0 else None


def maybe_reexec(argv=None):
    """필요하면 시스템 파이썬으로 이 펫을 다시 띄운다(돌아오지 않는다).

    venv 의 site-packages 를 그대로 PYTHONPATH 에 얹으면 거기 든 wheel PyQt6
    가 또 이긴다. 그래서 claudlet 패키지 하나만 가리키는 링크 디렉터리를
    만들어 그것만 얹는다. 실패는 전부 삼키고 원래 Qt 로 계속 간다."""
    if os.environ.pop(MARK, None):
        # 갈아탄 쪽이다. 경로는 이미 sys.path 에 들어갔으니 환경에서는 걷어낸다
        # — 펫이 띄우는 셸·세션에 우리 PYTHONPATH 가 새어 들어가면 안 된다.
        os.environ.pop("PYTHONPATH", None)
        return
    # 링크 디렉터리는 남이 못 건드리는 곳이어야 한다: 공용 /tmp 에 두면 다른
    # 사용자가 미리 만든 `claudlet` 을 우리가 실행하게 된다.
    runtime = os.environ.get("XDG_RUNTIME_DIR")
    if not runtime or not os.path.isdir(runtime):
        return
    try:
        from PyQt6.QtCore import QLibraryInfo as L
        ours = has_fcitx(L.path(L.LibraryPath.PluginsPath))
        if ours:
            return
        theirs_dir = _system_plugins()
        if not should_switch(sys.platform, os.environ.get("XMODIFIERS"), ours,
                             bool(theirs_dir) and has_fcitx(theirs_dir)):
            return
        pkg = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        link_dir = os.path.join(runtime, "claudlet-sysqt")
        os.makedirs(link_dir, exist_ok=True)
        link = os.path.join(link_dir, "claudlet")
        if os.path.realpath(link) != os.path.realpath(pkg):
            if os.path.lexists(link):
                os.unlink(link)
            os.symlink(pkg, link)
        env = dict(os.environ)
        env[MARK] = "1"
        env["PYTHONPATH"] = link_dir
        args = sys.argv[1:] if argv is None else argv
        # -s: 사용자 site(~/.local)에 pip 로 깐 PyQt6 가 있어도 그것을 건너뛴다
        os.execve(SYSTEM_PYTHON, [SYSTEM_PYTHON, "-s", "-m", "claudlet", *args],
                  env)
    except Exception:
        return
