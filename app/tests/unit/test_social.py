from claudlet.core import social


def test_should_start_gated_by_chance_and_cooldown():
    assert social.should_start(0.0, True) is True
    assert social.should_start(social.START_CHANCE + 0.1, True) is False
    assert social.should_start(0.0, False) is False       # 쿨다운 중


def test_pick_none_without_companions():
    assert social.pick(0.5, 0) is None


def test_pick_returns_an_act():
    assert social.pick(0.5, 2) in social.ACTS


def test_arrange_stack_reuses_pyramid_layout():
    leader = (100.0, 200.0, 40.0)
    comps = [(0.0, 200.0, 20.0), (0.0, 200.0, 20.0)]
    tgts = social.arrange("stack", leader, comps, creature_h=30.0, foot=44.0, head=25.0)
    assert tgts == social.arrange_pocket(
        leader, comps, creature_h=30.0, foot=44.0, head=25.0)


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


def test_arrange_pocket_centres_pairs_and_builds_pyramid():
    leader = (100.0, 200.0, 100.0)
    comp = (0.0, 0.0, 20.0)
    one = social.arrange_pocket(leader, [comp], 30.0, 40.0, 20.0)
    two = social.arrange_pocket(leader, [comp] * 2, 30.0, 40.0, 20.0)
    three = social.arrange_pocket(leader, [comp] * 3, 30.0, 40.0, 20.0)
    assert [t[0] for t in one] == [140.5]                 # 중앙에서 우측 0.5px
    assert [t[0] for t in two] == [136.5, 144.5]          # 안쪽으로 6px
    assert [t[0] for t in three] == [136.5, 144.5, 140.5] # 위층은 중앙
    assert three[2][1] == three[0][1] - 30.0              # 피라미드 꼭대기
    assert one[0][1] == 192.0                              # 전체를 아래로 12px
