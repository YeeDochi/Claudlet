"""Pure cursor-follow navigation planner.

Each tick the pet asks: where is the cursor's PLACE (inside a window, or the
spot on the surface under the cursor), and what single move gets me closer --
walk along my surface, an aimed ballistic jump, enter the window, an in-place
strain hop (unreachable above), or a climb-down. No Qt, no Pet, no wall clock:
the caller passes positions, the pet's box, the window list and screen bounds,
and gets an intent tuple back. pet.py's follow branch is a thin adapter.

Design: docs/superpowers/specs/2026-07-13-jump-window-navigation-design.md.
"""
from collections import namedtuple

from claudlet.core import physics
from claudlet.platform import geom

# Jump strength (device px/tick); the reach envelope derives from these, so
# never launch an arc that can't land. Must stay <= physics.V_MAX. Tuned on
# hardware -- treat as provisional.
VY_JUMP = 24.0        # max upward launch speed
VX_JUMP = 14.0        # max horizontal launch speed
JUMP_MARGIN = 48.0    # the apex clears the target by at least this (px)
MIN_LAUNCH = 13.0     # weakest launch: every jump is a real, throw-like leap

X_ALIGN = 14          # cursor column considered "over" the pet
STRAIN_ABOVE = 10     # cursor this far above the pet's head -> strain-worthy
EDGE_STEP = 10.0      # within one walk step of a ledge = "at the edge"
SURF_TOL = 6          # feet-vs-surface tolerance (matches geom's support tol)
MIN_PROGRESS = 8.0    # a stepping-stone jump must gain at least this much

Box = namedtuple("Box", "w h foot_y")     # pet window dims + feet offset

# A resting surface for the pet's centre column. kind: floor | top | inside.
# y is the FEET height when standing on it; [left, right] the walkable span
# for the centre column.
Surface = namedtuple("Surface", "kind win y left right")


def reach_envelope(vy_jump=VY_JUMP, vx_jump=VX_JUMP, gravity=physics.GRAVITY):
    """(dx_max, dy_max) reachable by one jump: dy_max is the apex rise,
    dx_max the horizontal carry over a full up-and-down flight (drag ignored
    here -- jump_velocity re-checks precisely)."""
    dy_max = vy_jump * vy_jump / (2.0 * gravity)
    dx_max = vx_jump * 2.0 * vy_jump / gravity
    return dx_max, dy_max


def jump_velocity(dx, dy, vy_jump=VY_JUMP, vx_jump=VX_JUMP,
                  gravity=physics.GRAVITY, margin=JUMP_MARGIN):
    """Launch velocity (vx0, vy0) whose arc lands at (dx, dy) relative to the
    feet (screen coords: dy < 0 = above), or None when no arc within the
    strength limits gets there.

    Works in "effective" velocity vye = vy0 + g/2, which makes the discrete
    step sequence of physics.advance (gravity added BEFORE integrating) match
    the continuous formulas. vy clears the target by `margin` with at least
    MIN_LAUNCH strength (big natural throw-like arcs, no skimming), escalating
    once to full strength when the horizontal limit would be exceeded."""
    g = gravity
    rise = max(0.0, -dy) + margin
    vye = max(-max(((2.0 * g * rise) ** 0.5), MIN_LAUNCH), -vy_jump)
    for _ in range(2):
        if vye * vye / (2.0 * g) < -dy:      # apex can't clear the target
            return None
        disc = vye * vye + 2.0 * g * dy
        if disc < 0:
            return None
        t = (-vye + disc ** 0.5) / g          # descending crossing time
        if t < 1.0:
            return None
        k = physics.AIR_DRAG                  # horizontal travel with drag:
        travel = (1.0 - k ** t) / (1.0 - k)   # sum of k^i for i in [0, t)
        vx0 = dx / travel
        if abs(vx0) <= vx_jump:
            return vx0, vye - 0.5 * g
        vye = -vy_jump                        # stronger arc = more airtime
    return None


def floor_feet(screen_bottom, box):
    """Feet height when standing on the screen floor (the pet window is kept
    fully on-screen there, so the feet sit box.h - box.foot_y above it)."""
    return screen_bottom - (box.h - box.foot_y)


def inside_feet(win, box):
    """Feet height when standing on a window's interior floor (mirrors
    Pet._bounds' contained branch, including the short-window centring)."""
    if win.h < box.h:
        return win.y + (win.h - box.h) / 2.0 + box.foot_y
    return win.y + win.h - (box.h - box.foot_y)


def current_surface(cx, feet_y, contain, wins, screen_bottom,
                    screen_left, screen_right, box):
    """The Surface the pet's feet are resting on right now."""
    if contain is not None:
        c = contain
        return Surface("inside", c, inside_feet(c, box), c.x, c.x + c.w)
    s = geom.support_surface_under(cx, wins, screen_bottom, feet_y)
    if s < screen_bottom:
        hit = None                        # topmost-listed provider of this top
        for w in wins:
            if w.x <= cx <= w.x + w.w and w.y == s:
                hit = w
        return Surface("top", hit, float(s), hit.x, hit.x + hit.w)
    return Surface("floor", None, floor_feet(screen_bottom, box),
                   screen_left, screen_right)


def target_place(cursor_x, cursor_y, wins, screen_bottom,
                 screen_left, screen_right, box):
    """Where the cursor is: ("inside", win) when it is over a window;
    otherwise ("spot", ax, ay, win_or_None) -- the point ON the surface
    directly under the cursor (a window top, or the screen floor), with the
    aim x clamped so the pet's centre column stays within reach."""
    win = geom.window_at(cursor_x, cursor_y, wins)
    if win is not None:
        return ("inside", win)
    best, hit = screen_bottom, None       # first window top BELOW the cursor
    for w in wins:
        if w.x <= cursor_x <= w.x + w.w and cursor_y <= w.y < best:
            best, hit = w.y, w
    if hit is not None:
        ax = min(max(cursor_x, hit.x + 4), hit.x + hit.w - 4)
        return ("spot", ax, float(hit.y), hit)
    half = box.w / 2.0
    ax = min(max(cursor_x, screen_left + half), screen_right - half)
    return ("spot", ax, floor_feet(screen_bottom, box), None)


def _walk_or_arrived(cx, want_cx, cur):
    tx = min(max(want_cx, cur.left), cur.right)
    if abs(tx - cx) <= 1.0:
        return ("arrived",)
    return ("walk", tx)


def _waypoint(cx, feet_y, cur, ax, ay, wins, vy_jump, vx_jump):
    """Best stepping-stone jump toward (ax, ay): a reachable window top that
    makes real progress. Returns (vx0, vy0) or None."""
    dx_max, dy_max = reach_envelope(vy_jump, vx_jump)
    best, best_score = None, MIN_PROGRESS
    for w in wins:
        if cur.win is not None and w.wid == cur.win.wid:
            continue                      # the surface we're already on/in
        px = min(max(ax, w.x + 4), w.x + w.w - 4)
        py = float(w.y)
        ddx, ddy = px - cx, py - feet_y
        if abs(ddx) > dx_max or (ddy < 0 and -ddy > dy_max):
            continue
        if abs(ddx) <= X_ALIGN and abs(ddy) <= SURF_TOL:
            continue                      # lands where we already stand
        v = jump_velocity(ddx, ddy, vy_jump, vx_jump)
        if v is None:
            continue
        gain_x = abs(ax - cx) - abs(ax - px)
        gain_y = abs(ay - feet_y) - abs(ay - py)
        if gain_x < -X_ALIGN:
            continue                      # don't jump AWAY horizontally
        score = gain_x + gain_y
        if score > best_score:
            best, best_score = v, score
    return best


def _route(cx, feet_y, cur, ax, ay, wins, vy_jump, vx_jump):
    """Move toward an aim point on ANOTHER surface: jump when in reach,
    stepping-stone when not, walk closer when that helps, else strain."""
    dx, dy = ax - cx, ay - feet_y
    dx_max, dy_max = reach_envelope(vy_jump, vx_jump)

    # aim BELOW a window-top perch: climb down in place, or walk to the ledge
    # and hop off (an upward launch clears our own lip before descending).
    if dy > SURF_TOL and cur.kind == "top":
        if cur.left - EDGE_STEP <= ax <= cur.right + EDGE_STEP:
            if abs(dx) > X_ALIGN:
                return ("walk", min(max(ax, cur.left), cur.right))
            return ("climbdown",)
        edge = cur.left if ax < cur.left else cur.right
        if abs(cx - edge) > EDGE_STEP:
            return ("walk", edge)
        v = jump_velocity(dx, dy, vy_jump, vx_jump)
        if v is not None:
            return ("jump", v[0], v[1])
        return ("walk", edge)             # hug the ledge; replans as it moves

    v = None
    if abs(dx) <= dx_max and (dy >= 0 or -dy <= dy_max):
        v = jump_velocity(dx, dy, vy_jump, vx_jump)
    if v is not None:
        return ("jump", v[0], v[1])

    wp = _waypoint(cx, feet_y, cur, ax, ay, wins, vy_jump, vx_jump)
    if wp is not None:
        return ("jump", wp[0], wp[1])

    walk_tx = min(max(ax, cur.left), cur.right)   # approach-then-leap
    if abs(walk_tx - cx) > EDGE_STEP:
        return ("walk", walk_tx)

    if dy < -SURF_TOL:
        return ("strain",)                # unreachable above: reach for it
    return ("arrived",)                   # unreachable sideways: wait here


def plan_move(x, y, box, contain, wins, screen_left, screen_right,
              screen_bottom, cursor_x, cursor_y,
              vy_jump=VY_JUMP, vx_jump=VX_JUMP):
    """One follow intent for this tick. x, y are the pet window's top-left."""
    cx = x + box.w / 2.0
    feet_y = y + box.foot_y
    target = target_place(cursor_x, cursor_y, wins, screen_bottom,
                          screen_left, screen_right, box)
    cur = current_surface(cx, feet_y, contain, wins, screen_bottom,
                          screen_left, screen_right, box)

    if target[0] == "inside":
        win = target[1]
        if cur.kind == "inside" and cur.win.wid == win.wid:
            return _walk_or_arrived(cx, cursor_x, cur)     # follow within
        if cur.kind == "inside" and float(win.y) > cur.y + SURF_TOL:
            return ("climbdown",)          # exit DOWNWARD: descend, don't jump
        if cur.kind != "inside":
            if cur.kind == "top" and cur.win is not None \
                    and cur.win.wid == win.wid:
                return ("enter", win)      # drop in from the window's own top
            if (win.x <= cx <= win.x + win.w
                    and inside_feet(win, box) >= feet_y - SURF_TOL):
                return ("enter", win)      # interior floor at/below the feet:
                                           # step in sideways / fall in
        pad = min(box.w / 2.0, win.w / 2.0)
        ax = min(max(cursor_x, win.x + pad), win.x + win.w - pad)
        # prefer landing on the top edge (then drop in), but when the top is
        # out of reach, aim INTO the body at its interior floor -- walls don't
        # block flight, and midflight_enter contains the pet the moment its
        # feet pierce the target's rect (how a pet on the floor gets into a
        # window hovering just above the panel).
        dx_max, dy_max = reach_envelope(vy_jump, vx_jump)
        dxa, dya = ax - cx, float(win.y) - feet_y
        if abs(dxa) <= dx_max and (dya >= 0 or -dya <= dy_max):
            v = jump_velocity(dxa, dya, vy_jump, vx_jump)
            if v is not None:
                return ("jump", v[0], v[1])
        dyi = inside_feet(win, box) - feet_y
        if abs(dxa) <= dx_max and (dyi >= 0 or -dyi <= dy_max):
            v = jump_velocity(dxa, dyi, vy_jump, vx_jump)
            if v is not None:
                return ("jump", v[0], v[1])
        return _route(cx, feet_y, cur, ax, float(win.y), wins,
                      vy_jump, vx_jump)

    _kind, ax, ay, twin = target
    if cur.kind == "inside" and ay > cur.y + SURF_TOL:
        return ("climbdown",)              # exit DOWNWARD: descend, don't jump
    same = (cur.kind == "floor" and twin is None) or \
           (cur.kind == "top" and cur.win is not None and twin is not None
            and cur.win.wid == twin.wid)
    if same:
        intent = _walk_or_arrived(cx, ax, cur)
        if intent[0] == "arrived" and abs(cursor_x - cx) <= X_ALIGN \
                and cursor_y < (feet_y - box.foot_y) - STRAIN_ABOVE:
            return ("strain",)             # cursor dangling overhead, in vain
        return intent
    return _route(cx, feet_y, cur, ax, ay, wins, vy_jump, vx_jump)


def midflight_enter(x, y, box, wins, cursor_x, cursor_y):
    """While airborne on a follow-jump: the window to become contained in NOW,
    or None. Entering is only ever the CURSOR's window, and only once the
    feet are inside its body -- an arc aimed into a window converts to
    containment the moment it pierces the rect (so the interior floor can
    catch it), instead of sailing through and falling back out."""
    win = geom.window_at(cursor_x, cursor_y, wins)
    if win is None:
        return None
    cx = x + box.w / 2.0
    feet_y = y + box.foot_y
    if win.x <= cx <= win.x + win.w and win.y <= feet_y <= win.y + win.h:
        return win
    return None


def resolve_landing(x, y, box, wins, screen_bottom, screen_left, screen_right,
                    cursor_x, cursor_y):
    """What a settled follow-jump landed in/on. The target is re-read from the
    CURRENT cursor (it may have moved mid-arc): landing on/in the window the
    cursor is in -> ("enter", win); any other window top -> ("perch", win);
    else ("floor",)."""
    cx = x + box.w / 2.0
    feet_y = y + box.foot_y
    target = target_place(cursor_x, cursor_y, wins, screen_bottom,
                          screen_left, screen_right, box)
    if target[0] == "inside":
        win = target[1]
        if win.x <= cx <= win.x + win.w \
                and win.y - SURF_TOL <= feet_y <= win.y + win.h + SURF_TOL:
            return ("enter", win)         # feet on its top edge or in its body
    s = geom.support_surface_under(cx, wins, screen_bottom, feet_y)
    if s < screen_bottom:
        hit = None
        for w in wins:
            if w.x <= cx <= w.x + w.w and w.y == s:
                hit = w
        return ("perch", hit)
    return ("floor",)
