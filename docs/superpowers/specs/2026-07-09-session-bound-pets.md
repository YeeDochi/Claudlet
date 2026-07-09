# claude-pet — session-bound pets (one pet per Claude Code session)

_2026-07-09_

## Decision

Move from **one shared desktop pet** (all sessions collapsed by priority) to **one pet
per Claude Code session**, launched from *inside* the session. Rationale: with several
sessions open, a per-session creature makes it obvious which session finished and which
needs input. Multiple pets on screen is acceptable; 3+ concurrent sessions is rare.

A side benefit: because the launcher runs inside the session, the pet inherits the
session environment — so it knows both the `session_id` and the **host app** (terminal or
IDE) with no external window-detection spike.

## Architecture change

### Launch (session-bound)
- The `SessionStart` hook launches a pet for that session, detached, passing the
  `session_id` and the detected host. It must not double-launch if that session's pet is
  already running (check the per-session socket / a pidfile).
- A `claude-pet-session <session_id> [--host <host>]` launcher wraps this; the
  `SessionStart` hook calls it. (A `/claude-pet` skill/command for manual start/stop is a
  nice-to-have follow-up, not required for v1.)
- Login autostart (`packaging/claude-pet.desktop`) becomes optional — the pet is now
  session-scoped, not desktop-scoped.

### Host detection (folds in the old feat/host-detection)
Detected at launch from env, in priority order:
- `TERM_PROGRAM == "vscode"` (or `VSCODE_PID` set) → host `vscode`, window class `code`
- `TERMINAL_EMULATOR` contains `JetBrains` → host `jetbrains`, class `jetbrains`
- `KONSOLE_VERSION` set → host `konsole`, class `konsole`
- else → host `unknown`, no reliable class (activation/focus best-effort/off)

The pet stores its host → a list of window-class substrings, used by:
- `_activate_claude` — raise the session's host window (not hardcoded konsole).
- `focus.terminal_focused(host_classes)` — celebrate only fires when the session's host
  window is NOT focused; on `unknown` host, keep the conservative suppress-celebrate
  fallback.

### Per-session transport
- Each pet listens on `$XDG_RUNTIME_DIR/claude-pet-<session_id>.sock`.
- `claude-pet-hook` already knows `session_id` (in the payload); it sends each event to
  that session's socket. No shared socket, no priority collapse.
- The `StateEngine` now tracks a single session per pet; multi-session priority becomes
  vestigial (keep the code, it's harmless, or trim to single-session later).

### Lifecycle
- `SessionEnd` → the pet for that session exits cleanly (removes its socket).
- Multiple pets spawn at staggered X positions so they don't perfectly overlap.

## Files touched (planned)
- `bin/claude-pet-hook` — on `SessionStart`, launch the session pet (detached) if not
  already up; still forward every event to the per-session socket. Detect host from env
  and pass it through.
- `bin/claude-pet-session` (new) — launcher: `pet.py --session <sid> --host <host>`.
- `src/pet.py` — accept `--session`/`--host`; per-session socket path; quit on
  `SessionEnd`; host-aware `_activate_claude`; stagger initial X.
- `src/focus.py` — `terminal_focused(classes)` takes the host's classes.
- `bin/claude-pet-install-hooks` — unchanged event list; SessionStart now also launches.
- `README.md` / `packaging` — document session-bound model; autostart optional.

## Out of scope (v1)
- `/claude-pet` skill for manual toggle (follow-up).
- Reconciling two sessions sharing one host window (same IDE window, two terminals).
- Trimming the now-vestigial multi-session priority code.

## Verification
- Unit: host-from-env mapping; per-session socket path; hook launch-guard (no double
  launch). Offscreen pet smoke with `--session`/`--host`.
- Manual: open two sessions (e.g. one in Konsole, one in VS Code) → two pets, each
  reacting to its own session; click each raises its own host window; SessionEnd removes
  its pet.
