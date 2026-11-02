"""펫 그림 → 터미널 반 블록 칸."""
import base64
import struct

from claudlet.core import termframe as T

R, G, _ = 0xFFFF0000, 0xFF00FF00, 0x00000000


def _cells(b64):
    raw = base64.b64decode(b64)
    words = struct.unpack("<%dI" % (len(raw) // 4), raw)
    return [words[i:i + 3] for i in range(0, len(words), 3)]


def test_two_pixels_stack_into_one_half_block_cell():
    # 2x3 그림, 왼쪽 열만 칠해짐: 빨강 위, 초록 아래, 그 아래 빨강
    cols, rows, b64 = T.encode(2, 3, [R, _, G, _, R, _])
    assert (cols, rows) == (1, 2)              # 빈 오른쪽 열은 잘려 나간다
    assert _cells(b64) == [(T.UPPER, 0xFF0000, 0x00FF00),
                           (T.UPPER, 0xFF0000, T.DEFAULT)]   # 홀수 줄의 아래는 비었다


def test_a_transparent_top_uses_the_lower_half_block():
    assert T.cell(None, 0x123456) == (T.LOWER, 0x123456, T.DEFAULT)
    assert T.cell(None, None) == (0x20, T.DEFAULT, T.DEFAULT)


def test_an_empty_picture_has_no_frame():
    assert T.encode(2, 2, [_] * 4) is None


def test_written_frames_say_where_and_when(tmp_path, monkeypatch):
    import json
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path))
    T.write("s1", (1, 1, "AAAA"), x=1.7)
    body = json.loads(open(T.frame_file("s1")).read())
    assert body["x"] == 1.0 and not body["gone"]
    T.write("s1", None, 0)
    assert json.loads(open(T.frame_file("s1")).read())["gone"]
