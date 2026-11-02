import json

from claudlet.core import affection as A

D1, D2 = "2026-11-02", "2026-11-03"


def test_stage_follows_the_thresholds():
    assert [A.stage(p) for p in (0, 29, 30, 119, 120, 299, 300, 10_000)] == \
        [0, 0, 1, 1, 2, 2, 3, 3]


def test_first_touch_of_the_day_carries_a_bonus_then_plain_gains():
    d = A.gain({}, "slime", "pet", D1)
    assert A.points(d, "slime") == A.GAINS["pet"] + A.DAY_BONUS
    d = A.gain(d, "slime", "talk", D1)
    assert A.points(d, "slime") == A.GAINS["pet"] + A.DAY_BONUS + A.GAINS["talk"]


def test_spam_stops_at_the_daily_cap_and_a_new_day_reopens_it():
    d = {}
    for _ in range(100):
        d = A.gain(d, "slime", "pet", D1)
    assert A.points(d, "slime") == A.DAILY_CAP
    assert A.gain(d, "slime", "talk", D1) is d          # nothing left today
    d = A.gain(d, "slime", "pet", D2)
    assert A.points(d, "slime") == A.DAILY_CAP + A.GAINS["pet"] + A.DAY_BONUS


def test_points_never_go_down_and_other_creatures_are_untouched():
    d = {"slime": {"points": 500, "day": D1, "used": 3}, "codex": {"points": 7}}
    d2 = A.gain(d, "slime", "done", D2)
    assert A.points(d2, "slime") > 500
    assert d2["codex"] == {"points": 7}
    assert A.gain(d, "slime", "nonsense", D1) is d      # unknown kind adds nothing


def test_a_corrupt_record_counts_as_a_fresh_start():
    for bad in ({"slime": "x"}, {"slime": {"points": -4, "used": "a"}},
                {"slime": {"points": True}}, []):
        assert A.points(A.gain(bad, "slime", "pet", D1), "slime") == \
            A.GAINS["pet"] + A.DAY_BONUS


def test_voice_adds_a_closeness_line_only_once_familiar():
    assert A.voice("물컹하게", 0) == "물컹하게"
    assert A.voice("", 0) == ""
    assert A.voice("물컹하게", 300) == "물컹하게, " + A.VOICE["ko"][3]
    assert A.voice("", 120, "en") == A.VOICE["en"][2]


def test_record_merges_into_what_another_pet_wrote(tmp_path):
    # 다른 펫(다른 프로세스)이 그새 써 둔 것 위에 더한다 — 덮어쓰지 않는다
    with open(A.path(), "w") as f:
        json.dump({"slime": {"points": 40, "day": D1, "used": 10},
                   "codex": {"points": 3, "day": D1, "used": 3}}, f)
    assert A.record("slime", "talk", D1) == 43
    on_disk = A.load()
    assert on_disk["slime"]["used"] == 13
    assert on_disk["codex"]["points"] == 3


def test_load_survives_a_missing_or_broken_file():
    assert A.load() == {}
    with open(A.path(), "w") as f:
        f.write("{not json")
    assert A.load() == {}
    assert A.record("slime", "pet", D1) == A.GAINS["pet"] + A.DAY_BONUS
