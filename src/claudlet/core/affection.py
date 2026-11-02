"""호감도 — 크리처마다 천천히 쌓이는 친밀도. 순수(파일 IO 는 load/record 뿐).

- 줄지 않는다. 안 놀아줬다고 깎이거나 토라지지 않는다.
- 매일 해야 하는 일은 없다. 하루에 오르는 양만 막아(DAILY_CAP) 쓰다듬기 연타로
  쌓을 수 없게 한다.
- 펫 창은 세션마다 하나씩 뜨지만 호감도는 크리처(아바타 이름)마다 하나다. 그래서
  config.json 옆 affection.json 에 둔다::

      {"claudlet": {"points": 42, "day": "2026-11-02", "used": 12}}

  여러 펫이 동시에 쓰므로 오를 때마다 디스크에서 다시 읽어 그 위에 더하고 쓴다
  (`record`). 남의 크리처 기록과 같은 크리처의 다른 펫이 올린 몫이 그대로 남는다.
"""
import json
import os

from claudlet.core import petconfig

GAINS = {"pet": 2, "talk": 3, "done": 1}   # 쓰다듬기 · 말 걸기 · 세션이 일을 마침
DAY_BONUS = 5                              # 그날 첫 교감
DAILY_CAP = 20                             # 하루에 오를 수 있는 최대치

STAGES = ("shy", "warming", "friend", "bestie")
THRESHOLDS = (0, 30, 120, 300)             # 각 단계가 시작되는 점수

# 크리처 목소리에 덧붙는 친밀도 한 줄(말투 뒤에 쉼표로). 처음엔 아무것도 안 붙인다.
VOICE = {
    "ko": ("", "조금 친해진 사이처럼", "친구처럼 편하게", "단짝처럼 스스럼없이 다정하게"),
    "en": ("", "like someone warming up to the user", "at ease, like a friend",
           "warm and familiar, like a best friend"),
}
GREETING = (None, "wave", "wave", "jump")  # 세션이 시작될 때 반기는 모션
HEARTS = (1, 3, 4, 5)                       # 쓰다듬으면 뜨는 하트 수


def stage(pts):
    """점수 -> 단계 번호(0..3)."""
    return sum(pts >= t for t in THRESHOLDS[1:])


# 단계마다 성격이 행동으로 드러난다(낯가림 → 단짝).
DONE_MOTION = (None, None, "jump", "jump")   # 같이 일 하나를 끝냈을 때 덧붙이는 모션
# 쓰다듬으면: 낯가림은 고개를 돌리고 물러서고("shy" — 모션이 아니라 펫이 직접 한다),
# 단짝은 흥얼거린다. (tic 은 기지개라 웃는 얼굴과 겹쳐 머쓱해 보이지 않았다 — 실측)
PET_MOTION = ("shy", None, None, "sing")
PLAY_MOTIONS = ("sing", "juggle", "wave")
# 놀 거리를 고를 때마다 (혼자 놀기, 커서 쪽으로 다가오기) 확률
IDLE_EXTRA = ((0.0, 0.0), (0.02, 0.0), (0.05, 0.04), (0.08, 0.10))


def idle_extra(pts, r):
    """놀 거리를 고르는 순간 덤으로 할 것: "approach" | "play" | None. 순수."""
    play, come = IDLE_EXTRA[stage(pts)]
    if r < come:
        return "approach"
    if r < come + play:
        return "play"
    return None


def gauge(pts, width=10):
    """"▰▰▰▱▱▱▱▱▱▱" — 이번 단계 안에서 다음 단계까지. 마지막 단계는 꽉 찬다. 순수."""
    lo = THRESHOLDS[stage(pts)]
    hi = next((t for t in THRESHOLDS if t > pts), None)
    filled = width if hi is None else int(width * (pts - lo) / (hi - lo))
    return "▰" * filled + "▱" * (width - filled)


def span(pts):
    """이번 단계의 (시작, 다음 단계) 점수. 마지막 단계면 (시작, None). 순수."""
    return THRESHOLDS[stage(pts)], next((t for t in THRESHOLDS if t > pts), None)


def progress(pts):
    """"8/30" — 다음 단계까지. 마지막 단계면 점수만. 순수."""
    nxt = next((t for t in THRESHOLDS if t > pts), None)
    return "%d/%d" % (pts, nxt) if nxt is not None else str(pts)


def voice(persona, pts, lang="ko"):
    """말투에 친밀도 한 줄을 덧붙인 것. 둘 다 비면 ""."""
    line = VOICE.get(lang, VOICE["ko"])[stage(pts)]
    return ", ".join(x for x in (persona, line) if x)


def _rec(data, creature):
    """파일에서 읽은 한 크리처의 기록을 믿을 만한 모양으로. 이상한 값은 0 으로."""
    rec = data.get(creature) if isinstance(data, dict) else None
    if not isinstance(rec, dict):
        rec = {}
    out = {"day": rec.get("day") if isinstance(rec.get("day"), str) else ""}
    for k in ("points", "used"):
        v = rec.get(k)
        out[k] = v if isinstance(v, int) and not isinstance(v, bool) and v > 0 else 0
    return out


def points(data, creature):
    return _rec(data, creature)["points"]


def gain(data, creature, kind, today):
    """`kind` 교감 한 번을 더한 새 dict. 오를 게 없으면 `data` 를 그대로 돌려준다.

    `today` 는 "YYYY-MM-DD"(호출자가 넣는다 — 날짜가 바뀌면 하루치가 새로 열린다).
    그날 첫 교감이면 DAY_BONUS 가 붙고, 하루 합은 DAILY_CAP 을 넘지 않는다."""
    rec = _rec(data, creature)
    fresh = rec["day"] != today
    used = 0 if fresh else rec["used"]
    add = min(GAINS.get(kind, 0) + (DAY_BONUS if fresh else 0), DAILY_CAP - used)
    if add <= 0:
        return data
    new = dict(data) if isinstance(data, dict) else {}
    new[creature] = {"points": rec["points"] + add, "day": today, "used": used + add}
    return new


def path():
    return os.path.join(os.path.dirname(petconfig.config_path()), "affection.json")


def left_today(data, creature, today):
    """오늘 더 오를 수 있는 점수. 순수."""
    rec = _rec(data, creature)
    return DAILY_CAP - (rec["used"] if rec["day"] == today else 0)


def fact(stage_name, pts, left, lang="ko"):
    """크리처 머리에 주는 사실 한 줄 — 대화에서 주워들은 숫자 대신 이것으로 답하게. 순수."""
    if lang == "en":
        return ("Fact: your closeness with the user is '%s', %s points; %s. If asked"
                " about it, use exactly this." % (stage_name, progress(pts),
                "no more can be gained today" if left <= 0 else "%d more can be gained today" % left))
    return ("사실: 지금 사용자와의 친밀도는 '%s', %s점이다. %s. 물으면 이 값으로만"
            " 답해라." % (stage_name, progress(pts),
                       "오늘 몫은 다 찼다(내일 다시 오른다)" if left <= 0
                       else "오늘은 %d점 더 오를 수 있다" % left))


def load():
    try:
        with open(path(), encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def record(creature, kind, today):
    """디스크에서 읽고 -> 더하고 -> 쓴다. 이 크리처의 새 점수를 돌려준다.

    쓰기는 임시 파일 + os.replace 라 반쯤 쓴 파일을 다른 펫이 읽는 일은 없다."""
    # ponytail: 잠금 없음 — 두 펫이 같은 순간에 쓰면 한쪽 몫(몇 점)이 빠질 수 있다.
    # 교감은 드물고 값은 줄지 않으니 감수한다. 문제가 되면 dockslot 식 파일 잠금.
    data = load()
    new = gain(data, creature, kind, today)
    if new is not data:
        p = path()
        tmp = "%s.%d.tmp" % (p, os.getpid())
        try:
            os.makedirs(os.path.dirname(p), exist_ok=True)
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(new, f, ensure_ascii=False)
            os.replace(tmp, p)
        except OSError:
            pass                    # 호감도를 못 남겼다고 펫이 죽을 일은 아니다
    return points(new, creature)
