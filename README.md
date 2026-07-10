# claude-pet 🐾

**English** | [한국어](README.ko.md)

A tiny pixel creature that lives on your desktop and reacts to **Claude Code** in
real time. It wanders around; when Claude works it hops behind a laptop and types,
and when Claude needs you it stands up with a speech bubble. Click it to bring the
Claude Code terminal back to the front.

Best on **KDE Plasma**, but the creature itself runs anywhere PyQt6 does. It's
drawn entirely in code — no image assets — so the whole thing is self-contained
and original (CC0 artwork).

![states](docs/superpowers/specs/creature_sheet.png)

## States

| State | Looks like | Triggered by |
|-------|-----------|--------------|
| idle / waiting | wanders around, then dozes (`z`) | no active tool activity |
| working | tool-specific: laptop (edit), magnifier (search/read), phone (web/MCP), clones (subagent), wizard hat (skill) | `PreToolUse` |
| thinking | head cocked, "고민중…" bubble | `UserPromptSubmit` |
| **attention** | jumps up, "이거 맞아?" | permission prompt |
| **asking** | waits calmly, "응?" | `AskUserQuestion` / `ExitPlanMode` |
| **autopilot** | puts a VR visor on and cruises; per-tool visor variants while auto/bypass mode is on | `permission_mode` auto/bypass |
| celebrate | happy hop, "다 됐다!" | finished while you're away |
| error | tips over, `X_X` | a failed turn |
| sleeping | `Z` | idle for a while |

It also **perches on and rides windows**: drop it on a window and it walks along the
top or lives inside; drag it onto the desktop and it wanders freely. When the window
it's riding is covered or minimized, the pet clips/hides with it.

## How it works

```
Claude Code ──hook──▶ claude-pet-hook ──unix socket──▶ pet (PyQt6 window)
```

- **`src/pet.py`** — the pet: a frameless, translucent, always-on-top window.
  It runs under XWayland (`QT_QPA_PLATFORM=xcb`) so it can roam freely, since
  native Wayland forbids a client from positioning its own window.
- **`src/creature.py`** — the creature renderer (pure `QPainter`, state-driven).
- **`bin/claude-pet-hook`** — forwards each Claude Code hook event to the pet
  over a per-session unix socket (`$XDG_RUNTIME_DIR/claude-pet-<session>.sock`),
  and launches a pet on `SessionStart`. Never blocks Claude.

## Requirements

- Python 3 + PyQt6 — `pip install PyQt6`
- **KDE Plasma** for the full experience: `qdbus6` (window integration / click-to-focus),
  `wmctrl` (optional, hides the pet from the taskbar). XWayland if on Wayland.

## Platform support

The reactive core (states, animation, roaming, drag-and-throw, tray) is portable;
the window integration (perch/occlusion, click-to-focus, taskbar-hide) is KDE-specific
and simply switches off elsewhere — the pet still runs.

| Platform | Runs | Window integration |
|----------|------|--------------------|
| **KDE Plasma** (Wayland/X11) | ✅ | ✅ full — perch, occlusion clip/hide, click-to-focus, taskbar-hide |
| Other Linux (GNOME, …) | ✅ (XWayland) | ✖ KDE-only bits no-op (roam/drag/states/tray work) |
| **macOS** | 🅱️ should launch (native Qt) | ✖ not implemented — needs a Cocoa focus/positioning layer |
| **Windows** | 🚧 not yet | hook↔pet plumbing (bash launcher, AF_UNIX socket) is Unix-oriented |

Only KDE is actively tested. GNOME is out of scope for window integration. Non-KDE
just falls back to the desktop floor with everything KDE-specific disabled.

### Help test on your OS

macOS/Windows paths are best-effort and **unverified on real hardware** — reports
welcome. If you run it, please check and open an issue:

- **Launches?** `bin/claude-pet` shows the creature; it roams, and drag-and-throw works.
- **Reacts?** After `claude-pet-install-hooks`, using Claude Code changes its state
  (working / thinking / celebrate).
- **Tray** icon appears and its menu works.
- **macOS only:** left-click brings your terminal/IDE (Terminal/iTerm/VS Code) to the
  front (`osascript`); frontmost-app detection gates the "celebrate" pose.
- Note what's broken vs. the table above (perch/occlusion/taskbar-hide are KDE-only by design).

## Install

```bash
git clone <this-repo> ~/claude-pet
pip install PyQt6
~/claude-pet/bin/claude-pet-install-hooks      # register hooks in ~/.claude/settings.json
~/claude-pet/bin/claude-pet                     # run it
```

Restart any running Claude Code session so it picks up the new hooks.

## `/claude-pet` skill (optional)

A Claude Code skill to launch a pet on demand from within a session. Enable it
by linking it into your skills dir:

```bash
mkdir -p ~/.claude/skills
ln -s ~/claude-pet/skills/claude-pet ~/.claude/skills/claude-pet
```

Then type `/claude-pet` (or "펫 띄워") in any session to launch one. This only
*launches* a pet; the per-session auto-launch still comes from the hooks above.

## Interaction

- **Drag** to pick it up and throw it — it falls with gravity and bounces. Fling
  it inside a window and it bounces off the interior walls; drag it out to leave.
- **Left-click** — bring the Claude Code terminal (Konsole) to the front.
- **Right-click / tray** — menu: *커서 따라오기* (follow the cursor) / *모션* submenu
  (jump / wave / sing / juggle / celebrate) / *둥둥 띄우기* (float, no-gravity toggle) /
  *quiet (mute)* / *quit*.
- **Motions from the CLI/skill** — `/claude-pet <motion>` (or
  `bin/claude-pet-motion <motion>`): `jump`, `wave`, `sing`, `juggle`, `float`,
  plus `celebrate`/`thinking`/`sleeping`/`error`/`attention`; `list`, `stop`.

## Custom motion mapping

Remap which motion shows for which Claude Code activity in a JSON config at
`~/.config/claude-pet/config.json` (all keys optional):

```json
{
  "tools":      { "Bash": "work_search", "Grep": "sing", "*": "work_computer" },
  "events":     { "prompt": "thinking", "celebrate": "juggle" },
  "raw_events": { "PostToolUse": "celebrate", "SubagentStop": "wave" }
}
```

- `tools` — tool name → state. `"*"` is the fallback for unmapped tools;
  `mcp__*` tools default to `work_web` unless named explicitly.
- `events` — event slot → state. Slots: `start`, `prompt`, `done`, `celebrate`,
  `error`, `permission`, `idle_prompt`.
- `raw_events` — raw hook event name → state, for any event without a slot
  (`PostToolUse`, `SubagentStop`, `PreCompact`, …). Knowing the event name the
  hook sends is enough to map it; slotted events keep their built-in behaviour.

Values must be a known state/motion (`work_computer`, `work_search`, `work_web`,
`work_agent`, `work_skill`, `idle`, `sleeping`, `thinking`, `attention`, `error`,
`celebrate`, `jump`, `wave`, `sing`, `juggle`); anything unknown is ignored, so a
typo falls back to the defaults. Restart the pet to pick up changes.

## Autostart

Copy the desktop entry so it launches at login:

```bash
cp ~/claude-pet/packaging/claude-pet.desktop ~/.config/autostart/
```

Remove that file to disable.

## Uninstall

```bash
~/claude-pet/bin/claude-pet-install-hooks --remove
rm ~/.config/autostart/claude-pet.desktop
rm -rf ~/claude-pet
```

## License

Code: MIT. Original artwork (the creature): CC0.
