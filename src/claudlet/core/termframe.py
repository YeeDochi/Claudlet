"""펫 그림 한 장을 터미널 칸으로 — mod 가 프롬프트 위 띠에 `Raster` 로 그린다.

한 칸에 세로 두 픽셀을 담는다(반 블록 `▀`: 글자색=위, 배경색=아래). 투명한
픽셀은 터미널 기본색(0x01000000)이라 띠 배경이 비쳐 보인다. 순수 — Qt 없이
테스트한다. 그림을 뽑는 쪽(QImage → 픽셀)은 pet.py 의 얇은 껍데기다.

`claude-code` 타입의 RasterProps: cells 는 `columns*rows` 개의 little-endian u32
세 개 묶음 `[codePoint, fg, bg]` 을 base64 로.
"""
import base64
import json
import os
import struct
import time

from claudlet.core import hostinfo

UPPER, LOWER = 0x2580, 0x2584     # ▀ ▄
DEFAULT = 0x01000000              # 터미널 기본색
ALPHA_MIN = 128                   # 이보다 투명하면 빈 픽셀로 본다


def _rgb(argb):
    """ARGB32 정수 하나 → 0xRRGGBB, 투명이면 None."""
    if (argb >> 24) & 0xFF < ALPHA_MIN:
        return None
    return argb & 0xFFFFFF


def cell(top, bottom):
    """위·아래 픽셀(0xRRGGBB 또는 None) → (codePoint, fg, bg)."""
    if top is None and bottom is None:
        return (0x20, DEFAULT, DEFAULT)
    if top is None:
        return (LOWER, bottom, DEFAULT)
    return (UPPER, top, DEFAULT if bottom is None else bottom)


def crop_box(width, height, pixels):
    """투명하지 않은 픽셀을 감싸는 (x0, y0, x1, y1), 다 비었으면 None.
    크리처 그리드에는 소품 자리로 빈 줄이 있다 — 띠의 줄은 귀하다."""
    xs, ys = [], []
    for y in range(height):
        for x in range(width):
            if _rgb(pixels[y * width + x]) is not None:
                xs.append(x)
                ys.append(y)
    if not xs:
        return None
    return min(xs), min(ys), max(xs) + 1, max(ys) + 1


def encode(width, height, pixels):
    """ARGB 픽셀(행 우선 목록) → (columns, rows, cells base64). 빈 그림은 None."""
    box = crop_box(width, height, pixels)
    if box is None:
        return None
    x0, y0, x1, y1 = box
    cols, rows = x1 - x0, (y1 - y0 + 1) // 2
    words = []
    for r in range(rows):
        for c in range(cols):
            x, y = x0 + c, y0 + 2 * r
            top = _rgb(pixels[y * width + x])
            bottom = _rgb(pixels[(y + 1) * width + x]) if y + 1 < y1 else None
            words.extend(cell(top, bottom))
    raw = struct.pack("<%dI" % len(words), *words)
    return cols, rows, base64.b64encode(raw).decode("ascii")


def frame_file(session_id):
    sid = session_id or "default"
    return os.path.join(hostinfo.runtime_dir(), "claudlet-{}.frame".format(sid))


def write(session_id, frame, x, gone=False, y=0.0):
    """한 장을 내보낸다. frame = encode() 결과, x = 띠 안에서 0..1 위치,
    y = 바닥에서 뜬 높이 0..1. gone 이면 띠에서 사라지라는 뜻."""
    body = {"ts": time.time(), "gone": bool(gone or frame is None)}
    if frame is not None and not gone:
        body.update(columns=frame[0], rows=frame[1], cells=frame[2],
                    x=max(0.0, min(1.0, x)), y=max(0.0, min(1.0, y)))
    path = frame_file(session_id)
    tmp = path + ".tmp"
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(body, f)
        os.replace(tmp, path)
        return True
    except OSError:
        return False


# ---------- 띠 안에서의 몸짓: 순수 ----------
# t = {"phase", "since", "dur", "x", "dir", "y"}. y 는 띠 바닥에서 뜬 높이(0..1),
# mod 가 LIFT 줄 안에서 위아래로 옮긴다. 일하는 중이면 제자리에서 그 일을 한다.

SPEED = 0.01                       # 띠 너비 비율 / 틱
FALL_S, JUMP_S, LEAVE_S = 0.5, 0.8, 0.6


def new_visit(now, rnd):
    """떨어지며 들어온다."""
    return {"phase": "enter", "since": now, "dur": FALL_S, "x": rnd(),
            "dir": -1 if rnd() < 0.5 else 1, "y": 1.0}


def _next(t, now, rnd):
    """걷기·멈춰 두리번·점프 중 하나를 고른다."""
    r = rnd()
    if r < 0.55:
        t.update(phase="walk", dur=2.0 + 3.0 * rnd())
    elif r < 0.85:
        t.update(phase="pause", dur=1.5 + 2.0 * rnd(),
                 look="observe" if rnd() < 0.5 else "idle")
        if rnd() < 0.4:
            t["dir"] = -t["dir"]          # 뒤돌아본다
    else:
        t.update(phase="jump", dur=JUMP_S)
    t["since"] = now


def step(t, now, working, state, rnd):
    """한 틱. (그릴 상태, 끝났나) 를 돌려주고 t 를 고친다."""
    k = min(1.0, (now - t["since"]) / t["dur"]) if t["dur"] else 1.0
    phase = t["phase"]
    if phase == "leave":                 # 위로 뛰어 사라진다
        t["y"] = min(1.0, 2.0 * k)
        return "jump", k >= 1.0
    if phase == "enter":
        t["y"] = 1.0 - k * k             # 중력처럼 점점 빨리
        if k >= 1.0:
            _next(t, now, rnd)
        return "falling", False
    if working:
        t["y"] = 0.0
        return state, False
    if phase == "jump":
        t["y"] = 4 * k * (1 - k)         # 포물선
    else:
        t["y"] = 0.0
    if phase in ("walk", "jump"):
        t["x"] += t["dir"] * SPEED
        if not 0.0 <= t["x"] <= 1.0:
            t["dir"] = -t["dir"]
            t["x"] = min(max(t["x"], 0.0), 1.0)
    if k >= 1.0:
        _next(t, now, rnd)
    return {"walk": "walk", "jump": "jump"}.get(phase, t.get("look", "idle")), False


def leave(t, now):
    if t["phase"] != "leave":
        t.update(phase="leave", since=now, dur=LEAVE_S)


def shrink(width, height, pixels, n):
    """n×n 칸마다 가장 많은 색 하나로 — 정수 배라 도트가 고르게 남는다. 순수.
    반 이상이 투명이면 투명. (루시엘 교훈: 최빈값 축소가 도트 느낌의 핵심)"""
    if n <= 1:
        return width, height, list(pixels)
    w, h = (width + n - 1) // n, (height + n - 1) // n
    out = []
    for by in range(h):
        for bx in range(w):
            counts, total, clear = {}, 0, 0
            for y in range(by * n, min(height, by * n + n)):
                for x in range(bx * n, min(width, bx * n + n)):
                    total += 1
                    px = pixels[y * width + x]
                    if _rgb(px) is None:
                        clear += 1
                    else:
                        counts[px] = counts.get(px, 0) + 1
            out.append(0 if clear * 2 > total or not counts
                       else max(counts, key=counts.get))
    return w, h, out


def factor(grid_h, max_h):
    """크리처 하나에 한 배율 — 자세마다 다르면 크기가 출렁인다. 순수."""
    return max(1, -(-grid_h // max_h))
