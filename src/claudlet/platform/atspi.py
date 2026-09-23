"""Read the on-screen text of a window through AT-SPI (Linux).

The Linux twin of `axtree.py` / `uiatree.py`, and deliberately the same four
function surface (`available` / `trusted` / `install_hint` / `read_window`) so
`core/inspect.py` never learns which OS it is on.

TWO THINGS MAKE THIS DIFFERENT FROM THE OTHER TWO

1. **The toolkit switch.** Qt and GTK publish nothing until accessibility is
   turned on for the session. With it off, the desktop showed 8 objects and
   Konsole was not among them; with it on, 23 objects and Konsole's terminal
   handed over 7869 characters. So "no text" here usually means "the switch is
   off", not "unreadable" -- `trusted()` reports that separately and
   `claudlet-doctor` offers to turn it on.

2. **We cannot import the binding.** The pet runs from a pipx venv, and
   `gi`/`Atspi` are system packages that are not in it. Rather than force a
   `--system-site-packages` install on everyone, the read happens in a short
   lived child process run by the SYSTEM python, which prints one prefixed line
   per string -- the same shape `uiatree.py` gets back from PowerShell, and for
   the same reason: the interesting part (which node, how deep, what to keep)
   stays pure and testable on a machine with no desktop at all.

Windows are matched by **pid**, never by title: two Konsole windows share a
title far too often, and the caller already knows the pid from `geom`.
"""
import os
import shutil
import subprocess
import sys

# Same caps as the other two backends, for the same reasons: a deep tree's tail
# is layout containers, and an unbounded read turns a question into a hang.
MAX_DEPTH = 12
MAX_NODES = 4000
TIMEOUT = 8.0

_PREFIX = "T:"

# The child. Kept as one string so the whole reader is visible in one place; it
# talks to the tree and prints, and decides nothing that is worth testing here.
READ_PY = r'''
import sys
try:
    import gi
    gi.require_version("Atspi", "2.0")
    from gi.repository import Atspi
except Exception:
    sys.exit(3)                       # binding missing -- caller says how to fix

WANT_PID = int(sys.argv[1])
MAX_DEPTH = int(sys.argv[2])
MAX_NODES = int(sys.argv[3])
PFX = sys.argv[4]

# 앱의 가구는 화면 내용이 아니다. 실측: Konsole 을 그냥 훑으면 메뉴 190여 줄이
# 먼저 나오고 정작 터미널 내용은 192번째 줄부터라, 상위 120줄만 싣는 쪽에서
# 통째로 잘렸다 — 메뉴만 질문에 실려 가는 셈이었다.
SKIP_ROLES = {"menu", "menu item", "menu bar", "tool bar", "separator",
              "check menu item", "radio menu item", "popup menu", "scroll bar"}

seen = [0]
out = []

def take(node, depth):
    if seen[0] >= MAX_NODES or depth > MAX_DEPTH:
        return
    seen[0] += 1
    try:
        if node.get_role_name() in SKIP_ROLES:
            return
    except Exception:
        pass
    try:
        name = node.get_name() or ""
    except Exception:
        name = ""
    text = ""
    try:
        n = Atspi.Text.get_character_count(node)
        if n:
            text = Atspi.Text.get_text(node, 0, min(n, 20000))
    except Exception:
        pass
    for chunk in (text, name):
        if chunk and chunk.strip():
            for line in chunk.splitlines():
                line = line.strip()
                if line:
                    out.append(line)
            break                     # 텍스트가 있으면 이름은 그 요약일 뿐이다
    try:
        count = node.get_child_count()
    except Exception:
        return
    for i in range(min(count, 60)):
        try:
            take(node.get_child_at_index(i), depth + 1)
        except Exception:
            pass

desktop = Atspi.get_desktop(0)
found = False
for i in range(desktop.get_child_count()):
    try:
        app = desktop.get_child_at_index(i)
        if app.get_process_id() != WANT_PID:
            continue
    except Exception:
        continue
    found = True
    take(app, 0)

if not found:
    sys.exit(4)                       # 그 pid 는 접근성 트리에 없다 (스위치/미지원)
for line in out:
    sys.stdout.write(PFX + line + "\n")
'''


def _system_python():
    """The interpreter that can `import gi`. The pet's own cannot."""
    for cand in ("/usr/bin/python3", "/usr/bin/python3.13", "python3"):
        path = cand if os.path.isabs(cand) and os.path.exists(cand) else shutil.which(cand)
        if path:
            return path
    return None


def available():
    """True when this backend could run at all — the binding must be reachable."""
    if not sys.platform.startswith("linux"):
        return False
    return _system_python() is not None


def trusted(run=None):
    """True when apps actually publish their trees.

    Separate from `available()` on purpose: everything can be installed and
    still read nothing, because the toolkit switch is off. Telling those two
    apart is the difference between "install this" and "turn this on"."""
    if not available():
        return False
    runner = run or _busctl
    try:
        return "true" in (runner() or "").lower()
    except Exception:
        return False


def _busctl():
    r = subprocess.run(["busctl", "--user", "get-property", "org.a11y.Bus",
                        "/org/a11y/bus", "org.a11y.Status", "IsEnabled"],
                       capture_output=True, text=True, timeout=5)
    return r.stdout


def install_hint():
    """What the user has to do, when this backend cannot read."""
    if _system_python() is None:
        return "sudo apt install python3-gi gir1.2-atspi-2.0"
    if not trusted():
        return ("gsettings set org.gnome.desktop.interface"
                " toolkit-accessibility true")
    return ""


def parse_output(text):
    """Strings out of the child's stdout. Pure.

    Unprefixed lines are dropped: the binding writes warnings (deprecations,
    dbus noise) to the same stream, and a warning is not window text."""
    out = []
    for line in (text or "").splitlines():
        line = line.rstrip()
        if line.startswith(_PREFIX):
            val = line[len(_PREFIX):].strip()
            if val:
                out.append(val)
    return out


def read_window(win, run=None):
    """Strings visible in `win` (a geom.Win), or None if unreadable.

    `run(argv)` is injected so the parse can be tested without a desktop."""
    if win is None or not available():
        return None
    pid = getattr(win, "pid", None)
    if not pid:
        return None                   # pid 로만 창을 고른다 — 제목은 겹친다
    argv = [_system_python(), "-c", READ_PY, str(int(pid)),
            str(MAX_DEPTH), str(MAX_NODES), _PREFIX]
    runner = run or _run
    try:
        return parse_output(runner(argv))
    except Exception:
        return None


def _run(argv, timeout=TIMEOUT):
    proc = subprocess.run(argv, capture_output=True, timeout=timeout)
    if proc.returncode != 0:
        raise OSError("atspi reader exited %d" % proc.returncode)
    return proc.stdout.decode("utf-8", "replace")
