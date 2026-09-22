"""Where a speech bubble goes and how its text breaks.

Pure and Qt-free on purpose: placement is the part that actually goes wrong
(a bubble off the edge of the screen, or covering the creature it belongs to),
and that is arithmetic, not painting. `pet.py` owns the widget; this owns the
decisions, so they can be tested without a display.

The in-creature bubble prop (`core/creature.py`) is a fixed-size pixel drawing
for one canned word per state. An answer is arbitrary text of arbitrary length,
so it needs a real window -- hence this module rather than another prop.
"""

# Text metrics are approximated rather than measured: pulling QFontMetrics in
# would drag Qt into a pure module for a few pixels of accuracy, and the bubble
# is padded enough to absorb the error. Tuned for the 12px UI font pet.py uses.
CHAR_W = 7.2
LINE_H = 17
PAD_X = 10
PAD_Y = 8

MIN_W = 120
MAX_W = 360
MAX_LINES = 12
GAP = 8          # between bubble and creature
MARGIN = 6       # keep this far off the screen edge


def wrap(text, max_chars):
    """Break `text` into display lines, honouring existing newlines.

    Long unbroken runs (a URL, a path) are hard-split rather than allowed to
    overflow the bubble -- a line that runs past the edge is worse than an
    ugly break.
    """
    if max_chars < 1:
        max_chars = 1
    out = []
    for para in str(text or "").splitlines() or [""]:
        if not para.strip():
            out.append("")
            continue
        line = ""
        for word in para.split():
            while len(word) > max_chars:
                if line:
                    out.append(line)
                    line = ""
                out.append(word[:max_chars])
                word = word[max_chars:]
            candidate = word if not line else line + " " + word
            if len(candidate) <= max_chars:
                line = candidate
            else:
                out.append(line)
                line = word
        if line:
            out.append(line)
    return out or [""]


def wrap_measured(text, max_w, measure):
    """`measure(str) -> px` 로 재가며 줄을 나눈다. 순수.

    글자 수로 나누면 안 된다 — 한글은 라틴의 두 배 폭이라 같은 글자 수가 두 배
    넓이가 되고, 그대로 말풍선 밖으로 나간다(실측). 평균 폭을 곱하는 것도 같은
    이유로 빗나가므로, 후보 줄을 그때그때 잰다."""
    lines, cur = [], ""
    for word in (text or "").split():
        trial = (cur + " " + word).strip()
        if cur and measure(trial) > max_w:
            lines.append(cur)
            cur = word
        else:
            cur = trial
        while measure(cur) > max_w and len(cur) > 1:   # 한 낱말이 통째로 길 때
            cut = len(cur) - 1
            while cut > 1 and measure(cur[:cut]) > max_w:
                cut -= 1
            lines.append(cur[:cut])
            cur = cur[cut:]
    if cur:
        lines.append(cur)
    return lines or [""]


def layout(text, max_w=MAX_W, footer="", char_w=CHAR_W, measure=None):
    """(lines, width, height, truncated) for `text`.

    `footer` is an optional trailing affordance ("되묻기"). It is appended as a
    real line, separated by a blank one, so it participates in width and height
    like any other text -- the alternative, reserving a strip and painting into
    it, puts the same number in two places and they drift.

    `char_w` 는 글자 하나의 평균 폭이다. 기본값은 라틴 기준 추정치인데, 한글은
    그 두 배라 그대로 두면 74자가 한 줄로 들어가고 말풍선이 잘린다(실측).
    화면이 있는 쪽(`pet.py`)은 이 글에 실제로 쓰는 폰트로 재서 넘긴다 — 이
    모듈은 여전히 Qt 를 모른다.
    """
    char_w = char_w or CHAR_W
    inner = max_w - 2 * PAD_X
    if measure is None:
        lines = wrap(text, max(1, int(inner / char_w)))
        measure = lambda s: len(s) * char_w            # noqa: E731
    else:
        lines = wrap_measured(text, inner, measure)
    truncated = False
    if len(lines) > MAX_LINES:
        lines = lines[:MAX_LINES]
        lines[-1] = (lines[-1] + "…") if lines[-1] else "…"
        truncated = True
    if footer:
        lines = lines + ["", footer]
    widest = max((measure(l) for l in lines), default=0)
    w = int(min(max_w, max(MIN_W, widest + 2 * PAD_X)))
    h = int(len(lines) * LINE_H + 2 * PAD_Y)
    return lines, w, h, truncated


def footer_top(lines):
    """Local y where the footer's clickable band starts.

    The band covers the blank separator too: a click in the gap just above the
    footer text is aiming at the footer, and a one-line dead zone in a bubble
    this small reads as the click not registering.
    """
    return PAD_Y + max(0, len(lines) - 2) * LINE_H


def place(pet_rect, size, screen_rect):
    """Top-left for a bubble of `size` next to `pet_rect`, kept on `screen_rect`.

    Prefers above the creature (a bubble below covers what the creature stands
    on); flips under it when there is no room above. Then clamps horizontally so
    it never runs off the edge -- clamping last means the flip decision isn't
    made on a position we're about to move anyway.
    """
    px, py, pw, ph = pet_rect
    bw, bh = size
    sx, sy, sw, sh = screen_rect

    x = px + pw // 2 - bw // 2
    y = py - bh - GAP
    if y < sy + MARGIN:                       # no room above -> go below
        y = py + ph + GAP
    y = max(sy + MARGIN, min(y, sy + sh - bh - MARGIN))
    x = max(sx + MARGIN, min(x, sx + sw - bw - MARGIN))
    return int(x), int(y)


def tail_x(pet_rect, bubble_x, bubble_w):
    """X of the bubble's tail, in bubble-local pixels, pointing at the creature.

    Kept inside the rounded corners so the tail never grows out of the curve.
    """
    px, pw = pet_rect[0], pet_rect[2]
    want = px + pw // 2 - bubble_x
    return int(max(12, min(bubble_w - 12, want)))
