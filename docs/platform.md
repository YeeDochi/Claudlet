# Platform support

[← README](../README.md) · **English** | [한국어](platform.ko.md)

The reactive core (states, animation, roaming, drag-and-throw, tray) is portable.
Window integration (perch/occlusion, click-to-focus) works on all three target
platforms — KDE via a KWin script, Windows via polled Win32 APIs, and macOS via
polled Quartz (`pyobjc`). Taskbar-hide is still KDE-only. Everything else just
switches off where it isn't implemented — the pet still runs.

All three platforms are **hardware-verified** as of v1.0.0.

| Platform | Runs | Window integration |
|----------|------|--------------------|
| **KDE Plasma** (Wayland/X11) | ✅ | ✅ full — perch, occlusion clip/hide, click-to-focus, taskbar-hide |
| Other Linux (GNOME, …) | ✅ (XWayland) | ✖ KDE-only bits no-op (roam/drag/states/tray work) |
| **Windows** | ✅ | ✅ perch, occlusion clip/hide, click-to-focus (`SetForegroundWindow`, polled `ctypes`/Win32); ✖ taskbar-hide not implemented |
| **macOS** | ✅ | ✅ perch, occlusion clip/hide, click-to-focus (`osascript`); self-calibrates CG→Qt coordinates at runtime (polled Quartz via `pyobjc`); ✖ taskbar-hide + hide-when-host-minimized not implemented |

All CLI tools (`bin/*`) are Python — no bash — so they run wherever Python does.
KDE, Windows, and macOS are all actively supported; GNOME is out of scope for
window integration. Where window integration isn't implemented (GNOME, or macOS
without `pyobjc`), the pet falls back to the desktop floor with those features
disabled.

> **A note on macOS testing.** The maintainer has no Mac, so macOS is verified on
> real hardware by a contributor — which means macOS-specific regressions tend to
> surface *after* a release rather than before. Reports are very welcome (see
> [macOS notes](#macos-notes) below).

## Requirements

- Python 3 + PyQt6 — `pip install PyQt6`
- **KDE Plasma** for the full experience: `qdbus6` (window integration / click-to-focus),
  `wmctrl` (optional, hides the pet from the taskbar). XWayland if on Wayland.
- **Windows**: nothing extra — window integration uses only the stdlib `ctypes`
  bindings to `user32`/`dwmapi`/`kernel32` in `src/claudlet/windows_win32.py`.
- **macOS only**: `pip install pyobjc-framework-Quartz` for perch/occlusion
  (`src/claudlet/windows_macos.py`). The installer (`pipx install claudlet` or the
  one-line source installer) adds it automatically. Optional — without it the pet
  still runs, with window integration off. Never needed (or imported) on
  Windows/Linux.

## Known limits / open items

- **Windows display scaling** — the Win32 geometry feed converts each window's
  physical-pixel rect to Qt logical coordinates using its monitor's DPI
  (`GetDpiForWindow`), so perch/occlusion line up at 125%/150% scaling on a
  single monitor and on same-scale multi-monitor arranged from the origin.
  **Mixed-DPI multi-monitor** (different scale per screen) still needs
  real-hardware calibration of each screen's logical origin — expect perch
  offsets across the seam until then.
- **Multi-user hosts** — the pet's command channel is an *unauthenticated*
  loopback TCP listener. On a shared machine another local user could connect
  to `127.0.0.1:<port>` and drive/quit the pet (state and motion only — no file
  or code access). Fine for a single-user desktop; a token handshake is the
  planned fix if this matters for your setup.

## macOS notes

- **Screen Recording permission (optional).** Since macOS 10.15, the window-
  enumeration API omits other apps' window *titles* unless the calling app has
  Screen Recording permission (System Settings → Privacy & Security → Screen
  Recording, granted to the terminal or Python that launches the pet).
  Perch/occlusion still work **without** it — the code falls back to app names —
  so grant it only if you want title-level accuracy.
- **Perch coordinates off?** Run `claudlet-macos-diag` to print the raw macOS
  window coordinates the pet sees; it's the fastest way to diagnose a perch that
  lands at the wrong height or on a second monitor. File an issue with its output.
- **Not implemented on macOS:** taskbar-hide (KDE-only by design) and per-session
  host-window tracking (hide-when-host-minimized). Everything else — roam, drag/
  throw, states, tray, perch, occlusion, click-to-focus — is supported.
