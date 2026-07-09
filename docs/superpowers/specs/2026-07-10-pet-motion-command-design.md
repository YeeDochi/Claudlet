# Pet motion command — design

Date: 2026-07-10
Status: approved-for-planning

## Goal

Let the user trigger a motion/animation on the pet on demand, via
`/claude-pet <motion>`. A triggered motion plays for a short time, then the pet
returns to whatever its Claude-activity state is. One motion (`float`) can be
held indefinitely until cleared, giving a "no-gravity" toggle.

## Command surface (extends the existing `claude-pet` skill)

- `/claude-pet` — attach a pet to the current session (unchanged)
- `/claude-pet standalone` — launch an unattached roaming pet (unchanged)
- `/claude-pet <motion>` — play a motion (see vocabulary below)
- `/claude-pet list` — print the available motions
- `/claude-pet stop` (alias `clear`) — clear any held motion (returns `float` to gravity)

The skill dispatches `<motion>`/`list`/`stop` to a new helper; the bare and
`standalone` forms keep their current behavior.

## Motion vocabulary

New motions (added to `creature.py` `STATES` + a rig branch each):

| motion  | look | default dur |
|---------|------|-------------|
| `jump`  | big vertical hops, squash on landing | 2.5s |
| `wave`  | one arm raised, swinging side to side | 2.5s |
| `sing`  | mouth open, music-note prop, body sway | 3.0s |
| `juggle`| arms up, balls arcing overhead (prop) | 3.0s |
| `float` | drifts up and bobs in place, no floor | **held** (0 = until cleared) |

Existing states also exposed as triggerable (no new art):
`celebrate, thinking, sleeping, error, attention`.

Any other name → helper rejects it (skill prints the valid list).

## Delivery path

New helper `bin/claude-pet-motion <name> [dur]`:

- Resolves live pet sockets by globbing `$XDG_RUNTIME_DIR/claude-pet-*.sock`
  (the skill has no session UUID, so it broadcasts; normally one pet, so this
  is effectively targeted — multiple sessions all react, which is acceptable).
- Sends one JSON line per socket: `{"cmd":"motion","motion":<name>,"dur":<sec>}`.
- `dur` defaults to the per-motion value above; `0` means hold until cleared.
- `stop` sends `{"cmd":"motion","motion":null}` (clear).
- Never blocks/raises on a dead socket — mirrors `claude-pet-hook`'s
  swallow-everything invariant.

`dur` is chosen by the helper from a name→duration table so the skill stays
thin; an explicit `[dur]` arg overrides it.

## pet.py changes

Timed override layered on top of the existing state machine — does NOT go
through `StateEngine` (that is Claude-event-driven only).

- New fields: `self._motion = None`, `self._motion_expiry = None`.
- `_handle_event`: if `ev.get("cmd") == "motion"`:
  - `motion` falsy → clear override (`self._motion = None`); if we were
    `float`, drop to `mode="thrown"` so gravity brings it back down.
  - else set `self._motion = motion`; `dur>0` → `self._motion_expiry = now+dur`,
    `dur<=0` → `self._motion_expiry = None` (held).
  - a `cmd` message is NOT a Claude event: it must not cancel the SessionEnd
    quit timer, so branch before the `_cancel_quit()` logic.
- `_tick`: after computing `claude_state`, if `self._motion` is set and
  `self.mode not in ("held","thrown")`:
  - expire first (`_motion_expiry` set and `now >= expiry` → clear, fall through
    to normal).
  - else force `self._render_state = self._motion` and skip roam/physics for
    this tick. For `float`, lift `self.y` toward a hover line and apply a bob so
    it visibly leaves the floor; on clear it falls via `thrown`.
- Dragging/throwing overrides the motion (physics/`held` win) — that's why the
  override is gated on `mode`.

## creature.py changes

Add `jump`, `wave`, `sing`, `juggle`, `float` to `STATES`, one rig branch each
(bob / sx / sy / tilt / prop), following the existing per-state pattern:

- `jump`  — large negative `bob` on a short cycle, `sy<1` squash at the bottom.
- `wave`  — reuse arm drawing with a raised-arm param; add a `wave` arm mode.
- `sing`  — `prop="note"` (new music-note prop), open-mouth eye/mouth variant, `tilt` sway.
- `juggle`— `prop="balls"` (new arced-balls prop), arms raised.
- `float` — slow sinusoidal `bob`, faint `tilt` drift, slight vertical stretch.

New props (`note`, `balls`) drawn in the untilted `rect()` space like existing
props. `wave` needs a small addition to the arm section (currently only `walk`
swings arms).

`SPEECH` optionally gains a line for `sing` ("라라라~") if a speech bubble reads
well; otherwise the note prop alone.

## Out of scope

- No new hook wiring (motions are user-invoked, not Claude-event-driven).
- No persistence of motion state across pet restarts.
- No per-motion sound.

## Testing / verification

- `python3 src/creature.py` sprite sheet renders all new motions without error.
- Run a pet, invoke each `/claude-pet <motion>`, confirm it plays and returns.
- `float` holds until `/claude-pet stop`, then falls under gravity.
- Dead-socket / no-pet case: helper exits 0 silently.
- Multi-monitor roam fix (already shipped) unaffected.
