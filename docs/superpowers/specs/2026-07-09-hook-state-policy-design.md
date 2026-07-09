# claude-pet — hook→state policy & animation redesign

_2026-07-09_

## Goal

Replace the provisional `EVENT_STATE` mapping with a deliberate policy that turns
Claude Code's **instantaneous hook events** into a **continuous creature state**,
and expand the animation set so the creature expresses what Claude is actually
doing (which tool, thinking, waiting, done, error).

## Problem with the current approach

`pet.py` maps each hook event directly to a state (`EVENT_STATE`). This breaks on
three facts about how Claude Code hooks actually fire:

1. **`Stop` fires after *every* turn**, not at session end. So `Stop → celebrate`
   makes the creature celebrate after every single response. (This is the root of
   the TODO "celebrate 후 안정 안 됨" bug.)
2. **There is no continuous "Claude is thinking/working" signal.** Hooks are
   discrete points; the active state must be *inferred* from the event stream and
   from gaps between events (with a timeout).
3. **Fast tools fire `PreToolUse`→`PostToolUse` within milliseconds** (e.g.
   `Read`), so a naive "state = last tool" flickers.

## Verified hook firing (Claude Code)

Confirmed against the official hooks reference:

| Event | When |
|-------|------|
| `SessionStart` | session begins/resumes |
| `UserPromptSubmit` | user submits a prompt, before Claude processes it (turn start) |
| `PreToolUse` | before each tool call; payload has `tool_name`, `tool_input` |
| `PostToolUse` | after each tool succeeds; payload has `tool_name`, `tool_input`, `tool_output` |
| `Stop` | **after every assistant turn** (not session end); does not fire on user interrupt |
| `StopFailure` | turn ended by API error instead of `Stop`; has `error_type` |
| `Notification` | has `notification_type` — notably `permission_prompt` (tool approval needed) vs `idle_prompt` (waiting for user) |
| `SubagentStop` | a subagent (`Task`) finished |
| `SessionEnd` | session ends |

Typical turn order: `UserPromptSubmit → (PreToolUse → PostToolUse)* → Stop`.

Caveats (documented as uncertain): the `idle_prompt` timeout duration is not
published, and exact hook ordering is inferred — both to be confirmed empirically
during implementation.

## State & animation inventory

| State | Trigger | Motion |
|-------|---------|--------|
| `thinking` | `UserPromptSubmit`, until the first tool of the turn (or `Stop`) | pondering alone, deep in thought 🤔 (no lightbulb) |
| `work_computer` | `Pre/PostToolUse` where `tool_name` ∈ {`Edit`,`Write`,`NotebookEdit`,`Bash`} | typing at the laptop |
| `work_search` | `tool_name` ∈ {`Read`,`Grep`,`Glob`} | darting quickly left/right, rummaging |
| `work_web` | `tool_name` ∈ {`WebFetch`,`WebSearch`} or starts with `mcp__` | making a phone call ☎️ (reaching outside) |
| `work_agent` | `PreToolUse` `tool_name`==`Task`, until matching `SubagentStop` | small Claude clones filing out 🐤 |
| `work_skill` | `tool_name`==`Skill` | dons a little party hat, sparkle ✨ |
| `attention` 🔴 | `Notification` `notification_type`==`permission_prompt` | jumps up, `!` bubble |
| `idle` (normal) | `Stop` **while the Claude terminal is focused** | calm standing / roaming |
| `celebrate` 🔔 | `Stop` **while the Claude terminal is NOT focused** | completion hop + "다 됐다!" — an alert for when the user is looking elsewhere |
| `sleeping` | quiet for the idle timeout after `Stop`, or `Notification{idle_prompt}` | dozes, `zZ` |
| `error` | `StopFailure` | tips over, `X_X` |
| `walk` | roaming movement | walking (render-only, not a Claude state) |

Notes:
- **Naming:** `idle` = calm, awake, "your turn" (this is the renderer's existing
  `idle` gentle-bob motion). The renderer's current `waiting` state (the sleeping
  `zZ` one) is **renamed `sleeping`** — the old `waiting` name is dropped to avoid
  the "waiting = your turn?" ambiguity.
- Any unrecognized `tool_name` (incl. other MCP or new built-ins) falls back to
  `work_computer`.
- `celebrate` is **not** a "joy" state — its purpose is a completion alert **only
  when the user isn't looking at the terminal**. When the terminal is focused,
  `Stop` goes straight to the calm `idle` state (no hopping). This also removes
  the every-turn-celebration overkill for free.

## State-derivation policy (the engine)

Per active session (`session_id`), track a small record: current base state and a
`last_event` monotonic timestamp. The displayed state is derived, not stored raw.

**1. Tool → working sub-state.** On `PreToolUse`, map `tool_name` to one of the
`work_*` states (table above) and set it as the session's state.

**2. Debounce (minimum hold = 0.8s).** When a `work_*` state is set, stamp a
`hold_until = now + 0.8s`. A newer `work_*` for the same session updates the state
but the *previous* motion is guaranteed to have shown for ≥0.8s (fast tools like
`Read` don't flicker). Implemented by not letting the render state change before
`hold_until` except for higher-priority interrupts (attention/error).

**3. Thinking inference.** `UserPromptSubmit` sets `thinking`. It naturally ends
when the first `PreToolUse` arrives (→ `work_*`) or `Stop` arrives (→ idle/
celebrate). No continuous signal needed.

**4. Turn end + focus check.** On `Stop`, query whether the Claude terminal
(Konsole) is the active window:
- focused → `idle`
- not focused → `celebrate` for **1.6s**, then decay to `idle`.

**5. Sleep timeout = 60s.** If a session sits in `idle` with no new event for
60s → `sleeping`. `Notification{idle_prompt}` forces `sleeping` immediately.

**6. Error.** `StopFailure` → `error` (transient, decays to `idle` like
celebrate; duration ~2s).

**7. Session lifecycle.** `SessionStart` → session enters `idle`.
`SessionEnd` → drop the session. When no sessions remain → `sleeping`.

**8. Multi-session priority.** When several sessions are active, display the
highest-priority state:
`attention > error > work_* > thinking > celebrate > idle > sleeping`.
(`work_*` variants share one priority tier; ties broken by most-recent event.)

## Required code changes

**`bin/claude-pet-hook`** — currently forwards only `{event, session}`. Must also
forward the fields the policy needs:
- `tool_name` (from `PreToolUse`/`PostToolUse` payload)
- `notification_type` (from `Notification` payload)
- `error_type` (from `StopFailure`, optional)
Still never blocks, still exits 0.

**`bin/claude-pet-install-hooks`** — add `StopFailure` to the registered events.
(`PreToolUse`/`PostToolUse` already use matcher `*`, which is what we need.)

**`src/pet.py`** — replace `EVENT_STATE`/`_recompute_state` with the policy engine
above: per-session records with timestamps, debounce, idle timeout tick, focus
check on `Stop`, `StopFailure` handling, and the tool_name→state map. The existing
`_tick` already runs at 20fps and is the natural place to age out
debounce/idle/celebrate/error timers.

**`src/creature.py`** — add the new states to `STATES` and a rig branch for each:
`thinking` (pondering pose, replacing bulb), `work_computer` (existing laptop),
`work_search` (fast horizontal dart), `work_web` (phone-to-ear pose), `work_agent`
(row of small clones), `work_skill` (party hat + sparkle), plus keep `attention`,
`idle` (calm bob), `celebrate`, `error`, `walk`, and **rename** the existing
`waiting` (sleeping `zZ`) motion to `sleeping`. Update the standalone
sprite-sheet `__main__` to show the new states.

## Risks / spikes

- **Focus detection on KDE Wayland is the one real unknown.** The pet already
  loads KWin scripts via `qdbus6 org.kde.KWin /Scripting` to *activate* Konsole,
  but *reading* the active window's `resourceClass` back into Python is not
  obviously supported by plain DBus on Wayland (Konsole is a native Wayland
  client, invisible to X tools like `xdotool`). Plan: spike a KWin query script
  (e.g. `callDBus` back to a tiny listener, or a persistent script emitting the
  active-window class on change). **Fallback if infeasible:** always `celebrate`
  on `Stop` but suppressed while the pet detects its own recent interaction, or
  gate the strong alert on `idle_prompt` instead of live focus. Decide during the
  spike; the rest of the design does not depend on the outcome.

## Deferred (out of scope for this spec)

- Real typed text in bubbles ("고민중...", "이거 맞아?", "다 됐다!") — motion first.
- Auto/plan "long autonomous run" dedicated state.
- GIF asset override rendering.
- Multi-monitor floor/roam correctness (tracked separately in TODO).

## Timing constants (final)

- working sub-state debounce / minimum hold: **0.8s**
- `idle` → `sleeping` transition after quiet: **60s**
- celebrate duration: **1.6s** → decay to `idle`
- error duration: **~2s** → decay to `idle`
