"""펫↔컴패니언 합동동작(소셜)의 순수 결정·배치 로직.

pet.py 소셜 디렉터가 idle+컴패니언일 때 should_start/pick으로 act를 고르고,
arrange로 각 컴패니언의 목표(위치/방향/포즈)를 받아 몰고 간다. GUI 무관, 데이터 테스트.
"""

ACTS = ("glance", "lineup", "stack", "highfive")
START_CHANCE = 0.03      # 적격 idle 틱당 발동 확률(~20fps에서 평균 ~1.7초에 한 번 시도)
COOLDOWN = 25.0          # act 사이 최소 간격(초)
GAP = 6                  # 정렬/근접 간격(device px, pet.py가 넘김)
DURATION = {"glance": 1.6, "lineup": 3.5, "stack": 3.5, "highfive": 2.0}


def should_start(roll, cooldown_ok):
    return bool(cooldown_ok and roll < START_CHANCE)


def pick(roll, n_companions):
    if n_companions < 1:
        return None
    idx = min(len(ACTS) - 1, int(roll * len(ACTS)))
    return ACTS[idx]


def _face(from_x, to_x):
    return 1 if to_x >= from_x else -1


def arrange(act, leader, companions, creature_h, gap=GAP, foot=0.0, head=0.0):
    """각 컴패니언의 Target=(tx, ty, facing, pose)를 companions 순서대로."""
    lx, ly, lw = leader
    lcx = lx + lw / 2.0
    out = []
    if act == "glance":                       # 이동 없이 리더를 마주봄
        for (x, y, w) in companions:
            out.append((x, y, _face(x + w / 2.0, lcx), "idle"))
        return out
    if act == "lineup":                       # 리더 뒤쪽으로 가로 정렬, 지상 유지, 쉼
        side = -1 if (companions and companions[0][0] < lcx) else 1
        cur = lx - gap if side < 0 else lx + lw + gap
        for (x, y, w) in companions:
            tx = cur - w if side < 0 else cur
            out.append((tx, y, _face(tx + w / 2.0, lcx), "settle"))
            cur = (tx - gap) if side < 0 else (tx + w + gap)
        return out
    if act == "stack":
        return arrange_pocket(leader, companions, creature_h, foot, head)
    if act == "highfive":                     # 가장 가까운 1마리만 붙어서 팔 듦
        near = min(range(len(companions)),
                   key=lambda i: abs(companions[i][0] + companions[i][2] / 2.0 - lcx))
        for i, (x, y, w) in enumerate(companions):
            if i == near:
                side = _face(lcx, x + w / 2.0)          # 리더 반대쪽에서 붙음
                tx = lx + lw + gap if side > 0 else lx - gap - w
                out.append((tx, y, _face(tx + w / 2.0, lcx), "wave"))
            else:
                out.append((x, y, _face(x + w / 2.0, lcx), "idle"))
        return out
    return [(x, y, 1, "idle") for (x, y, w) in companions]


def arrange_pocket(leader, companions, creature_h, foot, head, gap=0.0,
                   drop=12.0, inset=6.0, shift=0.5):
    """고정 주머니 배치: 1명 중앙, 2명 나란히, 3명 피라미드."""
    lx, ly, lw = leader
    lcx = lx + lw / 2.0 + shift
    base = ly + head - foot + drop

    def row(items, y):
        total = sum(w for _x, _y, w in items) + gap * max(0, len(items) - 1)
        x = lcx - total / 2.0
        targets = []
        for _old_x, _old_y, w in items:
            targets.append((x, y, 1, "idle"))
            x += w + gap
        return targets

    bottom = companions[:2] if len(companions) == 3 else companions
    out = row(bottom, base)
    if len(bottom) == 2:
        out[0] = (out[0][0] + inset, *out[0][1:])
        out[1] = (out[1][0] - inset, *out[1][1:])
    if len(companions) == 3:
        out += row(companions[2:], base - creature_h)
    return out
