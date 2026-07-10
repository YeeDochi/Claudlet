# Platform support

[← README](../README.md)

The reactive core (states, animation, roaming, drag-and-throw, tray) is portable;
the window integration (perch/occlusion, click-to-focus, taskbar-hide) is
KDE-specific and simply switches off elsewhere — the pet still runs.

| Platform | Runs | Window integration |
|----------|------|--------------------|
| **KDE Plasma** (Wayland/X11) | ✅ | ✅ full — perch, occlusion clip/hide, click-to-focus, taskbar-hide |
| Other Linux (GNOME, …) | ✅ (XWayland) | ✖ KDE-only bits no-op (roam/drag/states/tray work) |
| **macOS** | 🅱️ should launch (native Qt) | ⚠️ best-effort click-to-focus via `osascript`; perch/occlusion not implemented |
| **Windows** | 🚧 GUI may run | ✖ hook↔pet uses `AF_UNIX` sockets; skill symlink needs privileges — unverified |

All CLI tools (`bin/*`) are Python — no bash — so they run wherever `python3` does.
Only KDE is actively tested. GNOME is out of scope for window integration. Non-KDE
just falls back to the desktop floor with everything KDE-specific disabled.

## Requirements

- Python 3 + PyQt6 — `pip install PyQt6`
- **KDE Plasma** for the full experience: `qdbus6` (window integration / click-to-focus),
  `wmctrl` (optional, hides the pet from the taskbar). XWayland if on Wayland.

## Help test on your OS

macOS/Windows paths are best-effort and **unverified on real hardware** — reports
welcome. If you run it, please check and open an issue:

- **Launches?** `bin/claude-pet` shows the creature; it roams, and drag-and-throw works.
- **Reacts?** After `claude-pet-install`, using Claude Code changes its state
  (working / thinking / celebrate).
- **Tray** icon appears and its menu works.
- **macOS only:** left-click brings your terminal/IDE (Terminal / iTerm / VS Code) to
  the front (`osascript`); frontmost-app detection gates the "celebrate" pose.
- Note what's broken vs. the table above (perch / occlusion / taskbar-hide are KDE-only
  by design).
