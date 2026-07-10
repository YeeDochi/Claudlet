# Usage & interaction

[← README](../README.md)

## How it works

```
Claude Code ──hook──▶ claude-pet-hook ──unix socket──▶ pet (PyQt6 window)
```

- **`src/pet.py`** — the pet: a frameless, translucent, always-on-top window. On
  Linux it runs under XWayland (`QT_QPA_PLATFORM=xcb`) so it can position itself,
  which native Wayland forbids; on macOS/Windows it uses the native Qt platform.
- **`src/creature.py`** — the creature renderer (pure `QPainter`, state-driven).
- **`bin/claude-pet-hook`** — forwards each Claude Code hook event to the pet over
  a per-session unix socket (`$XDG_RUNTIME_DIR/claude-pet-<session>.sock`) and
  launches a pet on `SessionStart`. Never blocks Claude.

All `bin/*` tools are Python, so they run wherever `python3` does.

## Interaction

- **Drag** to pick it up and throw it — it falls with gravity and bounces. Fling it
  inside a window and it bounces off the interior walls; drag it out to leave.
- **Left-click** — bring the Claude Code terminal/IDE to the front.
- **Right-click / tray** — menu: *커서 따라오기* (follow the cursor) · *모션* submenu
  (jump / wave / sing / juggle / celebrate) · *둥둥 띄우기* (float, no-gravity toggle) ·
  *quiet (mute)* · *quit*.
- **Motions from the CLI/skill** — `/claude-pet <motion>` (or
  `bin/claude-pet-motion <motion>`): `jump`, `wave`, `sing`, `juggle`, `float`, plus
  `celebrate` / `thinking` / `sleeping` / `error` / `attention`; `list`, `stop`.

## The `/claude-pet` skill

`claude-pet-install` links this skill into `~/.claude/skills/` for you. In any
session, `/claude-pet` (or "펫 띄워") launches a pet on demand — handy for a session
that predates the install, or to bring a closed pet back. Per-session auto-launch
still comes from the hooks.

Manual link, if you installed hooks only:

```bash
ln -s ~/claude-pet/skills/claude-pet ~/.claude/skills/claude-pet
```

## Autostart

Copy the desktop entry so a standalone pet launches at login:

```bash
cp ~/claude-pet/packaging/claude-pet.desktop ~/.config/autostart/
```

Remove that file to disable.

## Uninstall

```bash
~/claude-pet/bin/claude-pet-install --remove    # removes hooks + skill link
rm ~/.config/autostart/claude-pet.desktop       # if you enabled autostart
rm -rf ~/claude-pet
```
