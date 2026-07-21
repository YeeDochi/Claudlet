from claudlet.core import social


def test_should_start_gated_by_chance_and_cooldown():
    assert social.should_start(0.0, True) is True
    assert social.should_start(social.START_CHANCE + 0.1, True) is False
    assert social.should_start(0.0, False) is False       # 쿨다운 중


def test_pick_none_without_companions():
    assert social.pick(0.5, 0) is None


def test_pick_returns_an_act():
    assert social.pick(0.5, 2) in social.ACTS


def test_arrange_stack_piles_upward():
    leader = (100.0, 200.0, 40.0)
    comps = [(0.0, 200.0, 20.0), (0.0, 200.0, 20.0)]
    tgts = social.arrange("stack", leader, comps, creature_h=30.0, foot=44.0, head=25.0)
    base = 200.0 + 25.0 - 44.0                            # 발이 리더 머리에 닿는 창-top
    assert tgts[0][0] == 100.0 + 40.0 / 2 - 20.0 / 2      # x 리더 중심 정렬
    assert tgts[0][1] == base                             # 1층
    assert tgts[1][1] == base - 30.0                      # 2층(몸통 높이만큼 위)


def test_arrange_lineup_spaces_horizontally():
    leader = (100.0, 200.0, 40.0)
    comps = [(0.0, 200.0, 20.0), (0.0, 200.0, 20.0)]
    tgts = social.arrange("lineup", leader, comps, creature_h=30.0, gap=6)
    xs = [t[0] for t in tgts]
    assert abs(abs(xs[1] - xs[0]) - (20.0 + 6)) < 1e-6     # w+gap 간격
    assert all(t[3] == "settle" for t in tgts)             # 쉼 포즈


def test_arrange_glance_faces_leader_no_move():
    leader = (100.0, 200.0, 40.0)
    comps = [(0.0, 200.0, 20.0)]      # 리더보다 왼쪽 -> 오른쪽(+1) 향함
    (tx, ty, facing, pose), = social.arrange("glance", leader, comps, creature_h=30.0)
    assert (tx, ty) == (0.0, 200.0)   # 이동 없음
    assert facing == 1 and pose == "idle"


def test_arrange_highfive_moves_nearest_only():
    leader = (100.0, 200.0, 40.0)
    comps = [(90.0, 200.0, 20.0), (300.0, 200.0, 20.0)]   # 0번이 더 가까움
    tgts = social.arrange("highfive", leader, comps, creature_h=30.0)
    assert tgts[0][3] == "wave"                # 가까운 놈이 하이파이브
    assert tgts[1][3] == "idle"                # 먼 놈은 대기
    assert tgts[1][0] == 300.0                 # 먼 놈 이동 없음
