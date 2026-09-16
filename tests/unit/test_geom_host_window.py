"""Picking THIS session's host window when one process owns many windows.

JetBrains runs every open project in one JVM and Konsole every tab in one
process, so pid-ancestry finds the app but cannot say which window is ours.
The captions are real ones read off a running KDE session.
"""
from claudlet.platform import geom

IDEA = "openstackit-java – telegraf.conf [openstackit-java]"
IDEA2 = "claudlet – pet.py [claudlet]"
PATHY = "serafin [/home/me/IdeaProjects/serafin_v2_be]"
KONSOLE = "claude-pet : claude — Konsole"


def _w(wid, pid, caption, cls="jetbrains-idea"):
    return geom.Win(wid, 0, 0, 800, 600, cls, pid, caption)


def test_project_of_reads_the_leading_segment():
    assert geom.project_of(IDEA) == "openstackit-java"
    assert geom.project_of(PATHY) == "serafin"
    assert geom.project_of(KONSOLE) == "claude-pet : claude"
    assert geom.project_of("") == ""


def test_bracketed_path_only_when_it_is_a_path():
    assert geom.bracketed_path(PATHY) == "/home/me/IdeaProjects/serafin_v2_be"
    assert geom.bracketed_path(IDEA) == ""          # a module name, not a path
    assert geom.bracketed_path("no brackets") == ""


def test_prefix_project_does_not_steal_the_other_window():
    # "bnk-approval" is a prefix of "bnk-approval-fe": a substring test would
    # hand each project the other's window
    wins = [_w("a", 9, "bnk-approval-fe – x.ts [bnk-approval-fe]"),
            _w("b", 9, "bnk-approval – y.java [bnk-approval]")]
    assert geom.pick_by_project(wins, "bnk-approval", "/p/bnk-approval").wid == "b"
    assert geom.pick_by_project(wins, "bnk-approval-fe", "/p/bnk-approval-fe").wid == "a"


def test_ambiguous_or_absent_match_declines():
    wins = [_w("a", 9, IDEA), _w("b", 9, IDEA)]      # same project twice
    assert geom.pick_by_project(wins, "openstackit-java", "/p/openstackit-java") is None
    assert geom.pick_by_project([_w("a", 9, IDEA)], "other", "/p/other") is None
    assert geom.pick_by_project([_w("a", 9, "")], "x", "/p/x") is None


def test_find_host_breaks_a_one_process_tie_by_project():
    # both windows are the same JVM: pid alone always yields the first one
    wins = [_w("first", 9, IDEA2), _w("second", 9, IDEA)]
    assert geom.find_host(wins, {9}).wid == "first"                  # old behaviour
    assert geom.find_host(wins, {9}, project="openstackit-java",
                          cwd="/home/ljh/openstackit-java").wid == "second"


def test_find_host_falls_back_when_the_caption_cannot_decide():
    wins = [_w("first", 9, IDEA2), _w("second", 9, IDEA)]
    assert geom.find_host(wins, {9}, project="unrelated",
                          cwd="/p/unrelated").wid == "first"
    blank = [_w("first", 9, ""), _w("second", 9, "")]
    assert geom.find_host(blank, {9}, project="x", cwd="/p/x").wid == "first"


def test_single_owned_window_is_unaffected():
    wins = [_w("only", 9, "whatever")]
    assert geom.find_host(wins, {9}, project="x", cwd="/p/x").wid == "only"


def test_caption_survives_the_wire_with_our_delimiters_in_it():
    # real title: "Microsoft Teams (PWA) - 채팅 | 아무것도 몰라요" — carries both
    # the field (;) and record (|) separators, so the sender percent-encodes it
    from urllib.parse import quote
    cap = "Teams (PWA) - 채팅 | 아무것도; 몰라요"
    dump = "w1;jetbrains-idea;0,0,800,600;42;" + quote(cap)
    wins = geom.parse_dump(dump)
    assert len(wins) == 1 and wins[0].caption == cap and wins[0].pid == 42


def test_feed_without_a_caption_still_parses():
    wins = geom.parse_dump("w1;konsole;0,0,800,600;42")
    assert wins[0].caption == "" and wins[0].pid == 42


def test_unidentifiable_host_window_stops_flip_flopping():
    """`wins` arrives in stacking order, so "the first pid match" moves every
    time one of those windows is raised. With two projects open in one IDE and
    nothing in the captions naming ours, click -> raise A -> A is topmost ->
    the first match is now B -> next click raises B, forever. Measured on KDE:
    the two projects alternated on every single click, which reads as the IDE
    minimising itself. Once a window is chosen it is kept."""
    a = _w("A", 9, "projA – x.java [projA]")
    b = _w("B", 9, "projB – y.java [projB]")
    # our project is open in neither, so the caption can never decide
    first = geom.find_host([a, b], {9}, project="mine", cwd="/p/mine")
    assert first.wid == "A"
    # raising A puts it on top -> the feed now lists B first
    again = geom.find_host([b, a], {9}, project="mine", cwd="/p/mine",
                           current=first.wid)
    assert again.wid == "A", "host window flip-flopped with the stacking order"


def test_a_stale_sticky_choice_is_dropped():
    # the remembered window is gone (project closed): fall back, don't return None
    wins = [_w("A", 9, "projA – x [projA]"), _w("B", 9, "projB – y [projB]")]
    assert geom.find_host(wins, {9}, project="mine", cwd="/p/mine",
                          current="CLOSED").wid == "A"


def test_the_caption_still_wins_over_a_stale_sticky_choice():
    # stickiness is only for the case nothing identifies ours
    wins = [_w("A", 9, "projA – x [projA]"), _w("B", 9, "mine – y [mine]")]
    assert geom.find_host(wins, {9}, project="mine", cwd="/p/mine",
                          current="A").wid == "B"
