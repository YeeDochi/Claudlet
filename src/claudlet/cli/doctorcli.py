#!/usr/bin/env python3
"""`claudlet-doctor` — 무엇이 꺼져 있어서 무엇이 안 되는지 알려준다.

    claudlet-doctor            점검 결과를 사람이 읽게 출력
    claudlet-doctor --quiet    문제가 있을 때만 출력 (설치 끝에 붙인다)

바깥을 찔러보는 일만 여기서 한다. 판정과 문구는 `core/doctor.py` 에 있고 순수하다.
각 점검은 **실패해도 점검 전체를 죽이지 않는다** — 진단 도구가 진단하다 죽으면
고치려던 것보다 나쁘다.
"""
import os
import shutil
import subprocess
import sys

from claudlet.cli import utf8_output
from claudlet.core import agents, doctor, petconfig


def _out(text, out=None):
    (out or sys.stdout).write(text)


def _probe(fn, default=(False, "")):
    try:
        return fn()
    except Exception as e:
        return (False, str(e)[:80])


# ---------- 개별 점검 (얇은 IO) ----------

def check_hooks():
    """이 에이전트의 훅이 등록돼 있나. 펫이 반응하는 모든 것의 전제."""
    import json
    for name in agents.detected() or [agents.DEFAULT]:
        spec = agents.get(name)
        path = os.path.join(os.path.expanduser("~"), spec["settings"])
        try:
            with open(path, encoding="utf-8") as f:
                if "claudlet-hook" in f.read():
                    return True, name
        except OSError:
            continue
        except json.JSONDecodeError:
            continue
    return False, ""


def check_konsole_send(ancestor_pids=None):
    """Konsole 이 sendText 를 받아주나 (즉시 전송의 전제)."""
    if not sys.platform.startswith("linux"):
        return None, ""                      # 이 OS 에는 해당 없음
    from claudlet.platform import konsole
    from claudlet.platform.qdbus import qdbus_bin
    if not shutil.which(qdbus_bin()):
        return False, "qdbus 없음"

    def run(*args):
        return subprocess.check_output([qdbus_bin(), *args], text=True,
                                       timeout=3, stderr=subprocess.DEVNULL)

    pids = ancestor_pids or _konsole_pids(run)
    if not pids:
        return None, ""                      # Konsole 호스트가 아니다
    return konsole.can_send_text(pids, run), ""


def _konsole_pids(run):
    """지금 떠 있는 Konsole 들의 pid — 이 기계에 Konsole 이 있는지 보려는 것뿐."""
    try:
        names = [s.strip() for s in run().splitlines() if "konsole-" in s]
    except Exception:
        return set()
    out = set()
    for name in names:
        try:
            out.add(int(name.rsplit("-", 1)[1]))
        except (IndexError, ValueError):
            continue
    return out


def check_input_dialog():
    """한글이 써지는 입력창이 있나 (pip Qt 대화상자에는 입력기가 없다)."""
    if not sys.platform.startswith("linux"):
        return None, ""
    for exe in ("kdialog", "zenity"):
        if shutil.which(exe):
            return True, exe
    return False, ""


def check_atspi_daemon():
    if not sys.platform.startswith("linux"):
        return None, ""
    try:
        out = subprocess.run(["pgrep", "-f", "at-spi2-registryd"],
                             capture_output=True, timeout=3)
        return out.returncode == 0, ""
    except Exception:
        return False, "확인 실패"


def check_atspi_gi():
    """접근성 트리를 읽을 파이썬 바인딩이 있나.

    펫은 pipx venv 에서 도는데 거기엔 시스템 `gi` 가 없다. 그래서 읽기는 시스템
    파이썬 자식 프로세스로 하고, 여기서도 같은 것을 확인한다."""
    if not sys.platform.startswith("linux"):
        return None, ""
    for exe in ("/usr/bin/python3", "python3"):
        path = shutil.which(exe) or (exe if os.path.exists(exe) else None)
        if not path:
            continue
        try:
            r = subprocess.run(
                [path, "-c", "import gi; gi.require_version('Atspi','2.0');"
                             " from gi.repository import Atspi"],
                capture_output=True, timeout=10)
            if r.returncode == 0:
                return True, path
        except Exception:
            continue
    return False, ""


def check_atspi_toolkit():
    """툴킷 접근성 스위치. 꺼져 있으면 Qt·GTK 앱이 트리를 아예 안 내놓는다."""
    if not sys.platform.startswith("linux"):
        return None, ""
    try:
        r = subprocess.run(
            ["busctl", "--user", "get-property", "org.a11y.Bus",
             "/org/a11y/bus", "org.a11y.Status", "IsEnabled"],
            capture_output=True, text=True, timeout=5)
        return "true" in r.stdout.lower(), r.stdout.strip()
    except Exception:
        return False, "확인 실패"


def check_java_bridge():
    """자바 앱이 글자를 내놓게 하는 스위치 (리눅스 ATK wrapper / 윈도우 JAB)."""
    path = os.path.join(os.path.expanduser("~"), ".accessibility.properties")
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            body = f.read()
    except OSError:
        return False, "~/.accessibility.properties 없음"
    return ("assistive_technologies" in body), ""


def check_uia():
    if os.name != "nt":
        return None, ""
    return bool(shutil.which("powershell")), ""


def check_ax_trusted():
    if sys.platform != "darwin":
        return None, ""
    try:
        from claudlet.platform import axtree
        return bool(axtree.trusted()), ""
    except Exception as e:
        return False, str(e)[:60]


ORDER = [
    ("hooks", check_hooks),
    ("konsole_send", check_konsole_send),
    ("input_dialog", check_input_dialog),
    ("atspi_daemon", check_atspi_daemon),
    ("atspi_gi", check_atspi_gi),
    ("atspi_toolkit", check_atspi_toolkit),
    ("java_bridge", check_java_bridge),
    ("uia", check_uia),
    ("ax_trusted", check_ax_trusted),
]


def gather(order=None):
    """(id, ok, detail) 목록. 이 OS 에 해당 없는 점검(None)은 빠진다."""
    facts = []
    for fid, fn in (order or ORDER):
        ok, detail = _probe(fn)
        if ok is None:
            continue
        facts.append((fid, bool(ok), detail))
    return facts


def main(argv=None, out=None):
    utf8_output()
    argv = list(sys.argv[1:] if argv is None else argv)
    quiet = "--quiet" in argv
    lang = petconfig.resolve_lang((petconfig.load_config() or {}).get("lang"))
    facts = gather()
    if quiet and not doctor.problems(facts):
        return 0
    _out(doctor.render(facts, lang), out)
    return 1 if doctor.problems(facts) else 0


def _cli():
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        sys.exit(130)


if __name__ == "__main__":
    _cli()
