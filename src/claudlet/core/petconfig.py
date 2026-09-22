"""User config for claudlet: remap which creature motion shows for which
Claude Code activity.

File (JSON, all keys optional), at ``$XDG_CONFIG_HOME/claudlet/config.json``
(default ``~/.config/claudlet/config.json``)::

    {
      "tools":      { "Bash": "work_search", "Grep": "sing", "*": "work_computer" },
      "events":     { "prompt": "thinking", "celebrate": "juggle" },
      "raw_events": { "PostToolUse": "celebrate", "SubagentStop": "wave" }
    }

- ``tools``  — tool name -> state. ``"*"`` is the fallback for unmapped tools;
  ``mcp__*`` tools default to ``work_web`` unless named explicitly.
- ``events`` — event slot -> state. Slots: start, prompt, done, celebrate,
  error, permission, idle_prompt (see state_engine.DEFAULT_EVENT_STATES).
- ``raw_events`` — raw hook event name -> state, for any event the engine does
  not already handle via a slot (PostToolUse, SubagentStop, PreCompact, and any
  future event). Knowing the event name the hook pushes is enough to map it.

Values must be one of state_engine.MAPPABLE_STATES; anything else (or a bad
file) is ignored, so a typo degrades to the built-in defaults rather than
breaking the pet. Pure except for the single file read in load_config.
"""
import os
import json

from claudlet.core import dock as dockgeom
from claudlet.core.state_engine import MAPPABLE_STATES, DEFAULT_EVENT_STATES


# 도크(고정 배치) 기본값. enabled=True가 기본 — 펫이 모니터 코너에 붙어 서고,
# 여러 마리는 dock.py가 옆으로 나란히 세운다. 배회하던 예전 동작은
# {"dock": {"enabled": false}} 또는 우클릭 메뉴의 "배회"로 돌아온다.
DEFAULT_DOCK = {"enabled": True, "anchor": dockgeom.DEFAULT_ANCHOR,
                "gap": dockgeom.DEFAULT_GAP, "screen": "primary",
                "offset": {"x": 0.0, "y": 0.0}}

SHINY_PALETTES = ("shiny_teal", "shiny_violet")
SHINY_CHANCE = 0.02
_PALETTE_NAMES = ("auto", "default") + SHINY_PALETTES


def config_path():
    base = os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config")
    return os.path.join(base, "claudlet", "config.json")


def default_dock():
    """DEFAULT_DOCK의 깊은 사본 — 호출자가 offset을 제자리 수정해도 안전하게."""
    d = dict(DEFAULT_DOCK)
    d["offset"] = dict(DEFAULT_DOCK["offset"])
    return d


def _clean_dock(v):
    """dock 섹션 검증. 다른 키와 같은 규칙: 이상한 값은 조용히 기본값으로 떨군다."""
    d = default_dock()
    if not isinstance(v, dict):
        return d
    if isinstance(v.get("enabled"), bool):
        d["enabled"] = v["enabled"]
    if v.get("anchor") in dockgeom.ANCHORS:
        d["anchor"] = v["anchor"]
    try:
        d["gap"] = max(0, int(v["gap"]))
    except (KeyError, TypeError, ValueError):
        pass
    scr = v.get("screen")
    # bool은 int의 하위형이라 isinstance만으로는 screen=true가 0번 모니터로 통과한다
    if scr == "primary" or (isinstance(scr, int) and not isinstance(scr, bool)
                            and scr >= 0):
        d["screen"] = scr
    off = v.get("offset")
    if isinstance(off, dict):
        try:
            d["offset"] = {"x": float(off.get("x", 0.0)),
                           "y": float(off.get("y", 0.0))}
        except (TypeError, ValueError):
            pass
    return d


def _clean(raw):
    """Validate a parsed config dict -> {tool_states, event_states}. Pure."""
    tools = {}
    for key, val in (raw.get("tools") or {}).items():
        if isinstance(key, str) and val in MAPPABLE_STATES:
            tools[key] = val
    events = {}
    for key, val in (raw.get("events") or {}).items():
        if key in DEFAULT_EVENT_STATES and val in MAPPABLE_STATES:
            events[key] = val
    raw_events = {}
    for key, val in (raw.get("raw_events") or {}).items():
        if isinstance(key, str) and val in MAPPABLE_STATES:
            raw_events[key] = val
    lang = raw.get("lang")
    if lang not in ("ko", "en", "auto"):
        lang = "auto"

    palette = raw.get("palette")
    # a name from the table, or "#RRGGBB" for a colour the user picked
    if palette not in _PALETTE_NAMES and derive_palette(palette) is None:
        palette = "auto"
    scale = clamp_scale(raw.get("scale"))
    avatar = clean_avatar(raw.get("avatar"))
    creatures = _clean_creatures(raw.get("creatures"))

    def _rect(v):
        if not isinstance(v, dict):
            return None
        try:
            x, y, w, h = float(v["x"]), float(v["y"]), float(v["w"]), float(v["h"])
        except (KeyError, TypeError, ValueError):
            return None
        if w <= 0 or h <= 0:
            return None
        return {"x": x, "y": y, "w": w, "h": h}

    roam_area = _rect(raw.get("roam_area"))
    if not isinstance(raw.get("no_go"), list):
        no_go = []
    else:
        no_go = [r for r in (_rect(z) for z in raw.get("no_go")) if r]

    return {"tool_states": tools, "event_states": events,
            "raw_events": raw_events, "lang": lang,
            "roam_area": roam_area, "no_go": no_go, "palette": palette,
            "scale": scale, "avatar": avatar, "creatures": creatures,
            "dock": _clean_dock(raw.get("dock"))}


def _windows_locale():
    """User's UI locale (e.g. "ko-KR") via Win32 — Windows doesn't set the
    POSIX LANG/LC_* vars resolve_lang() otherwise reads, so without this,
    "auto" would default to English on every Windows machine regardless of
    the system's actual language. Delegates to geom/win32.py (the one module
    that owns the guarded, typed ctypes handles) rather than re-opening windll."""
    try:
        from claudlet.platform.geom import win32
        return win32.user_locale()
    except Exception:
        return ""


def resolve_lang(value):
    """Map a config lang to a concrete "ko"/"en". "auto" (or anything odd) reads
    the locale: Korean locale -> ko, otherwise en."""
    if value in ("ko", "en"):
        return value
    loc = (os.environ.get("LC_ALL") or os.environ.get("LC_MESSAGES")
           or os.environ.get("LANG") or "")
    if not loc and os.name == "nt":
        loc = _windows_locale()
    return "ko" if loc.lower().startswith("ko") else "en"


# Device pixels per art pixel. Integers only: a fractional scale splits art
# pixels across device pixels, which is exactly the silhouette wobble v1.7.1
# removed. The range is what stays legible on one end and fits a screen on the
# other.
DEFAULT_SCALE = 5
# 1 is allowed because a creature may carry art at a finer grid than the
# built-in's 22x17 — such a creature declares its box in ITS dots and draws one
# dot per unit, and at a floor of 2 it could never be shown smaller than double
# size. Halving inside the creature instead is not the same thing: everything
# the pet places around it (petting hearts, the speech bubble) is measured in
# box units, so a creature that scales differently from its box drifts out of
# step with them at every odd size.
MIN_SCALE, MAX_SCALE = 1, 12


# How the "running unattended" signal is shown. Not a visor as such: the pet
# only reports that the mode is on and each creature decides what that looks
# like (the built-in wears a VR visor; another might glow, or ignore it).
# The only creature that existed before appearance became per creature, so the
# only one a pre-1.8 config's top-level palette/scale can have meant.
LEGACY_CREATURE = "claudlet"

VISOR_MODES = ("auto", "on", "off")
DEFAULT_VISOR = "auto"


def clean_visor(value):
    return value if value in VISOR_MODES else DEFAULT_VISOR


def clean_scale_opt(value):
    """A scale, or None when the creature has not been given one.

    Reading the file does not know which creature the value belongs to, so a
    fraction is kept here and snapped later, in `for_creature`, where the
    creature is in hand. Rounding to a whole number at this point threw away
    the half sizes a sprite creature is allowed before anything could ask
    whether it was allowed one."""
    return None if value is None else clamp_scale(value, fractional=True)


def clean_palette_opt(value):
    """A palette name or "#RRGGBB", or None when unset."""
    if isinstance(value, str) and (value in _PALETTE_NAMES
                                   or derive_palette(value) is not None):
        return value
    return None


def _clean_creatures(raw):
    """Per-creature appearance. Settings belong to the CREATURE, not to the
    pet: a slime and a claudlet want different colours and sizes, and a pet is
    a session — gone in an hour — so hanging the look off it would mean setting
    it again every time."""
    out = {}
    if not isinstance(raw, dict):
        return out
    for name, v in raw.items():
        if not isinstance(name, str) or not isinstance(v, dict):
            continue
        out[name] = {"palette": clean_palette_opt(v.get("palette")),
                     "scale": clean_scale_opt(v.get("scale")),
                     "visor": clean_visor(v.get("visor"))}
    return out


def for_creature(cfg, name, avatar=None):
    """Appearance for one creature: what the user set, then what the creature
    asks for, then the defaults.

    A creature declares its own `palette` because a slime opening in claudlet's
    orange is wrong before the user has touched anything — and its own `scale`
    for the same reason. The default of 5 assumes the built-in's 22x17 box; a
    creature carrying finer art declares a box in ITS dots, where 5 means five
    device pixels per dot and a pet the size of a window."""
    mine = (cfg.get("creatures") or {}).get(name) or {}
    palette = mine.get("palette")
    if palette is None:
        palette = clean_palette_opt(getattr(avatar, "palette", None))
    # A config written before appearance was per creature has palette/scale at
    # the top level. Those belong to the ONE creature that existed then, and
    # only while the user has not used the new settings at all -- carrying them
    # forward to every creature painted the built-in in a colour that had been
    # picked for something else.
    legacy = not cfg.get("creatures") and name == LEGACY_CREATURE
    if palette is None and legacy:
        palette = cfg.get("palette") or "auto"
    if palette is None:
        palette = "auto"
    fine = bool(getattr(avatar, "fractional_scale", False))
    scale = mine.get("scale")
    if scale is not None:
        scale = clamp_scale(scale, fine)
    elif legacy:
        scale = clamp_scale(cfg.get("scale"), fine)
    else:
        want = getattr(avatar, "scale", None)
        scale = clamp_scale(want, fine) if want is not None else DEFAULT_SCALE
    # 말투는 크리처가 들고 온다 — 슬라임을 내보내면 슬라임 말투도 따라간다.
    # 사용자가 적어둔 것이 있으면 그것이 이긴다(색·크기와 같은 규칙).
    persona = mine.get("persona")
    if persona is None:
        persona = getattr(avatar, "persona", None)
    return {"palette": palette, "scale": scale,
            "visor": mine.get("visor") or DEFAULT_VISOR,
            "persona": str(persona or "").strip()}


PERSONA_MAX = 200          # 한 줄 지시면 충분하다. 주입되는 컨텍스트이기도 하고.


def clean_persona(raw):
    """저장할 말투 한 줄, 또는 지우라는 뜻의 None. 순수.

    빈 값은 빈 문자열로 저장하지 않고 지운다 — 그래야 크리처가 들고 온 기본
    말투가 다시 산다(색·크기의 reset 과 같은 규칙)."""
    one = " ".join(str(raw or "").split())
    return one[:PERSONA_MAX] if one else None


def clamp_scale(value, fractional=False):
    """A usable scale from whatever the config holds. Pure.

    Whole numbers by default: a fractional unit makes the built-in's
    hand-placed art pixels alternate widths. `fractional` is for a creature
    whose frames are a sprite sheet, where a size change is a resample of an
    image — there the whole-number steps are too coarse to be useful, because
    the next size up from 1 is twice as big."""
    try:
        n = round(float(value), 1) if fractional else int(value)
    except (TypeError, ValueError):
        return DEFAULT_SCALE
    return max(MIN_SCALE, min(MAX_SCALE, n))


def _hex_to_rgb(h):
    if not isinstance(h, str):
        return None
    h = h.strip()
    if not h.startswith("#") or len(h) != 7:
        return None
    try:
        return tuple(int(h[i:i + 2], 16) / 255.0 for i in (1, 3, 5))
    except ValueError:
        return None


def derive_palette(base):
    """A four-colour creature palette from one colour, or None if unusable.

    The renderer wants body/highlight/shade/accent, but asking a person for
    four colours asks them to keep four in harmony. Moving LIGHTNESS only --
    hue and saturation untouched -- keeps them a family whatever colour is
    picked; the amounts come from the hand-tuned palettes, whose highlights and
    shades sit about this far from their body colour.

    The hand-tuned palettes themselves are NOT re-derived. Running this on
    `default`'s body misses its accent by a long way: #D0402E is a red alert
    colour, not a darkened body. Keeping the existing creatures pixel-identical
    beats a tidier rule. Pure."""
    import colorsys
    rgb = _hex_to_rgb(base)
    if rgb is None:
        return None
    h, l, sat = colorsys.rgb_to_hls(*rgb)

    def shift(dl):
        r, g, b = colorsys.hls_to_rgb(h, max(0.0, min(1.0, l + dl)), sat)
        return "#%02X%02X%02X" % (round(r * 255), round(g * 255), round(b * 255))

    return {"body": shift(0.0), "hi": shift(0.16),
            "lo": shift(-0.16), "bang": shift(-0.21)}


def resolve_palette(config_value, roll, pick=0.0):
    """Map a config palette value to a concrete palette name.

    config_value: "auto" (default) / a known name / anything else.
    roll: 0..1 shiny chance draw (caller passes random()). pick: 0..1 chooses
    among shinies. Pure & deterministic for tests — no randomness inside."""
    if config_value in (None, "auto"):
        if roll < SHINY_CHANCE:
            idx = int(pick * len(SHINY_PALETTES)) % len(SHINY_PALETTES)
            return SHINY_PALETTES[idx]
        return "default"
    if config_value in ("default",) + SHINY_PALETTES:
        return config_value
    if isinstance(config_value, str) and config_value.startswith("#"):
        # a colour the user picked: derived here rather than named. Returns the
        # palette itself, which the renderer accepts in place of a name.
        return derive_palette(config_value) or "default"
    return "default"


def _empty_config():
    return {"tool_states": {}, "event_states": {}, "raw_events": {},
            "lang": "auto", "roam_area": None, "no_go": [], "palette": "auto",
            "scale": DEFAULT_SCALE, "avatar": None, "creatures": {},
            "dock": default_dock()}


def load_config(path=None):
    """Read + validate the config file. Never raises: a missing/broken file
    yields empty overrides (built-in defaults apply)."""
    path = path or config_path()
    try:
        with open(path, encoding="utf-8") as f:
            raw = json.load(f)
    except (OSError, ValueError):
        return _empty_config()
    if not isinstance(raw, dict):
        return _empty_config()
    return _clean(raw)


def _read_raw(path):
    try:
        with open(path, encoding="utf-8") as f:
            raw = json.load(f)
        return raw if isinstance(raw, dict) else {}
    except (OSError, ValueError):
        return {}


def _write_raw(raw, path):
    """Replace config.json atomically. Silent on failure: not remembering a
    setting beats taking the pet down."""
    try:
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        tmp = "%s.%d.tmp" % (path, os.getpid())
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(raw, f, indent=2, ensure_ascii=False)
            f.write("\n")
        os.replace(tmp, path)      # 반쯤 쓰인 config를 다른 펫이 읽지 않도록
        return True
    except OSError:
        return False


def save_keys(updates, path=None):
    """Merge top-level keys into config.json and return the cleaned config.

    Read-modify-write, like save_dock: the settings UI writes two keys and must
    not erase the tools/events a user wrote by hand."""
    path = path or config_path()
    raw = _read_raw(path)
    raw.update(updates)
    _write_raw(raw, path)
    return _clean(raw)


def save_dock(updates, path=None):
    """config.json의 `dock` 하위 키만 병합해 저장하고 저장된 dock 섹션을 돌려준다.

    펫이 드래그로 옮겨진 위치를 기억하는 경로라서 read-modify-write다 — 파일을
    통째로 덮어쓰면 사용자가 손으로 적은 tools/events가 날아간다. 파일이 깨져
    있거나 쓸 수 없으면 기본값에 updates만 얹은 값을 돌려주고 조용히 넘어간다:
    위치를 못 기억하는 것이 펫이 죽는 것보다 낫다.
    """
    path = path or config_path()
    raw = _read_raw(path)
    merged = dict(raw.get("dock") or {})
    merged.update(updates)
    raw["dock"] = merged
    _write_raw(raw, path)
    return _clean_dock(merged)


def clean_avatar(raw):
    """The worn creature: one name for every agent (legacy), or a per-agent map
    {"claude": "claudlet", "codex": "codex"}. Junk entries are dropped rather
    than failing the whole config."""
    if isinstance(raw, str) and raw:
        return raw
    if isinstance(raw, dict):
        out = {k: v for k, v in raw.items()
               if isinstance(k, str) and isinstance(v, str) and v}
        return out or None
    return None


def avatar_for(cfg, agent):
    """Creature this agent's pet wears per the user's config, or None when the
    user has not chosen -- the caller then falls back to the agent's registry
    default and finally to the built-in."""
    a = (cfg or {}).get("avatar")
    if isinstance(a, dict):
        return a.get(agent)
    return a if isinstance(a, str) and a else None
