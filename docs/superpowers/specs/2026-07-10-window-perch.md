# claude-pet — window perching & containment (KDE only)

_2026-07-10_

## Goal

Let the pet interact with other windows (three behaviors the user asked for):
1. **Perch on top** — walk/land on the top edge of other windows (e.g. a small
   terminal's title bar).
2. **Contained in a window** — live *inside* a window's rectangle, roaming within
   it and following it as it moves.
3. **Drag into a window** — dropping the pet onto a window puts it inside (2).

**KDE-only, gated.** Perching needs live geometry of *other* windows, which is
platform-specific. Where that geometry is unavailable (no `wmctrl` / non-KDE),
the feature is simply inert and the pet behaves exactly as today (screen floor).
This does not KDE-lock the whole app — it's an optional capability
(cf. [[platform-support-scope]]).

## Data source

`wmctrl -lG` lists every window with geometry:
```
0x01a0000d  0 2493 74 1200 800 host  Title
# id        desk x    y  w    h
```
The pet polls this on a slow timer (~0.5 s) and parses it into rectangles.
Coordinates are X screen pixels, matching Qt's `move()` under XWayland (xcb), so
no coordinate remapping is needed. (KWin scripting is used elsewhere for
*acting* on windows, but it can't easily *return* geometry to Python; wmctrl is
the read path.)

**Filtering** (ignore): our own pet windows (title starts `claude-pet-`), the
desktop/panels (zero/huge or off-screen rects), and — v1 — windows not plausibly
on the visible screen. Keep it forgiving; a bad row is skipped, never fatal.

## New module `src/windows.py` (pure where possible)

```
Win = namedtuple("Win", "wid x y w h title")

parse_wmctrl_lg(text) -> list[Win]        # PURE — parse `wmctrl -lG` output
list_windows(exclude_prefix="claude-pet-", # runs wmctrl (best-effort, [] on fail)
             screen=None) -> list[Win]
window_at(px, py, wins) -> Win | None      # PURE — topmost window under a point
top_surface_under(cx, wins, screen_floor)  # PURE — highest window-top edge under
    -> float                               #        column cx, else screen_floor
```
`parse_*`, `window_at`, `top_surface_under` are pure and unit-tested. Only
`list_windows` shells out (guarded; returns `[]` when wmctrl absent → gating).

## Pet behavior

New `Pet` state: `self._wins = []` (last poll), `self._contain = None`
(a `Win` when contained, else None). A `QTimer` polls `windows.list_windows`
every ~500 ms into `self._wins`; if `_contain` is set, it is refreshed to the
current geometry of that window id (follow); if that id is gone, detach.

1. **Perch (passive).** When on the desktop (not contained) and roaming/falling,
   the effective floor at the creature's center-x is
   `top_surface_under(cx, self._wins, self.floor_y) - self.h`. So it lands on the
   nearest window top under it and walks along that edge; walking past the
   window's horizontal span drops it to the next surface / screen floor. Physics
   `advance` is called with this dynamic floor instead of the fixed one.

2. **Containment (drop-in).** On drag-release, if the drop point is inside a
   window (`window_at`), set `self._contain = win`; the pet's roaming/physics
   bounds (left/right/floor/top) become that window's rect. It roams inside and
   is redrawn to follow the window each poll. Right-click menu gains
   **"창에서 꺼내기"** to detach (`_contain = None` → back to desktop).

3. **Drag into a window** is just the drop path of (2).

## Files touched
- `src/windows.py` (new) + `tests/test_windows.py`.
- `src/pet.py` — poll timer; dynamic floor in `_roam`/`_physics`; containment
  bounds; drag-release attach; follow/detach; menu item; a `_bounds()` helper
  returning `(left, right, top, floor)` for the current context (screen or
  contained window).
- `src/physics.py` — unchanged (already takes `top`/`floor_y`; the pet passes
  context-dependent bounds).

## Out of scope (v1)
- Multi-monitor correctness (separate `feat/multimonitor`).
- Snapping to a window's exact title-bar height / decorations.
- Perching under Wayland-native (non-X) windows invisible to wmctrl — those are
  just ignored (pet walks "through" their screen region on the floor).
- Reconciling rapid window motion (poll lag is acceptable).

## Verification
- Unit: `parse_wmctrl_lg` on sample output; `window_at` / `top_surface_under`
  geometry math; `list_windows` returns `[]` without wmctrl (gating).
- Manual (KDE): small terminal on screen → pet walks onto its top edge; drag the
  pet into a window → it stays inside and follows the window; "창에서 꺼내기"
  releases it; close the contained window → pet drops back to desktop.
