"""Focus a Claude session's Windows Terminal tab over UI Automation.

Click-to-focus maps a session to its host window by process id (see
`geom.pick_focus_target`). Windows Terminal runs every window AND every tab in
ONE process, so all of its windows/tabs share that single pid: the window pid
can't tell two Claude sessions apart, and raising the window doesn't switch to
the right *tab*. Exactly the problem `konsole.py` describes on KDE — one
process, many tabs — so this module is its Windows twin.

Win32 can't help: a tab is not an HWND. UI Automation can — Windows Terminal
exposes each tab as a TabItem supporting SelectionItemPattern, so a tab can be
selected programmatically, including in a window that isn't focused.

What identifies OUR tab is its TITLE. Claude Code keeps the terminal title in
sync with the conversation, and the hook (which runs inside the pane) reads it
straight off the console — see `cli/hook.py:console_title`. That string is
exactly what UIA reports as the TabItem's Name, so matching is a plain
comparison rather than a guess.

The one wrinkle is that Claude Code prefixes the title with an ANIMATED status
glyph (observed cycling through "✳", "⠂", "⠐"): a title captured at hook time
would not match by the time the user clicks. `normalize_title` strips that
prefix, and the PowerShell side matches on *containment*, so the two ends never
have to agree on which glyph was current.

The decision logic here is pure and tested (`tests/unit/test_winterm.py`);
`pet.py` injects a real PowerShell runner. Best-effort throughout: no Windows
Terminal, no matching tab, or any UIA error simply returns None and the caller
falls back to the plain window raise it already did.
"""

# The title is handed over in the ENVIRONMENT, never spliced into the script or
# an argv: conversation titles routinely contain quotes, `$`, and backticks,
# all of which are active characters in PowerShell.
TITLE_ENV = "CLAUDLET_TAB_TITLE"

WT_WINDOW_CLASS = "CASCADIA_HOSTING_WINDOW_CLASS"

# Selects the single Windows Terminal tab whose name contains $env:CLAUDLET_TAB_TITLE.
#
# "Contains", not equals, because the caller passes a glyph-stripped title while
# the tab name still carries the live status glyph. Requiring EXACTLY ONE match
# across every terminal window is what keeps that loose test safe: two sessions
# with the same title select nothing rather than yanking focus to the wrong one.
#
# Scanning every WT window (not just the first) also settles which window to
# raise when the user has several -- the one holding our tab is by definition
# ours, which pid-ancestry could never determine.
SELECT_PS = """
$ErrorActionPreference = 'Stop'
try {
  $want = $env:%(env)s
  if (-not $want) { exit 0 }
  Add-Type -AssemblyName UIAutomationClient, UIAutomationTypes
  $root = [System.Windows.Automation.AutomationElement]::RootElement
  $wcond = New-Object System.Windows.Automation.PropertyCondition(
    [System.Windows.Automation.AutomationElement]::ClassNameProperty, '%(cls)s')
  $tcond = New-Object System.Windows.Automation.PropertyCondition(
    [System.Windows.Automation.AutomationElement]::ControlTypeProperty,
    [System.Windows.Automation.ControlType]::TabItem)
  $hits = @()
  foreach ($w in $root.FindAll([System.Windows.Automation.TreeScope]::Children, $wcond)) {
    foreach ($t in $w.FindAll([System.Windows.Automation.TreeScope]::Descendants, $tcond)) {
      # .Contains, NOT -like: -like treats *, ? and [ as wildcards, and
      # conversation titles are prose that routinely contains them.
      $n = $t.Current.Name
      if ($n -and $n.Contains($want)) { $hits += ,@($w, $t) }
    }
  }
  if ($hits.Count -ne 1) { exit 0 }
  $win, $tab = $hits[0]
  $pat = $null
  if ($tab.TryGetCurrentPattern(
        [System.Windows.Automation.SelectionItemPattern]::Pattern, [ref]$pat)) {
    $pat.Select()
  }
  # Selecting a tab does not bring the window forward over other apps. The
  # caller already raised the window it found by pid/class, but with several
  # terminal windows open that may not be the one holding our tab -- so raise
  # the one we actually matched.
  try { $win.SetFocus() } catch { }
} catch { }
exit 0
""" % {"env": TITLE_ENV, "cls": WT_WINDOW_CLASS}


def normalize_title(title):
    """Strip Claude Code's leading status glyph so a title captured at hook time
    still matches the tab at click time.

    The glyph animates ("✳" -> "⠂" -> "⠐" and friends), so only the text after it
    is stable. Drops every leading character that is neither alphanumeric nor an
    opening bracket, then trims. Returns "" for anything empty or glyph-only --
    the caller treats that as "nothing to match on" and skips the lookup rather
    than firing a wildcard that could hit any tab.
    """
    if not title:
        return ""
    s = str(title).strip()
    i = 0
    while i < len(s) and not (s[i].isalnum() or s[i] in "([{<"):
        i += 1
    return s[i:].strip()


def focus(title, run):
    """Select the Windows Terminal tab whose name carries `title`.

    `run(normalized_title)` performs the UIA call (pet.py hands it a PowerShell
    launcher). Returns the normalized title that was dispatched, or None when
    there was nothing usable to match on or the runner failed -- the caller then
    just leaves the window raise it already did.

    Does NOT raise the window itself for the common single-window case; that has
    already happened by the time we get here (see `Pet._activate_claude_windows`).
    """
    want = normalize_title(title)
    if not want:
        return None
    try:
        run(want)
    except Exception:
        return None
    return want
