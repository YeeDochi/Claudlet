"""Read the on-screen text of a window through Windows UI Automation.

The Windows twin of `axtree.py`, and deliberately the same four-function
surface (`available` / `trusted` / `install_hint` / `read_window`) so
`core/inspect.py` never learns which OS it is on.

Mechanism follows the precedent already in `winterm.py`: UIA is a COM API with
no stock Python binding, so we drive it through PowerShell and parse stdout.
That keeps the dependency at zero -- PowerShell ships with Windows -- and keeps
the interesting part (building the script, parsing the output) pure and
testable off-Windows, which is where this file is being written.

Unlike macOS there is no permission to grant: a desktop process may read the
UIA tree of another process in the same session. So `trusted()` is just
`available()`, and the failure mode we actually have to survive is PowerShell
being missing, slow, or returning junk.
"""
import subprocess
import sys

# Same caps as the AX side, for the same reasons: a deep tree's tail is layout
# containers, and an unbounded read turns a question into a hang.
MAX_DEPTH = 12
MAX_NODES = 4000
TIMEOUT = 8.0

# One field per line, prefixed, so a value containing our delimiter can't shift
# the parse. Anything not matching a known prefix is ignored rather than
# guessed at.
_PREFIX = "T:"

READ_PS = """
$ErrorActionPreference = 'Stop'
try {
  Add-Type -AssemblyName UIAutomationClient, UIAutomationTypes
  $h = [IntPtr]%(hwnd)d
  $el = [System.Windows.Automation.AutomationElement]::FromHandle($h)
  if (-not $el) { exit 0 }
  $walker = [System.Windows.Automation.TreeWalker]::ControlViewWalker
  $stack = New-Object System.Collections.Generic.Stack[object]
  $stack.Push(@($el, 0))
  $n = 0
  while ($stack.Count -gt 0 -and $n -lt %(max_nodes)d) {
    $pair = $stack.Pop()
    $cur = $pair[0]; $depth = $pair[1]
    $n++
    foreach ($prop in @('NameProperty','HelpTextProperty')) {
      $v = $cur.GetCurrentPropertyValue([System.Windows.Automation.AutomationElement]::$prop)
      if ($v -and "$v".Trim()) { Write-Output ('%(pfx)s' + ("$v" -replace '[\\r\\n]+',' ')) }
    }
    try {
      $vp = $cur.GetCurrentPattern([System.Windows.Automation.ValuePattern]::Pattern)
      if ($vp -and $vp.Current.Value) {
        Write-Output ('%(pfx)s' + ("$($vp.Current.Value)" -replace '[\\r\\n]+',' '))
      }
    } catch { }
    if ($depth -lt %(max_depth)d) {
      $kid = $walker.GetFirstChild($cur)
      while ($kid) { $stack.Push(@($kid, $depth + 1)); $kid = $walker.GetNextSibling($kid) }
    }
  }
} catch { exit 0 }
"""


def build_script(hwnd, max_depth=MAX_DEPTH, max_nodes=MAX_NODES):
    """The PowerShell for one window. Pure -- this is what tests assert on.

    The hwnd goes in as an int through %d, never string-spliced, so a hostile
    window title can't reach the script body (winterm.py passes its title via
    the environment for the same reason).
    """
    return READ_PS % {"hwnd": int(hwnd), "max_depth": int(max_depth),
                      "max_nodes": int(max_nodes), "pfx": _PREFIX}


def parse_output(text):
    """Strings out of the script's stdout. Pure.

    Unprefixed lines are dropped: PowerShell writes warnings and progress to
    the same stream under some hosts, and a warning is not window text.
    """
    out = []
    for line in (text or "").splitlines():
        line = line.rstrip()
        if line.startswith(_PREFIX):
            val = line[len(_PREFIX):].strip()
            if val:
                out.append(val)
    return out


def available():
    """True when this backend could run at all."""
    return sys.platform.startswith("win")


def trusted():
    """No separate grant exists on Windows -- availability is the whole test."""
    return available()


def install_hint():
    """What to tell the user when this can't run, or None when it can."""
    if not available():
        return None          # not this OS; the caller picks another backend
    return None


def _run(script, timeout=TIMEOUT):
    """Execute PowerShell and return stdout. Raises on any failure."""
    proc = subprocess.run(
        ["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
        capture_output=True, timeout=timeout,
        # 창을 띄우지 않는다. GUI 인 펫에서 그냥 띄우면 커맨드 창이 하나 뜨고,
        # 사용자가 그 창을 닫으면 읽기가 죽는다(실기 보고). 같은 이유로
        # winterm/winsend 도 이 플래그를 단다.
        #
        # ponytail: 이 호출은 최대 8초간 펫의 이벤트 루프를 막는다. 읽은 다음에
        # 미리보기를 띄워야 하니 사용자 눈에는 동기 동작이 맞지만, 오래 걸리는
        # 창에서는 펫이 굳어 보인다. 느리다는 보고가 오면 스레드로 뺀다.
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    return proc.stdout.decode("utf-8", "replace")


def read_window(win, run=None):
    """Strings visible in `win` (a geom.Win), or None if unreadable.

    `run(script)` is injected so the parse can be tested without Windows; it
    defaults to a real PowerShell call.
    """
    if win is None or not available():
        return None
    runner = run or _run
    try:
        return parse_output(runner(build_script(win.wid)))
    except Exception:
        return None
