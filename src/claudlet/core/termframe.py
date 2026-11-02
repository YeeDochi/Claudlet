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


def write(session_id, frame, x, gone=False):
    """한 장을 내보낸다. frame = encode() 결과, x = 띠 안에서 0..1 위치.
    gone 이면 띠에서 사라지라는 뜻."""
    body = {"ts": time.time(), "gone": bool(gone or frame is None)}
    if frame is not None and not gone:
        body.update(columns=frame[0], rows=frame[1], cells=frame[2],
                    x=max(0.0, min(1.0, x)))
    path = frame_file(session_id)
    tmp = path + ".tmp"
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(body, f)
        os.replace(tmp, path)
        return True
    except OSError:
        return False
