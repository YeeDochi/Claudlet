"""도크(고정 배치)의 순수 기하: 화면 코너를 기준으로 펫들을 겹치지 않게 세운다.

Qt도 파일 IO도 없는 순수 계산이라 데이터로 테스트된다(CLAUDE.md: behavior over
interaction). 역할 분담은 자리 하나당 슬롯 번호 하나 — *누가* 어떤 슬롯을 가질지는
dockslot.py(프로세스 간 잠금)가, 그 슬롯이 *화면 어디*인지는 여기가 정한다.

좌표는 모두 가상 데스크톱 픽셀, 사각형은 (x, y, w, h) 튜플.
"""

ANCHORS = ("bottom-right", "bottom-left", "top-right", "top-left")
DEFAULT_ANCHOR = "bottom-right"
DEFAULT_GAP = 4          # 펫 사이 간격(device px)
ROW_GAP = 4              # 줄이 넘칠 때 위/아래 줄 사이 간격


def _resolve(anchor):
    """앵커 이름 -> (오른쪽 기준인가, 아래쪽 기준인가). 모르는 값은 기본값."""
    if anchor not in ANCHORS:
        anchor = DEFAULT_ANCHOR
    vert, horiz = anchor.split("-")
    return horiz == "right", vert == "bottom"


def per_row(screen_w, win_w, gap=DEFAULT_GAP):
    """한 줄에 들어가는 펫 수(최소 1). 마지막 펫은 gap이 뒤따르지 않으므로
    (n*w + (n-1)*gap <= screen_w)을 푼다 — 단순히 screen_w // (w+gap)로 하면
    딱 맞아떨어지는 폭에서 한 마리를 괜히 다음 줄로 넘긴다."""
    step = win_w + gap
    if step <= 0:
        return 1
    return max(1, int((screen_w + gap) // step))


def slot_position(screen, size, slot, anchor=DEFAULT_ANCHOR, gap=DEFAULT_GAP,
                  offset=(0.0, 0.0)):
    """슬롯 번호 -> 펫 창의 좌상단 (x, y).

    slot 0이 앵커 코너에 붙고, 이후 슬롯은 코너 반대 방향으로 (창폭 + gap)씩
    밀려난다. 한 줄이 화면 폭을 넘어가면 다음 줄로 접는다: 계속 밀면 화면 밖으로
    나가고, 가장자리에 clamp하면 결국 처음 문제(겹침)로 되돌아간다.

    offset은 사용자가 드래그로 옮긴 **줄 전체**의 변위라서 모든 슬롯에 똑같이
    더해진다 — 한 마리를 끌면 대열이 통째로 따라오고 간격은 유지된다.
    """
    sx, sy, sw, sh = screen
    ww, wh = size
    to_right, to_bottom = _resolve(anchor)
    n = per_row(sw, ww, gap)
    col, row = int(slot) % n, int(slot) // n
    step_x = ww + gap
    step_y = wh + ROW_GAP
    x = (sx + sw - ww - col * step_x) if to_right else (sx + col * step_x)
    y = (sy + sh - wh - row * step_y) if to_bottom else (sy + row * step_y)
    return float(x) + float(offset[0]), float(y) + float(offset[1])


def offset_for(screen, size, slot, dropped, anchor=DEFAULT_ANCHOR,
               gap=DEFAULT_GAP):
    """slot_position의 역함수: 이 슬롯의 펫을 `dropped`에 놓으려면 필요한 offset.

    드래그로 대열을 옮길 때 쓴다 — 놓인 자리에서 그 슬롯의 기준 위치를 빼면
    나머지 슬롯에도 그대로 적용할 수 있는 공통 변위가 된다."""
    bx, by = slot_position(screen, size, slot, anchor, gap, (0.0, 0.0))
    return float(dropped[0]) - bx, float(dropped[1]) - by


def clamp_point(x, y, size, limit, margin=24.0):
    """창 좌상단 (x, y)를 `limit`(x, y, w, h) 안으로 되돌린다.

    창 전체를 가두지는 않는다: `margin`만큼만 걸쳐 있으면 통과시켜서, 화면 가장
    자리에 반쯤 걸친 배치는 허용하되 완전히 화면 밖으로 사라져 다시 못 잡는 상황만
    막는다."""
    lx, ly, lw, lh = limit
    ww, wh = size
    x = min(max(float(x), lx - ww + margin), lx + lw - margin)
    y = min(max(float(y), ly - wh + margin), ly + lh - margin)
    return x, y
