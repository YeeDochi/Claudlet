"""Bubble geometry: where it goes and how the text breaks.

Pure arithmetic, so no display is needed -- which is the point of keeping it
out of pet.py.
"""
from claudlet.core import bubble as B


SCREEN = (0, 0, 1920, 1080)


def test_short_text_is_one_line():
    lines, w, h, tr = B.layout("hello")
    assert lines == ["hello"]
    assert not tr


def test_width_never_exceeds_the_cap():
    _, w, _, _ = B.layout("x " * 500)
    assert w <= B.MAX_W


def test_width_has_a_floor_for_tiny_text():
    _, w, _, _ = B.layout("hi")
    assert w >= B.MIN_W


def test_explicit_newlines_are_kept():
    lines, _, _, _ = B.wrap("a\nb\nc", 40), None, None, None
    assert lines == ["a", "b", "c"]


def test_long_words_are_hard_split_rather_than_overflowing():
    lines = B.wrap("x" * 100, 10)
    assert all(len(l) <= 10 for l in lines)
    assert "".join(lines) == "x" * 100


def test_wrapping_breaks_on_spaces():
    assert B.wrap("aaa bbb ccc", 7) == ["aaa bbb", "ccc"]


def test_too_many_lines_are_truncated_with_a_marker():
    lines, _, _, tr = B.layout("\n".join("line %d" % i for i in range(100)))
    assert tr
    assert len(lines) <= B.MAX_LINES
    assert lines[-1].endswith("…")


def test_empty_text_still_lays_out():
    lines, w, h, _ = B.layout("")
    assert lines == [""] and w >= B.MIN_W and h > 0


def test_bubble_sits_above_the_creature_by_default():
    x, y = B.place((500, 400, 100, 90), (150, 40), SCREEN)
    assert y + 40 <= 400            # entirely above the pet's top


def test_bubble_flips_below_when_there_is_no_room_above():
    x, y = B.place((500, 0, 100, 90), (150, 40), SCREEN)
    assert y >= 90                  # pushed under the pet


def test_bubble_is_clamped_to_the_left_edge():
    x, _ = B.place((0, 400, 100, 90), (300, 40), SCREEN)
    assert x >= SCREEN[0]


def test_bubble_is_clamped_to_the_right_edge():
    x, _ = B.place((1900, 400, 100, 90), (300, 40), SCREEN)
    assert x + 300 <= SCREEN[0] + SCREEN[2]


def test_bubble_stays_on_a_non_zero_origin_screen():
    screen = (1920, 0, 1920, 1080)      # second monitor to the right
    x, y = B.place((2000, 400, 100, 90), (200, 40), screen)
    assert x >= 1920 and x + 200 <= 3840


def test_tail_points_at_the_creature():
    pet = (500, 400, 100, 90)
    x, _ = B.place(pet, (150, 40), SCREEN)
    tail = B.tail_x(pet, x, 150)
    # pet centre is 550; tail is bubble-local, so x + tail should land near it
    assert abs((x + tail) - 550) <= 14


def test_tail_stays_inside_the_bubble():
    pet = (0, 400, 100, 90)
    x, _ = B.place(pet, (300, 40), SCREEN)
    tail = B.tail_x(pet, x, 300)
    assert 0 < tail < 300


# ---------- reply footer ----------

def test_footer_is_appended_as_a_line():
    lines, _, _, _ = B.layout("answer", footer="↩ more")
    assert lines[-1] == "↩ more"
    assert lines[0] == "answer"


def test_footer_is_separated_by_a_blank_line():
    lines, _, _, _ = B.layout("answer", footer="↩ more")
    assert lines[-2] == ""


def test_no_footer_means_no_extra_lines():
    assert B.layout("answer")[0] == ["answer"]


def test_footer_grows_the_bubble():
    _, _, plain, _ = B.layout("answer")
    _, _, withf, _ = B.layout("answer", footer="↩ more")
    assert withf > plain


def test_a_long_footer_widens_the_bubble():
    _, narrow, _, _ = B.layout("hi", footer="↩ x")
    _, wide, _, _ = B.layout("hi", footer="↩ " + "y" * 30)
    assert wide > narrow


def test_footer_band_starts_below_the_answer_text():
    lines, _, h, _ = B.layout("answer", footer="↩ more")
    top = B.footer_top(lines)
    assert 0 < top < h


def test_the_blank_separator_counts_as_footer():
    # a click in the gap is aiming at the footer, not the text above it
    lines, _, _, _ = B.layout("answer", footer="↩ more")
    gap_y = B.PAD_Y + (len(lines) - 2) * B.LINE_H
    assert gap_y >= B.footer_top(lines)


def test_footer_top_of_a_plain_bubble_is_the_top_padding():
    assert B.footer_top(["one"]) == B.PAD_Y


def test_truncation_still_applies_with_a_footer():
    lines, _, _, tr = B.layout("\n".join(str(i) for i in range(100)),
                               footer="↩ more")
    assert tr
    assert lines[-1] == "↩ more"
