from claudlet.core import follow_nav as N
from claudlet.core import physics
from claudlet.platform import geom as W

BOX = N.Box(120, 105, 89)


def _arc_landing_x(vx0, vy0, dy, steps=300):
    """Fly the REAL physics (no walls/floor) from (0,0); x at the first
    descending crossing of height dy, or None if never reached."""
    x = y = 0.0
    vx, vy = vx0, vy0
    py = 0.0
    for _ in range(steps):
        vy = min(max(vy + physics.GRAVITY, -physics.V_MAX), physics.V_MAX)
        x += vx
        y += vy
        vx *= physics.AIR_DRAG
        if y >= dy and y > py and vy > 0:
            return x
        py = y
    return None


def test_reach_envelope_follows_jump_strength():
    dx_max, dy_max = N.reach_envelope()
    assert abs(dy_max - N.VY_JUMP ** 2 / (2 * physics.GRAVITY)) < 1e-6
    assert abs(dx_max - N.VX_JUMP * 2 * N.VY_JUMP / physics.GRAVITY) < 1e-6
    assert N.VY_JUMP <= physics.V_MAX


def test_jump_velocity_lands_on_target():
    # representative targets: up-right, level gap, high, down-right, up-left
    for dx, dy in [(120, -100), (200, 0), (60, -180), (150, 120), (-140, -50)]:
        v = N.jump_velocity(dx, dy)
        assert v is not None, (dx, dy)
        vx0, vy0 = v
        assert abs(vx0) <= N.VX_JUMP and -N.VY_JUMP - 1 <= vy0 < 0
        lx = _arc_landing_x(vx0, vy0, dy)
        assert lx is not None, (dx, dy)
        # one integration step moves up to VX_JUMP px -> that is the error bound
        assert abs(lx - dx) <= N.VX_JUMP + 2, (dx, dy, lx)


def test_jump_velocity_none_when_above_apex():
    _, dy_max = N.reach_envelope()
    assert N.jump_velocity(0, -(dy_max + 20)) is None


def test_jump_velocity_none_when_too_far_sideways():
    assert N.jump_velocity(700, 0) is None


def test_jump_velocity_escalates_to_full_arc_for_long_level_jumps():
    # 400px level gap needs the full-strength arc (the low "pretty" arc
    # can't carry that far) -- must escalate instead of returning None.
    v = N.jump_velocity(400, 0)
    assert v is not None
    vx0, vy0 = v
    assert abs(vy0) > N.VY_JUMP * 0.9      # full-strength launch
    lx = _arc_landing_x(vx0, vy0, 0)
    assert lx is not None and abs(lx - 400) <= N.VX_JUMP + 2


SL, SR, SB = 0, 1600, 1000          # test screen: left, right, bottom
FLOOR_FEET = SB - (BOX.h - BOX.foot_y)   # 984


def test_floor_and_inside_feet():
    assert N.floor_feet(SB, BOX) == FLOOR_FEET
    win = W.Win("w1", 100, 400, 600, 500, "code", 1)      # bottom at 900
    assert N.inside_feet(win, BOX) == 900 - (BOX.h - BOX.foot_y)  # 884


def test_current_surface_floor_top_inside():
    win = W.Win("w1", 100, 400, 600, 500, "code", 1)
    # bare floor
    s = N.current_surface(400, FLOOR_FEET, None, [], SB, SL, SR, BOX)
    assert s.kind == "floor" and s.y == FLOOR_FEET and (s.left, s.right) == (SL, SR)
    # feet on the window's top edge
    s = N.current_surface(400, 400.0, None, [win], SB, SL, SR, BOX)
    assert s.kind == "top" and s.win.wid == "w1" and s.y == 400.0
    assert (s.left, s.right) == (100, 700)
    # contained
    s = N.current_surface(400, 800.0, win, [win], SB, SL, SR, BOX)
    assert s.kind == "inside" and s.win.wid == "w1"
    assert s.y == N.inside_feet(win, BOX) and (s.left, s.right) == (100, 700)


def test_target_place_inside_window():
    win = W.Win("w1", 100, 400, 600, 500, "code", 1)
    t = N.target_place(300, 600, [win], SB, SL, SR, BOX)
    assert t == ("inside", win)


def test_target_place_spot_on_surface_below_cursor():
    win = W.Win("w1", 100, 400, 600, 500, "code", 1)
    # cursor in open air ABOVE the window -> the spot is on that window's top
    kind, ax, ay, twin = N.target_place(300, 200, [win], SB, SL, SR, BOX)
    assert kind == "spot" and ay == 400.0 and twin.wid == "w1" and ax == 300
    # cursor over bare floor -> spot on the screen floor
    kind, ax, ay, twin = N.target_place(1200, 500, [win], SB, SL, SR, BOX)
    assert kind == "spot" and ay == FLOOR_FEET and twin is None
    # aim x is clamped so the pet's centre stays on-screen
    kind, ax, _ay, _ = N.target_place(5, 500, [], SB, SL, SR, BOX)
    assert ax == SL + BOX.w / 2.0


def _plan(x, y, contain, wins, cx_cursor, cy_cursor):
    return N.plan_move(x, y, BOX, contain, wins, SL, SR, SB,
                       cx_cursor, cy_cursor)


def _floor_y():
    return FLOOR_FEET - BOX.foot_y      # pet-window y when feet on the floor


def test_plan_flat_floor_walks_never_jumps():
    i = _plan(100, _floor_y(), None, [], 1200, 990)
    assert i[0] == "walk" and i[1] > 100 + BOX.w / 2.0


def test_plan_arrived_when_under_cursor():
    x = 400
    i = _plan(x, _floor_y(), None, [], x + BOX.w // 2, 990)
    assert i == ("arrived",)


def test_plan_strains_when_cursor_high_above_bare_floor():
    x = 400
    i = _plan(x, _floor_y(), None, [], x + BOX.w // 2, 300)
    assert i == ("strain",)


def test_plan_jumps_to_window_top_gap():
    w1 = W.Win("w1", 100, 400, 600, 600, "code", 1)
    w2 = W.Win("w2", 760, 400, 300, 300, "code", 2)
    # perched near w1's right edge (cx=620), cursor inside w2 across the gap:
    # the aim point (~200px away) is within drag-corrected jump reach -> leap.
    i = _plan(560, 400 - BOX.foot_y, None, [w1, w2], 800, 480)
    assert i[0] == "jump" and i[1] > 0 and i[2] < 0
    # a target beyond even the interior-aim reach (~760px off) -> walk closer
    w3 = W.Win("w3", 1100, 400, 300, 300, "code", 3)
    i = _plan(340, 400 - BOX.foot_y, None, [w1, w3], 1150, 480)
    assert i[0] == "walk" and i[1] > 400


def test_plan_drop_in_enter_from_own_top():
    w1 = W.Win("w1", 100, 400, 600, 500, "code", 1)
    i = _plan(340, 400 - BOX.foot_y, None, [w1], 400, 500)
    assert i == ("enter", w1)


def test_plan_walk_in_enter_from_floor_level():
    # window reaching the screen floor: its interior floor == the pet's floor,
    # so a pet standing "in front of" it just steps in sideways.
    w1 = W.Win("w1", 600, 700, 400, 300, "code", 1)      # bottom at SB
    i = _plan(590, _floor_y(), None, [w1], 700, 800)     # cx=650, in span
    assert i == ("enter", w1)


def test_plan_no_walk_in_when_interior_floor_above_feet():
    # floating window: interior floor well above the pet's feet -> must NOT
    # pop in from below; it aims for the top instead (here unreachable ->
    # strain, since the top is beyond the apex and the cursor is above).
    w1 = W.Win("w1", 200, 300, 500, 300, "code", 1)      # body 300..600
    i = _plan(390, _floor_y(), None, [w1], 450, 450)     # cx=450 under it
    assert i[0] == "strain"


def test_plan_climbs_down_when_spot_below_within_span():
    w1 = W.Win("w1", 100, 400, 600, 500, "code", 1)      # bottom 900 < floor
    # cursor below the window bottom, in its column, over bare floor
    i = _plan(340, 400 - BOX.foot_y, None, [w1], 400, 950)
    assert i == ("climbdown",)


def test_plan_walks_to_edge_then_jumps_off_for_below_outside():
    w1 = W.Win("w1", 100, 400, 600, 600, "code", 1)
    y = 400 - BOX.foot_y
    # cursor on the floor beyond w1's right edge: far from the edge -> walk
    i = _plan(340, y, None, [w1], 900, 990)              # cx=400
    assert i[0] == "walk" and abs(i[1] - 700) <= 1
    # at the edge -> jump off toward the floor spot
    i = _plan(700 - BOX.w // 2, y, None, [w1], 900, 990)  # cx=700
    assert i[0] == "jump" and i[1] > 0


def test_plan_waypoint_climbs_an_intermediate_step():
    # target window's top is beyond one jump from the floor, but a mid-height
    # window top is in range and gains height -> jump the stepping stone.
    hi = W.Win("hi", 200, 660, 500, 140, "code", 1)      # body 660..800
    mid = W.Win("mid", 150, 850, 600, 150, "code", 2)    # top 850, in reach
    i = _plan(340, _floor_y(), None, [hi, mid], 400, 700)  # cursor inside hi
    assert i[0] == "jump" and i[2] < 0 and abs(i[1]) < 3.0  # near-vertical hop


def test_plan_walks_within_contained_window():
    w1 = W.Win("w1", 100, 400, 600, 500, "code", 1)
    y = N.inside_feet(w1, BOX) - BOX.foot_y
    i = _plan(200, y, w1, [w1], 600, 500)                # cursor inside w1 too
    assert i[0] == "walk" and i[1] == 600


def test_plan_climbs_down_out_of_contained_window_when_target_below():
    # exiting DOWNWARD out of a window is a descent, never a jump: climb
    # down through the bottom, fall, continue on the floor.
    w1 = W.Win("w1", 100, 400, 600, 500, "code", 1)      # bottom 900 < floor
    y = N.inside_feet(w1, BOX) - BOX.foot_y
    i = _plan(630, y, w1, [w1], 900, 990)                # cursor on the floor
    assert i == ("climbdown",)


def test_plan_jumps_out_of_contained_window_toward_higher_target():
    # exiting UPWARD (cursor in a higher window) is still a jump.
    w1 = W.Win("w1", 100, 700, 600, 300, "code", 1)      # bottom = SB
    w2 = W.Win("w2", 760, 850, 300, 150, "code", 2)      # top above w1 floor
    y = N.inside_feet(w1, BOX) - BOX.foot_y
    i = _plan(630, y, w1, [w1, w2], 800, 900)            # cursor inside w2
    assert i[0] == "jump" and i[1] > 0


def test_jump_velocity_always_launches_a_real_leap():
    # even tiny hops launch with a hearty, throw-like arc -- no skimming
    # micro-parabolas that graze the ledges they aim for.
    vx0, vy0 = N.jump_velocity(60, 0)
    assert abs(vy0) >= N.MIN_LAUNCH - physics.GRAVITY


def _land(x, y, wins, cx_cursor, cy_cursor):
    return N.resolve_landing(x, y, BOX, wins, SB, SL, SR,
                             cx_cursor, cy_cursor)


def test_landing_on_target_top_enters():
    w2 = W.Win("w2", 760, 400, 300, 300, "code", 2)
    r = _land(800 - BOX.w // 2, 400 - BOX.foot_y, [w2], 800, 480)
    assert r == ("enter", w2)


def test_landing_on_nontarget_top_perches():
    w2 = W.Win("w2", 760, 400, 300, 300, "code", 2)
    # cursor moved away mid-arc -> the same landing is now just a perch
    r = _land(800 - BOX.w // 2, 400 - BOX.foot_y, [w2], 100, 990)
    assert r == ("perch", w2)


def test_landing_inside_target_body_enters():
    w1 = W.Win("w1", 600, 700, 400, 300, "code", 1)      # reaches the floor
    r = _land(640, FLOOR_FEET - BOX.foot_y, [w1], 700, 800)
    assert r == ("enter", w1)


def test_landing_on_bare_floor():
    r = _land(400, FLOOR_FEET - BOX.foot_y, [], 500, 990)
    assert r == ("floor",)


def test_plan_jumps_into_window_hovering_above_panel():
    # real KDE windows float ~40px above the screen bottom (panel), so the
    # walk-in tolerance misses them and the top edge is beyond the apex.
    # The pet must still get in: aim INTO the body (interior floor) and jump.
    w1 = W.Win("w1", 300, SB - 400, 400, 360, "code", 1)   # bottom SB-40
    i = _plan(340, _floor_y(), None, [w1], 450, SB - 200)  # cx=400, in span
    assert i[0] == "jump" and i[2] < 0


def test_midflight_enter_triggers_inside_target_body():
    w1 = W.Win("w1", 300, SB - 400, 400, 360, "code", 1)
    # airborne with the feet inside the cursor's window -> enter it now
    y = (SB - 100) - BOX.foot_y                            # feet at SB-100
    assert N.midflight_enter(340, y, BOX, [w1], 450, SB - 200) == w1
    # cursor elsewhere -> never enter mid-flight
    assert N.midflight_enter(340, y, BOX, [w1], 100, 990) is None
    # feet outside the window body -> not yet
    y = (SB - 500) - BOX.foot_y                            # feet above the top
    assert N.midflight_enter(340, y, BOX, [w1], 450, SB - 200) is None
