from claudlet.core import dock

SCREEN = (0, 0, 1920, 1080)      # 주 모니터 작업영역
SIZE = (120, 105)                # 펫 창 (GRID_W+2)*U x (GRID_H+4)*U


def test_slot0_sits_in_the_bottom_right_corner():
    x, y = dock.slot_position(SCREEN, SIZE, 0)
    assert (x, y) == (1920 - 120, 1080 - 105)


def test_slots_line_up_leftwards_without_overlapping():
    xs = [dock.slot_position(SCREEN, SIZE, n)[0] for n in range(4)]
    ys = [dock.slot_position(SCREEN, SIZE, n)[1] for n in range(4)]
    assert ys == [ys[0]] * 4                        # 같은 줄
    assert xs == sorted(xs, reverse=True)           # 오른쪽 -> 왼쪽
    gaps = [xs[i] - xs[i + 1] for i in range(3)]
    assert gaps == [124.0] * 3                      # 창폭 120 + gap 4
    assert min(gaps) >= SIZE[0]                     # 겹치지 않는다


def test_other_anchors_flip_the_growth_direction():
    x, y = dock.slot_position(SCREEN, SIZE, 0, anchor="top-left")
    assert (x, y) == (0.0, 0.0)
    x1, _ = dock.slot_position(SCREEN, SIZE, 1, anchor="top-left")
    assert x1 == 124.0                              # 왼쪽 앵커는 오른쪽으로 자란다


def test_unknown_anchor_falls_back_to_bottom_right():
    assert (dock.slot_position(SCREEN, SIZE, 0, anchor="sideways")
            == dock.slot_position(SCREEN, SIZE, 0))


def test_a_full_row_wraps_to_the_next_row_instead_of_running_off_screen():
    n = dock.per_row(SCREEN[2], SIZE[0])
    first_of_next_row = dock.slot_position(SCREEN, SIZE, n)
    assert first_of_next_row[0] == dock.slot_position(SCREEN, SIZE, 0)[0]
    assert first_of_next_row[1] < dock.slot_position(SCREEN, SIZE, 0)[1]
    # 화면 밖으로 새지 않는다
    assert all(dock.slot_position(SCREEN, SIZE, k)[0] >= 0 for k in range(n))


def test_per_row_does_not_waste_an_exactly_fitting_slot():
    # 폭 244 = 120 + 4 + 120 -> 마지막 펫 뒤에는 gap이 필요 없으므로 딱 2마리
    assert dock.per_row(244, 120, 4) == 2
    assert dock.per_row(243, 120, 4) == 1
    assert dock.per_row(10, 120, 4) == 1            # 창보다 좁아도 최소 1


def test_offset_shifts_the_whole_row_by_the_same_amount():
    base = [dock.slot_position(SCREEN, SIZE, n) for n in range(3)]
    moved = [dock.slot_position(SCREEN, SIZE, n, offset=(-40.0, -12.0))
             for n in range(3)]
    assert all(m == (b[0] - 40.0, b[1] - 12.0) for b, m in zip(base, moved))


def test_offset_for_is_the_inverse_of_slot_position():
    dropped = (700.0, 400.0)
    off = dock.offset_for(SCREEN, SIZE, 2, dropped)
    assert dock.slot_position(SCREEN, SIZE, 2, offset=off) == dropped


def test_dragging_one_pet_keeps_its_neighbours_spaced():
    off = dock.offset_for(SCREEN, SIZE, 1, (500.0, 300.0))
    xs = [dock.slot_position(SCREEN, SIZE, n, offset=off)[0] for n in range(3)]
    assert xs[1] == 500.0
    assert xs[0] - xs[1] == 124.0 and xs[1] - xs[2] == 124.0


def test_clamp_point_keeps_a_sliver_on_screen():
    x, y = dock.clamp_point(-5000, -5000, SIZE, SCREEN, margin=24.0)
    assert x == 24.0 - SIZE[0] and y == 24.0 - SIZE[1]
    x, y = dock.clamp_point(9999, 9999, SIZE, SCREEN, margin=24.0)
    assert x == 1920 - 24.0 and y == 1080 - 24.0


def test_clamp_point_leaves_an_on_screen_position_alone():
    assert dock.clamp_point(300.0, 400.0, SIZE, SCREEN) == (300.0, 400.0)
