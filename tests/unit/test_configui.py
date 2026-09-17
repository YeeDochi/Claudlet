"""The creature settings page, without a socket.

Request handling is pure functions over data; the HTTP class is a shell. These
check what the page is told and what a save actually writes.
"""
import json
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from claudlet.cli import configui as U
from claudlet.core import petconfig


def _cfg(tmp_path, monkeypatch, **keys):
    path = tmp_path / "config.json"
    path.write_text(json.dumps(keys), encoding="utf-8")
    monkeypatch.setattr(petconfig, "config_path", lambda: str(path))
    return path


def test_page_state_reports_what_the_controls_need(tmp_path, monkeypatch):
    _cfg(tmp_path, monkeypatch, palette="#4A90D9", scale=9)
    s = U.state_payload()
    assert s["colour"] == "#4A90D9" and s["named"] is False
    assert s["scale"] == 9
    assert s["scale_range"] == [petconfig.MIN_SCALE, petconfig.MAX_SCALE]
    assert s["avatars"][0]["name"] == "claudlet"


def test_a_named_palette_opens_the_picker_on_a_real_colour(tmp_path, monkeypatch):
    # "auto"/"shiny_teal" have no single colour; the picker still needs one
    _cfg(tmp_path, monkeypatch, palette="auto")
    s = U.state_payload()
    assert s["named"] is True
    assert s["colour"].startswith("#") and len(s["colour"]) == 7


def test_only_recognised_keys_are_written(tmp_path, monkeypatch):
    # this endpoint edits the same file a user hand-writes tools/events into
    C = U.clean_creature_updates
    assert C({"palette": "#4A90D9"}) == {"palette": "#4A90D9"}
    assert C({"palette": "shiny_teal"}) == {"palette": "shiny_teal"}
    assert C({"palette": "; rm -rf /"}) == {"palette": None}   # None = clear it
    assert C({"tool_states": {"Bash": "sing"}}) == {}
    assert C({"scale": 99}) == {"scale": petconfig.MAX_SCALE}
    assert C({"visor": "on"}) == {"visor": "on"}
    assert C({"visor": "nonsense"}) == {"visor": petconfig.DEFAULT_VISOR}


def test_saving_keeps_hand_written_settings(tmp_path, monkeypatch):
    path = _cfg(tmp_path, monkeypatch, tools={"Bash": "sing"}, avatar="claudlet")
    U.apply({"palette": "#2FA88C", "scale": 7}, broadcast=lambda line: 0)
    raw = json.loads(path.read_text(encoding="utf-8"))
    assert raw["tools"] == {"Bash": "sing"}        # untouched
    # appearance lands UNDER the creature it was set on
    assert raw["creatures"]["claudlet"] == {"palette": "#2FA88C", "scale": 7}


def test_one_creatures_colour_does_not_repaint_another(tmp_path, monkeypatch):
    # the whole point of per-creature settings: switching creature must not
    # drag the previous one's look along
    path = _cfg(tmp_path, monkeypatch, avatar="claudlet")
    U.apply({"palette": "#2FA88C"}, broadcast=lambda line: 0)
    U.apply({"avatar": "claudlet", "palette": "#4A90D9"}, broadcast=lambda line: 0)
    raw = json.loads(path.read_text(encoding="utf-8"))
    assert raw["creatures"]["claudlet"]["palette"] == "#4A90D9"


def test_saving_tells_running_pets_to_restyle(tmp_path, monkeypatch):
    _cfg(tmp_path, monkeypatch)
    sent = []
    out = U.apply({"scale": 8}, broadcast=lambda line: sent.append(line) or 3)
    assert json.loads(sent[0]) == {"cmd": "restyle"}
    assert out["pets"] == 3 and out["applied"] == ["scale"]
    assert out["scale"] == 8                       # page redraws from this


def test_nothing_to_save_tells_nobody(tmp_path, monkeypatch):
    _cfg(tmp_path, monkeypatch)
    sent = []
    out = U.apply({"nonsense": 1}, broadcast=lambda line: sent.append(line) or 1)
    assert sent == [] and out["applied"] == []


def test_no_pet_running_is_not_an_error(tmp_path, monkeypatch):
    _cfg(tmp_path, monkeypatch)

    def boom(line):
        raise OSError("no pets")

    assert U.apply({"scale": 6}, broadcast=boom)["pets"] == 0


def test_preview_renders_a_png_at_the_asked_scale():
    small = U.render_png("#4A90D9", 3)
    big = U.render_png("#4A90D9", 9)
    assert small[:4] == b"\x89PNG" and big[:4] == b"\x89PNG"
    assert len(big) > len(small)      # more pixels, not a cached one-size image


def test_preview_never_rolls_a_shiny():
    # "auto" rolls a rare shiny in a pet; a preview that did would show a
    # colour the user did not pick
    for _ in range(20):
        assert U.render_png("auto", 3)[:4] == b"\x89PNG"


def test_reset_goes_back_to_the_defaults(tmp_path, monkeypatch):
    # once a colour is picked there has to be a way back: "auto" is what rolls
    # the rare shiny again, and scale returns to the built-in size
    path = _cfg(tmp_path, monkeypatch, avatar="claudlet",
                creatures={"claudlet": {"palette": "#00FFCC", "scale": 9,
                                        "visor": "on"}})
    # clearing, not storing "auto": a stored value is a choice the user made and
    # outranks the creature's own default, so resetting has to REMOVE it
    out = U.apply({"palette": None, "scale": None, "visor": None},
                  broadcast=lambda line: 1)
    raw = json.loads(path.read_text(encoding="utf-8"))["creatures"]["claudlet"]
    assert raw == {}
    assert out["named"] is True and out["scale"] == petconfig.DEFAULT_SCALE


def test_preview_shows_the_colour_being_picked_not_the_saved_one(tmp_path,
                                                                 monkeypatch):
    # the page renders the picker's current value, which is not yet in config
    _cfg(tmp_path, monkeypatch, palette="#00FFCC")
    picked = U.render_png("#D97757", 5, "idle")
    saved = U.render_png("#00FFCC", 5, "idle")
    assert picked != saved


def test_preview_is_of_the_chosen_creature_not_the_builtin(tmp_path, monkeypatch):
    # picking a creature and being shown claudlet is worse than no preview
    _cfg(tmp_path, monkeypatch)
    a = U.render_png("#D97757", 5, "idle", avatar="claudlet")
    b = U.render_png("#D97757", 5, "idle", avatar="nosuchcreature")
    assert a == b                      # unknown falls back, same picture
    assert a[:4] == b"\x89PNG"


def test_page_lists_which_states_each_creature_can_show(tmp_path, monkeypatch):
    # a creature need not draw every state; the preview row follows what it
    # declares rather than showing rows of fallback
    _cfg(tmp_path, monkeypatch)
    s = U.state_payload()
    assert set(s["avatar_states"]) == set(a["name"] for a in s["avatars"])
    for shown in s["avatar_states"].values():
        assert shown, "a creature must preview at least one state"


def test_each_creature_card_carries_its_own_colour(tmp_path, monkeypatch):
    # the list showed every creature in the worn one's colour, so it told you
    # nothing about what picking a different one would give you
    _cfg(tmp_path, monkeypatch, avatar="claudlet",
         creatures={"claudlet": {"palette": "#00FFCC"}})
    by_name = {a["name"]: a for a in U.state_payload()["avatars"]}
    assert by_name["claudlet"]["colour"] == "#00FFCC"


def test_settings_save_to_the_creature_being_viewed_not_the_one_worn(
        tmp_path, monkeypatch):
    # looking at another creature's settings must not require putting it on
    path = _cfg(tmp_path, monkeypatch, avatar="claudlet")
    U.apply({"creature": "claudlet", "palette": "#4A90D9"},
            broadcast=lambda line: 0)
    raw = json.loads(path.read_text(encoding="utf-8"))
    assert raw["avatar"] == "claudlet"                    # still worn
    assert raw["creatures"]["claudlet"]["palette"] == "#4A90D9"


def test_wearing_a_creature_is_its_own_action(tmp_path, monkeypatch):
    # switching creature and saving settings are separate buttons, so posting
    # only an avatar changes what is worn and touches nothing else
    path = _cfg(tmp_path, monkeypatch, avatar="claudlet",
                creatures={"claudlet": {"palette": "#00FFCC"}})
    U.apply({"avatar": "claudlet"}, broadcast=lambda line: 0)
    raw = json.loads(path.read_text(encoding="utf-8"))
    assert raw["creatures"]["claudlet"]["palette"] == "#00FFCC"   # untouched


def test_page_carries_every_creatures_settings(tmp_path, monkeypatch):
    # so the panel can show one without a round trip, and without wearing it
    _cfg(tmp_path, monkeypatch)
    s = U.state_payload()
    assert set(s["looks"]) == set(a["name"] for a in s["avatars"])
    for look in s["looks"].values():
        assert set(look) == {"palette", "scale", "visor"}


def test_the_server_stops_once_the_page_stops_saying_it_is_open():
    """Opened from the pet's right-click menu there is no terminal to Ctrl-C,
    and closing the tab would otherwise leave a server running all session. The
    page says it is there; the server stops when that stops."""
    import threading
    import time

    alive = {"v": True}

    def run():
        U.serve(open_browser=False, idle_timeout=0.6)
        alive["v"] = False

    t = threading.Thread(target=run, daemon=True)
    t.start()
    t.join(timeout=15)
    assert alive["v"] is False, "settings server outlived its page"


def test_the_page_sends_a_heartbeat_and_a_goodbye():
    pg = U.page({})
    assert "/api/alive" in pg and str(U.HEARTBEAT_MS) in pg
    assert "/api/bye" in pg              # closing the tab stops it at once


def test_the_page_follows_the_language_setting():
    # the pet already speaks the user's language; the settings page shipped
    # Korean-only, which was fine while it was one developer's tool
    ko, en = U.page({"lang": "ko"}), U.page({"lang": "en"})
    assert "크리처" in ko and "Creatures" in en
    assert "크리처" not in en
    for pg in (ko, en):
        assert "__T_" not in pg, "an untranslated placeholder reached the page"


def test_both_languages_say_the_same_things():
    # a missing key would render as a literal __T_whatever__ in someone's page
    assert set(U.TEXT["ko"]) == set(U.TEXT["en"])
    assert all(U.TEXT["ko"].values()) and all(U.TEXT["en"].values())
