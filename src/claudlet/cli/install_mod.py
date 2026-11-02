"""claudlet mod 설치·제거 — `claude plugin` CLI 에 맡긴다.

패키지 안의 mod 폴더를 그대로 로컬 마켓플레이스로 등록하고 설치한다. 폴더
마켓플레이스는 복사본이 아니라 그 폴더를 읽으므로, pip 로 claudlet 을 업데이트하면
mod 도 같이 바뀐다(세션은 `/reload-plugins` 나 재시작 뒤에).

mod 는 덤이다. `claude` 가 없거나 너무 옛 버전이면 건너뛰고, 펫은 옛 길(직접 치기·
깨우기)로 말한다.
"""
import os
import shutil
import subprocess

MOD_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "mod")
NAME = "claudlet"                 # plugin.json 과 marketplace.json 의 name
PLUGIN = "{0}@{0}".format(NAME)


def _run(argv):
    try:
        out = subprocess.run(argv, capture_output=True, text=True, timeout=120)
    except (OSError, subprocess.SubprocessError) as e:
        return False, str(e)
    return out.returncode == 0, (out.stderr or out.stdout).strip()


def _last(msg):
    lines = (msg or "").splitlines()
    return lines[-1] if lines else ""


def install(claude=None):
    """(설치됐나, 한 줄 설명)."""
    claude = claude or shutil.which("claude")
    if not claude:
        return False, "claude CLI not found — pet uses the hook paths instead"
    if not os.path.isfile(os.path.join(MOD_DIR, ".claude-plugin", "plugin.json")):
        return False, "mod files missing from the package"
    ok, msg = _run([claude, "plugin", "marketplace", "add", MOD_DIR])
    if not ok and "already" not in msg.lower():
        return False, "marketplace add failed: " + _last(msg)
    ok, msg = _run([claude, "plugin", "install", PLUGIN, "--scope", "user"])
    if not ok and "already" not in msg.lower():
        return False, "install failed: " + _last(msg)
    return True, MOD_DIR


def remove(claude=None):
    claude = claude or shutil.which("claude")
    if not claude:
        return False, "claude CLI not found"
    _run([claude, "plugin", "uninstall", PLUGIN])
    ok, msg = _run([claude, "plugin", "marketplace", "remove", NAME])
    return ok, msg
