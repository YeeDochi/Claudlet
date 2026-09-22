"""The creature settings page, without a socket.

Request handling is pure functions over data; the HTTP class is a shell. These
check what the page is told and what a save actually writes.
"""
import json
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from claudlet.cli import configui
from claudlet.cli import configui as U
from claudlet.core import agents, avatars, petconfig


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
        assert set(look) == {"palette", "scale", "visor", "persona"}


def test_the_server_stops_once_the_page_stops_saying_it_is_open():
    """Opened from the pet's right-click menu there is no terminal to Ctrl-C,
    and closing the tab would otherwise leave a server running all session. The
    page says it is there; the server stops when that stops."""
    import threading
    import time

    alive = {"v": True}

    def run():
        U.serve(open_browser=False, idle_timeout=0.6, port=0)
        alive["v"] = False

    t = threading.Thread(target=run, daemon=True)
    t.start()
    t.join(timeout=15)
    assert alive["v"] is False, "settings server outlived its page"


def test_bye_last_seen_leaves_a_grace_window_not_instant_death():
    # a page REFRESH fires the same pagehide -> bye as a real close; killing
    # the server at once (old last_seen=0.0) stranded the refresh on a dead
    # port. bye_last_seen must leave `grace` seconds of runway instead.
    now = 1000.0
    ls = U.bye_last_seen(now, idle_timeout=90.0, grace=5.0)
    assert ls == now - 85.0
    assert 0 < now - ls < 90.0          # some life left, not none, not more


def test_bye_last_seen_clamps_when_grace_exceeds_timeout():
    # a huge grace must not read as MORE time left than the server ever had
    assert U.bye_last_seen(1000.0, idle_timeout=2.0, grace=5.0) == 1000.0


def test_a_refresh_survives_but_a_real_close_still_dies():
    # simulate what the handler does on bye: a refresh's next request lands
    # inside the grace window and revives the server; a real close, with no
    # further request, still expires within grace of the original timeout.
    import threading
    import time
    import urllib.request
    from http.server import HTTPServer

    srv = HTTPServer(("127.0.0.1", 0), U._handler_class())
    srv.timeout = 0.2
    srv.idle_timeout = 1.0
    srv.last_seen = time.monotonic()
    url = "http://127.0.0.1:%d" % srv.server_port

    def serve_until_dead():
        while time.monotonic() - srv.last_seen < srv.idle_timeout:
            srv.handle_request()
        srv.server_close()

    t = threading.Thread(target=serve_until_dead, daemon=True)
    t.start()
    # a "refresh": bye, then immediately a follow-up request (a real browser
    # would fetch /api/state next)
    urllib.request.urlopen(url + "/api/bye", timeout=5).read()
    urllib.request.urlopen(url + "/api/state", timeout=5).read()   # revives it
    assert t.is_alive(), "a refresh's bye should not have killed the server"
    t.join(timeout=10)
    assert not t.is_alive(), "server should still expire eventually"


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


def test_state_payload_lists_detected_agents(monkeypatch):
    monkeypatch.setattr(agents, "detected", lambda home=None: ["claude", "codex"])
    p = configui.state_payload({"avatar": {"claude": "claudlet", "codex": "codex"}})
    names = [a["name"] for a in p["agents"]]
    assert names == ["claude", "codex"]
    assert [a["creature"] for a in p["agents"]] == ["claudlet", "codex"]
    assert p["agents"][0]["label"] == "Claude Code"


def test_state_payload_hides_the_chip_row_for_a_single_agent(monkeypatch):
    monkeypatch.setattr(agents, "detected", lambda home=None: ["claude"])
    assert configui.state_payload({"avatar": "claudlet"})["agents"] == []


def test_wearing_a_creature_writes_only_that_agents_key(monkeypatch):
    saved = {}
    monkeypatch.setattr(agents, "detected", lambda home=None: ["claude", "codex"])
    monkeypatch.setattr(configui.petconfig, "load_config",
                        lambda: {"avatar": {"claude": "claudlet", "codex": "codex"}})
    monkeypatch.setattr(configui.petconfig, "save_keys", saved.update)

    configui.apply({"agent": "codex", "avatar": "slime"}, broadcast=lambda p: 0)

    assert saved["avatar"] == {"claude": "claudlet", "codex": "slime"}


def test_save_and_reset_js_post_the_agent_too(tmp_path, monkeypatch):
    # The "wear" button already posted {agent: S.agent, ...}; save/reset did
    # not, so current_agent() fell back to the default agent and the page
    # snapped back to it after every save/reset on a non-default agent.
    _cfg(tmp_path, monkeypatch)
    pg = U.page({})
    save_call = pg[pg.index('$("save").addEventListener'):]
    save_call = save_call[:save_call.index("async function doWear")]
    assert "agent: S.agent" in save_call
    reset_call = pg[pg.index('$("reset").addEventListener'):]
    assert "agent: S.agent" in reset_call


def test_serve_initial_agent_seeds_the_first_state_response(monkeypatch):
    # pet.py threads its own self.agent through `configcli ui --agent ...`
    # into configui.serve(agent=...); the FIRST /api/state fetch (no query
    # string yet) must reflect it, or a Codex pet's settings page would still
    # open showing Claude.
    import threading
    import urllib.request
    from http.server import HTTPServer

    monkeypatch.setattr(agents, "detected", lambda home=None: ["claude", "codex"])
    srv = HTTPServer(("127.0.0.1", 0), U._handler_class(initial_agent="codex"))
    srv.timeout = 5
    t = threading.Thread(target=srv.handle_request, daemon=True)
    t.start()
    try:
        with urllib.request.urlopen(
                "http://127.0.0.1:%d/api/state" % srv.server_port, timeout=5) as r:
            data = json.loads(r.read())
        assert data["agent"] == "codex"
    finally:
        t.join(timeout=5)
        srv.server_close()


def test_current_agent_takes_only_the_body(tmp_path, monkeypatch):
    # the `cfg` parameter was unused dead weight
    assert U.current_agent({"agent": "codex"}) == "codex"
    assert U.current_agent({}) == agents.DEFAULT
    assert U.current_agent({"agent": "nonsense"}) == agents.DEFAULT


# ---------- export / import ----------

def test_export_api_returns_the_written_path(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    out = U.export_api({"creature": "slime", "out": str(tmp_path)})
    assert "error" not in out
    assert os.path.isfile(out["path"])
    assert out["path"] == str(tmp_path / "slime.claudlet-creature.zip")


def test_export_api_bad_creature_writes_nothing(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    out = U.export_api({"creature": "nonexistent-creature", "out": str(tmp_path)})
    assert out.get("error")
    assert list(tmp_path.iterdir()) == []


def test_export_api_defaults_to_home_directory_when_out_is_empty(tmp_path, monkeypatch):
    monkeypatch.setattr(os.path, "expanduser", lambda p: str(tmp_path) if p == "~" else p)
    out = U.export_api({"creature": "slime"})
    assert out["path"] == str(tmp_path / "slime.claudlet-creature.zip")
    assert os.path.isfile(out["path"])


def _zip(path, top, files):
    import zipfile
    with zipfile.ZipFile(path, "w") as zf:
        for rel, content in files.items():
            zf.writestr("%s/%s" % (top, rel), content)
    return path


def test_import_api_inspect_step_writes_nothing(tmp_path, monkeypatch):
    creatures_dir = tmp_path / "creatures"
    monkeypatch.setattr(avatars, "CREATURES_DIR", str(creatures_dir))
    zpath = _zip(tmp_path / "cool.zip", "cool", {"__init__.py": "AVATAR = None\n"})

    out = U.import_api({"path": str(zpath)})

    assert out["name"] == "cool"
    assert out["entries"] == ["cool/__init__.py"]
    assert not creatures_dir.exists()


def test_import_api_confirm_step_installs(tmp_path, monkeypatch):
    creatures_dir = tmp_path / "creatures"
    monkeypatch.setattr(avatars, "CREATURES_DIR", str(creatures_dir))
    zpath = _zip(tmp_path / "cool.zip", "cool", {"__init__.py": "AVATAR = None\n"})

    out = U.import_api({"path": str(zpath), "confirm": True})

    assert out["name"] == "cool"
    assert (creatures_dir / "cool" / "__init__.py").exists()


def test_import_api_rejects_path_traversal_and_writes_nothing(tmp_path, monkeypatch):
    import zipfile
    creatures_dir = tmp_path / "creatures"
    monkeypatch.setattr(avatars, "CREATURES_DIR", str(creatures_dir))
    p = tmp_path / "evil.zip"
    with zipfile.ZipFile(p, "w") as zf:
        zf.writestr("cool/__init__.py", "AVATAR = None\n")
        zf.writestr("cool/../../evil.py", "pwned = True\n")

    out = U.import_api({"path": str(p)})

    assert out.get("error") and "unsafe" in out["error"]
    assert not creatures_dir.exists()

    out2 = U.import_api({"path": str(p), "confirm": True})
    assert out2.get("error")
    assert not creatures_dir.exists()


def test_import_api_rejects_dot_top_level_archive(tmp_path, monkeypatch):
    import zipfile
    creatures_dir = tmp_path / "creatures"
    monkeypatch.setattr(avatars, "CREATURES_DIR", str(creatures_dir))
    p = tmp_path / "evil.zip"
    with zipfile.ZipFile(p, "w") as zf:
        zf.writestr("./pwn.py", "pwned = True\n")

    out = U.import_api({"path": str(p)})

    assert out.get("error")
    assert not creatures_dir.exists()


# ---------- import token gate ----------
# /api/import is the one endpoint that plants (and later executes) new code
# on disk, so unlike every other endpoint here it requires the per-run token
# the page was served with. A filesystem-sandboxed-but-loopback-reachable
# caller (e.g. Codex under bubblewrap) must not be able to use it blind.

def _post(srv, path, body):
    import urllib.error
    import urllib.request
    req = urllib.request.Request(
        "http://127.0.0.1:%d%s" % (srv.server_port, path),
        data=json.dumps(body).encode("utf-8"),
        headers={"content-type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=5) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())


def test_import_inspect_refused_without_or_with_wrong_token(tmp_path, monkeypatch):
    import threading
    from http.server import HTTPServer

    creatures_dir = tmp_path / "creatures"
    monkeypatch.setattr(avatars, "CREATURES_DIR", str(creatures_dir))
    zpath = _zip(tmp_path / "cool.zip", "cool", {"__init__.py": "AVATAR = None\n"})

    srv = HTTPServer(("127.0.0.1", 0), U._handler_class(import_token="right-token"))
    srv.timeout = 5
    try:
        for body in ({"path": str(zpath)}, {"path": str(zpath), "token": "wrong"}):
            t = threading.Thread(target=srv.handle_request, daemon=True)
            t.start()
            code, out = _post(srv, "/api/import", body)
            t.join(timeout=5)
            assert code == 403
            assert out.get("error")
            assert not creatures_dir.exists()
    finally:
        srv.server_close()


def test_import_confirm_refused_without_or_with_wrong_token(tmp_path, monkeypatch):
    import threading
    from http.server import HTTPServer

    creatures_dir = tmp_path / "creatures"
    monkeypatch.setattr(avatars, "CREATURES_DIR", str(creatures_dir))
    zpath = _zip(tmp_path / "cool.zip", "cool", {"__init__.py": "AVATAR = None\n"})

    srv = HTTPServer(("127.0.0.1", 0), U._handler_class(import_token="right-token"))
    srv.timeout = 5
    try:
        for body in ({"path": str(zpath), "confirm": True},
                     {"path": str(zpath), "confirm": True, "token": "wrong"}):
            t = threading.Thread(target=srv.handle_request, daemon=True)
            t.start()
            code, out = _post(srv, "/api/import", body)
            t.join(timeout=5)
            assert code == 403
            assert out.get("error")
            assert not creatures_dir.exists()
    finally:
        srv.server_close()


def test_import_with_the_right_token_still_works(tmp_path, monkeypatch):
    import threading
    from http.server import HTTPServer

    creatures_dir = tmp_path / "creatures"
    monkeypatch.setattr(avatars, "CREATURES_DIR", str(creatures_dir))
    zpath = _zip(tmp_path / "cool.zip", "cool", {"__init__.py": "AVATAR = None\n"})

    srv = HTTPServer(("127.0.0.1", 0), U._handler_class(import_token="right-token"))
    srv.timeout = 5
    try:
        t = threading.Thread(target=srv.handle_request, daemon=True)
        t.start()
        code, out = _post(srv, "/api/import", {"path": str(zpath), "token": "right-token"})
        t.join(timeout=5)
        assert code == 200
        assert out["name"] == "cool" and not creatures_dir.exists()   # inspect only

        t = threading.Thread(target=srv.handle_request, daemon=True)
        t.start()
        code, out = _post(srv, "/api/import",
                          {"path": str(zpath), "confirm": True, "token": "right-token"})
        t.join(timeout=5)
        assert code == 200
        assert out["name"] == "cool"
        assert (creatures_dir / "cool" / "__init__.py").exists()
    finally:
        srv.server_close()


def test_the_page_carries_the_current_runs_token():
    pg = U.page({}, import_token="a-run-specific-token")
    assert "a-run-specific-token" in pg


def test_two_serve_setups_do_not_share_a_token():
    # exactly what serve() does per call: a fresh token, threaded through
    # _handler_class into the served page
    import secrets
    import threading
    import urllib.request
    from http.server import HTTPServer

    def one():
        tok = secrets.token_urlsafe(16)
        srv = HTTPServer(("127.0.0.1", 0), U._handler_class(import_token=tok))
        srv.timeout = 5
        t = threading.Thread(target=srv.handle_request, daemon=True)
        t.start()
        with urllib.request.urlopen(
                "http://127.0.0.1:%d/" % srv.server_port, timeout=5) as r:
            pg = r.read().decode("utf-8")
        t.join(timeout=5)
        srv.server_close()
        return tok, pg

    tok1, pg1 = one()
    tok2, pg2 = one()
    assert tok1 != tok2
    assert tok1 in pg1 and tok2 not in pg1
    assert tok2 in pg2 and tok1 not in pg2


def test_page_inserts_entry_names_as_text_not_html():
    pg = U.page({})
    share = pg[pg.index("renderImportInfo("):]
    share = share[:share.index("$(\"importInspect\")")]
    assert "li.textContent = e" in share
    assert "innerHTML = e" not in share
    assert "+= e" not in share
    assert "innerHTML += " not in pg


def test_legacy_string_avatar_is_promoted_without_losing_the_choice(monkeypatch):
    saved = {}
    monkeypatch.setattr(agents, "detected", lambda home=None: ["claude", "codex"])
    monkeypatch.setattr(configui.petconfig, "load_config", lambda: {"avatar": "slime"})
    monkeypatch.setattr(configui.petconfig, "save_keys", saved.update)

    configui.apply({"agent": "codex", "avatar": "astronaut"}, broadcast=lambda p: 0)

    # claude keeps what the single string meant; only codex changes
    assert saved["avatar"] == {"claude": "slime", "codex": "astronaut"}


# ---------- one fixed origin: port choice, singleton, app window ----------

def test_port_plan_binds_the_preferred_port_when_it_is_free():
    assert U.port_plan(8770, lambda p: "free") == ("bind", 8770)


def test_port_plan_hands_over_to_a_settings_server_already_running():
    # clicking "settings" twice, or from two pets, must not start two servers
    assert U.port_plan(8770, lambda p: "ours") == ("attach", 8770)


def test_port_plan_falls_back_when_someone_else_holds_the_port():
    # 0 = let the OS pick, the behaviour this page always had
    assert U.port_plan(8770, lambda p: "other") == ("fallback", 0)


def _spawn(handler_cls):
    """A one-request server on an OS-chosen port; returns (port, join)."""
    import threading
    from http.server import HTTPServer
    srv = HTTPServer(("127.0.0.1", 0), handler_cls)
    srv.timeout = 5
    srv.last_seen = __import__("time").monotonic()
    srv.idle_timeout = 5.0
    t = threading.Thread(target=srv.handle_request, daemon=True)
    t.start()
    return srv, t


def test_probe_port_tells_free_from_ours_from_a_stranger():
    import socket
    from http.server import BaseHTTPRequestHandler

    # free: nothing listening. Grab a port, then let it go.
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    free_port = s.getsockname()[1]
    s.close()
    assert U.probe_port(free_port) == "free"

    srv, t = _spawn(U._handler_class())
    try:
        assert U.probe_port(srv.server_port) == "ours"
    finally:
        t.join(timeout=5)
        srv.server_close()

    class Stranger(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def do_GET(self):
            body = b'{"ok": true}'
            self.send_response(200)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    srv, t = _spawn(Stranger)
    try:
        assert U.probe_port(srv.server_port) == "other"
    finally:
        t.join(timeout=5)
        srv.server_close()


def test_probe_port_calls_a_free_port_free_even_when_the_connect_times_out():
    # the Windows case: a closed loopback port drops the SYN instead of
    # refusing, so the probe times out. Deciding "free" from the connect error
    # read that as a stranger's server, and the settings app fell back to an
    # OS-chosen port on every launch instead of reusing its fixed one.
    import socket
    import urllib.error
    import urllib.request

    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    free_port = s.getsockname()[1]
    s.close()

    def timing_out(*a, **k):
        raise urllib.error.URLError(TimeoutError("timed out"))

    real = urllib.request.urlopen
    urllib.request.urlopen = timing_out
    try:
        assert U.probe_port(free_port) == "free"
    finally:
        urllib.request.urlopen = real


def test_serve_attaches_to_a_running_settings_server_instead_of_a_second_one():
    srv, t = _spawn(U._handler_class())
    try:
        url = U.serve(open_browser=False, port=srv.server_port)
    finally:
        t.join(timeout=5)
        srv.server_close()
    # it returned the RUNNING server's url at once instead of serving its own
    assert url == "http://127.0.0.1:%d/" % srv.server_port


def test_browser_command_opens_an_app_window_with_the_first_browser_found():
    which = {"chromium": "/usr/bin/chromium"}.get
    cmd = U.browser_command("http://127.0.0.1:8770/", which=which, size=(900, 700),
                            profile_dir="/fake/claudlet/chrome-profile")
    assert cmd[:3] == ["/usr/bin/chromium", "--app=http://127.0.0.1:8770/",
                       "--window-size=900,700"]
    # the window must carry our own identity, or a desktop attributes it to
    # whatever owns the display it opened on (seen live: a gamescope-provided
    # X display made the app and its icon show up as "gamescope")
    assert "--class=claudlet" in cmd
    # and on a Wayland session with an X server also present, let Chrome pick
    # Wayland instead of silently falling back to X11
    assert "--ozone-platform-hint=auto" in cmd


def test_browser_command_uses_its_own_chrome_profile_not_the_running_one():
    # verified live: without --user-data-dir, an already-running Chrome just
    # hands the URL to itself and exits -- no process carrying --app= exists
    # afterward, and every flag here (window size, class) is silently ignored
    which = {"chromium": "/usr/bin/chromium"}.get
    cmd = U.browser_command("http://x/", which=which,
                            profile_dir="/home/user/.cache/claudlet/chrome-profile")
    assert "--user-data-dir=/home/user/.cache/claudlet/chrome-profile" in cmd
    assert "--no-first-run" in cmd
    assert "--no-default-browser-check" in cmd


def test_chrome_profile_dir_is_claudlet_owned_not_the_users_default(tmp_path):
    d = U.chrome_profile_dir(cache_home=str(tmp_path))
    assert d == str(tmp_path / "claudlet" / "chrome-profile")
    # never the real default profile a running Chrome already uses
    assert "google-chrome" not in d and "chromium" not in d.split(os.sep)[-1]


def test_chrome_profile_dir_defaults_under_xdg_cache_home(monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path))
    assert U.chrome_profile_dir() == str(tmp_path / "claudlet" / "chrome-profile")


def test_browser_command_prefers_the_earlier_browser_in_the_list():
    both = {"google-chrome": "/g", "brave-browser": "/b"}.get
    assert U.browser_command("http://x/", which=both)[0] == "/g"


def test_browser_command_is_none_without_a_chromium_family_browser():
    # macOS / Windows boxes usually have none of these on PATH -- the caller
    # then opens the default browser the old way
    assert U.browser_command("http://x/", which=lambda n: None) is None


# ---------- installed-PWA lookup: find our settings page among installed
# chromium/edge web apps, so "settings" can open the app someone installed
# instead of always a plain tab ----------

_OURS = """[Desktop Entry]
Version=1.0
Terminal=false
Type=Application
Name=claudlet 크리처
Exec=/opt/google/chrome/google-chrome --profile-directory=Default --app-id=gflghkeoenmpajpibkmhelgbooaocgbf
Icon=chrome-gflghkeoenmpajpibkmhelgbooaocgbf-Default
StartupWMClass=crx_gflghkeoenmpajpibkmhelgbooaocgbf
"""

_DECOY = """[Desktop Entry]
Version=1.0
Terminal=false
Type=Application
Name=YouTube
Exec=/opt/google/chrome/google-chrome --profile-directory=Default --app-id=agimnkijcaahngcdmfeangaknmldooml %U
Icon=chrome-agimnkijcaahngcdmfeangaknmldooml-Default
StartupWMClass=crx_agimnkijcaahngcdmfeangaknmldooml
"""

_MALFORMED = "this is not a desktop entry at all\n%%%broken=="


def test_find_installed_pwa_matches_ours_among_several_entries():
    entries = {
        "chrome-agimnkijcaahngcdmfeangaknmldooml-Default.desktop": _DECOY,
        "chrome-gflghkeoenmpajpibkmhelgbooaocgbf-Default.desktop": _OURS,
        "chrome-broken-Default.desktop": _MALFORMED,
    }
    argv = U.find_installed_pwa(entries, "claudlet 크리처")
    assert argv == ["/opt/google/chrome/google-chrome",
                    "--profile-directory=Default",
                    "--app-id=gflghkeoenmpajpibkmhelgbooaocgbf"]


def test_find_installed_pwa_strips_field_codes():
    entries = {"msedge-x-Default.desktop": _DECOY.replace("chrome-", "msedge-")}
    argv = U.find_installed_pwa(entries, "YouTube")
    assert "%U" not in argv
    assert argv[-1] == "--app-id=agimnkijcaahngcdmfeangaknmldooml"


def test_find_installed_pwa_none_when_nothing_matches():
    entries = {"chrome-agimnkijcaahngcdmfeangaknmldooml-Default.desktop": _DECOY}
    assert U.find_installed_pwa(entries, "claudlet 크리처") is None


def test_find_installed_pwa_ignores_non_pwa_and_malformed_entries():
    entries = {"claudlet.desktop": "[Desktop Entry]\nName=claudlet 크리처\nExec=claudlet\n",
              "chrome-broken-Default.desktop": _MALFORMED}
    # "claudlet.desktop" isn't a chrome-/msedge- PWA entry, so even though its
    # Name matches it must not be picked up as the installed app
    assert U.find_installed_pwa(entries, "claudlet 크리처") is None


def test_find_installed_pwa_none_on_empty_or_missing_entries():
    assert U.find_installed_pwa({}, "claudlet 크리처") is None
    assert U.find_installed_pwa(None, "claudlet 크리처") is None


def test_installed_pwa_command_reads_the_real_directory(tmp_path):
    d = tmp_path / "applications"
    d.mkdir()
    (d / "chrome-decoy-Default.desktop").write_text(_DECOY, encoding="utf-8")
    (d / "chrome-ours-Default.desktop").write_text(_OURS, encoding="utf-8")
    argv = U.installed_pwa_command("claudlet 크리처", apps_dir=str(d))
    assert argv[0] == "/opt/google/chrome/google-chrome"
    assert "--app-id=gflghkeoenmpajpibkmhelgbooaocgbf" in argv


def test_installed_pwa_command_is_a_noop_when_the_directory_is_missing(tmp_path):
    # macOS / Windows: this directory never exists there
    assert U.installed_pwa_command("claudlet 크리처",
                                   apps_dir=str(tmp_path / "nope")) is None


def test_installed_pwa_command_skips_an_unreadable_entry(tmp_path, monkeypatch):
    d = tmp_path / "applications"
    d.mkdir()
    (d / "chrome-ours-Default.desktop").write_text(_OURS, encoding="utf-8")
    real_open = open

    def flaky_open(path, *a, **kw):
        if "chrome-ours" in str(path):
            raise OSError("permission denied")
        return real_open(path, *a, **kw)

    monkeypatch.setattr("builtins.open", flaky_open)
    # the one entry that would have matched is unreadable; still ends at None
    # (rather than raising) instead of crashing the whole lookup
    assert U.installed_pwa_command("claudlet 크리처", apps_dir=str(d)) is None


def test_find_windows_pwa_shortcut_matches_localized_start_menu_entry():
    paths = [
        r"C:\Users\u\AppData\Roaming\Microsoft\Windows\Start Menu\Programs\Chrome 앱\YouTube.lnk",
        r"C:\Users\u\AppData\Roaming\Microsoft\Windows\Start Menu\Programs\Chrome 앱\claudlet 크리처.lnk",
    ]
    assert U.find_windows_pwa_shortcut(paths, "claudlet 크리처") == paths[1]


def test_find_windows_pwa_shortcut_is_case_insensitive_and_skips_bad_values():
    paths = [None, r"C:\Apps\CLAUDLET 크리처.LNK"]
    assert U.find_windows_pwa_shortcut(paths, "claudlet 크리처") == paths[1]


def test_windows_pwa_lookup_walks_nested_start_menu_directory(tmp_path):
    app = tmp_path / "Chrome 앱" / "claudlet 크리처.lnk"
    app.parent.mkdir()
    app.write_text("shortcut")
    assert U._windows_pwa_shortcut("claudlet 크리처", [str(tmp_path)]) == str(app)


# ---------- launch order: explicit app window > installed PWA > ordinary
# browser, with every fallback intact ----------

def test_launch_browser_prefers_an_explicit_app_window(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(U, "browser_command", lambda url: ["explicit-app", url])
    monkeypatch.setattr(U, "installed_pwa_command", lambda *a, **kw: ["installed-pwa"])
    monkeypatch.setattr(U, "chrome_profile_dir", lambda: str(tmp_path / "profile"))
    import subprocess
    monkeypatch.setattr(subprocess, "Popen", lambda cmd, **kw: calls.append(cmd))
    U.launch_browser("http://x/", app_window=True)
    assert calls == [["explicit-app", "http://x/"]]


def _fixed_url():
    return "http://127.0.0.1:%d/" % U.PREFERRED_PORT


def test_launch_browser_falls_back_to_the_installed_pwa(monkeypatch):
    calls = []
    monkeypatch.setattr(U, "browser_command", lambda url: None)
    monkeypatch.setattr(U, "installed_pwa_command", lambda *a, **kw: ["installed-pwa"])
    import subprocess
    monkeypatch.setattr(subprocess, "Popen", lambda cmd, **kw: calls.append(cmd))
    U.launch_browser(_fixed_url(), app_window=False)
    assert calls == [["installed-pwa"]]


def test_launch_browser_falls_back_to_the_ordinary_browser(monkeypatch):
    opened = []
    monkeypatch.setattr(U, "browser_command", lambda url: None)
    monkeypatch.setattr(U, "installed_pwa_command", lambda *a, **kw: None)
    import webbrowser
    monkeypatch.setattr(webbrowser, "open", lambda url: opened.append(url))
    U.launch_browser("http://x/", app_window=False)
    assert opened == ["http://x/"]


def test_launch_browser_explicit_app_window_requested_but_absent_still_checks_pwa(monkeypatch):
    # app_window=True with no chromium-family browser on PATH (browser_command
    # returns None) must not stop at "no app window" -- it still falls
    # through to the installed-PWA step and then the ordinary browser.
    calls = []
    monkeypatch.setattr(U, "browser_command", lambda url: None)
    monkeypatch.setattr(U, "installed_pwa_command", lambda *a, **kw: ["installed-pwa"])
    import subprocess
    monkeypatch.setattr(subprocess, "Popen", lambda cmd, **kw: calls.append(cmd))
    U.launch_browser(_fixed_url(), app_window=True)
    assert calls == [["installed-pwa"]]


def test_launch_browser_a_lookup_error_still_ends_at_the_ordinary_browser(monkeypatch):
    opened = []
    monkeypatch.setattr(U, "browser_command", lambda url: None)

    def boom(*a, **kw):
        raise RuntimeError("should never escape launch_browser")

    monkeypatch.setattr(U, "installed_pwa_command", boom)
    import webbrowser
    monkeypatch.setattr(webbrowser, "open", lambda url: opened.append(url))
    U.launch_browser("http://x/", app_window=False)
    assert opened == ["http://x/"]


def test_launch_browser_opens_windows_pwa_shortcut_with_startfile(monkeypatch):
    opened = []
    monkeypatch.setattr(U, "browser_command", lambda url: None)
    monkeypatch.setattr(U, "installed_pwa_command",
                        lambda *a, **kw: r"C:\Apps\claudlet.lnk")
    monkeypatch.setattr(U.os, "name", "nt")
    monkeypatch.setattr(U.os, "startfile", lambda path: opened.append(path),
                        raising=False)
    U.launch_browser(_fixed_url(), app_window=False)
    assert opened == [r"C:\Apps\claudlet.lnk"]


# ---------- installable: manifest, service worker, icon ----------

def _get(port, path):
    import urllib.request
    with urllib.request.urlopen("http://127.0.0.1:%d%s" % (port, path),
                                timeout=5) as r:
        return r.headers.get("Content-Type"), r.read()


def test_alive_identifies_this_server_as_ours():
    srv, t = _spawn(U._handler_class())
    try:
        ctype, body = _get(srv.server_port, "/api/alive")
    finally:
        t.join(timeout=5)
        srv.server_close()
    assert json.loads(body) == {"ok": True, "app": U.APP_ID}


def test_manifest_declares_an_installable_standalone_app():
    m = U.manifest({})
    assert m["display"] == "standalone" and m["start_url"] == "/"
    assert m["theme_color"] == "#16161a" and m["background_color"] == "#16161a"
    assert [i["sizes"] for i in m["icons"]] == ["192x192", "512x512"]
    assert all(i["src"].startswith("/api/icon?size=") for i in m["icons"])


def test_manifest_and_worker_are_served_from_the_page_root():
    srv, t = _spawn(U._handler_class())
    try:
        ctype, body = _get(srv.server_port, "/manifest.webmanifest")
    finally:
        t.join(timeout=5)
        srv.server_close()
    assert "manifest" in ctype
    assert json.loads(body)["display"] == "standalone"

    srv, t = _spawn(U._handler_class())
    try:
        ctype, body = _get(srv.server_port, "/sw.js")
    finally:
        t.join(timeout=5)
        srv.server_close()
    assert "javascript" in ctype
    # Chrome only offers the install when a worker handles fetch
    assert 'addEventListener("fetch"' in body.decode("utf-8")


def test_the_page_links_the_manifest_and_registers_the_worker():
    pg = U.page({})
    assert 'rel="manifest" href="/manifest.webmanifest"' in pg
    assert 'serviceWorker.register("/sw.js")' in pg


def test_icon_is_a_square_png_at_the_size_asked_for():
    png = U.icon_png(192)
    if not png:
        return                       # no Qt here: same contract as the preview
    from PyQt6.QtGui import QImage
    img = QImage()
    img.loadFromData(png)
    assert (img.width(), img.height()) == (192, 192)


def test_icon_does_not_change_with_what_an_agent_is_wearing(tmp_path, monkeypatch):
    # a PWA has ONE icon per origin; two agents wearing two creatures have no
    # single right answer, so the app icon is fixed
    _cfg(tmp_path, monkeypatch, avatar={"claude": "slime"})
    a = U.icon_png(64)
    _cfg(tmp_path, monkeypatch, avatar={"claude": "claudlet"}, palette="#00FF00")
    assert U.icon_png(64) == a


def test_icon_endpoint_serves_a_png():
    srv, t = _spawn(U._handler_class())
    try:
        ctype, body = _get(srv.server_port, "/api/icon?size=192")
    finally:
        t.join(timeout=5)
        srv.server_close()
    assert ctype == "image/png"
    assert body[:8] == b"\x89PNG\r\n\x1a\n"


# ---------- the dashboard: tabs and refresh ----------

def test_the_page_picks_a_creature_from_a_dropdown_card_panel():
    # layout stability: an unbounded card list fights a fixed-size window with
    # no page scrollbar, so the cards live inside a collapsible panel behind a
    # trigger button instead of an always-open list or a native <select>
    pg = U.page({})
    assert '<select id="pick">' not in pg
    assert 'id="pickTrigger"' in pg and 'id="pickPanel"' in pg
    assert 'id="wornBadge"' in pg
    # exactly one apply button: the panel used to carry a duplicate of it
    assert pg.count('id="wear"') == 1 and 'id="wearTop"' not in pg
    assert 'aria-expanded="false"' in pg   # a real <button>, closed by default


def test_the_panel_is_populated_from_every_avatar_and_shows_worn_state():
    pg = U.page({})
    card_fn = pg[pg.index("function pickCardEl("):pg.index("function renderPickPanel()")]
    assert "a.selected" in card_fn
    assert "T.worn" in card_fn and "T.notworn" in card_fn
    # picking a card selects it for viewing, it does NOT wear it
    assert "showCreature(a.name)" in card_fn
    assert "doWear" not in card_fn
    panel_fn = pg[pg.index("function renderPickPanel()"):pg.index("function renderPickTrigger()")]
    assert "S.avatars" in panel_fn and "pickCardEl(a)" in panel_fn


def test_the_panel_closes_on_pick_outside_click_escape_and_refill():
    pg = U.page({})
    assert "closePanel(false);" in pg[pg.index("function pickCardEl("):]
    assert 'e.key === "Escape"' in pg and "closePanel(true)" in pg
    assert "onOutsideClick" in pg
    fill_fn = pg[pg.index("function fill(s) {"):pg.index('$("pickTrigger").addEventListener')]
    assert "closePanel(false);" in fill_fn   # never left open across a refill/tab switch


def test_the_page_has_one_tab_per_detected_agent_and_no_share_tab():
    pg = U.page({})
    assert 'id="tabs"' in pg
    assert "function tabRows" in pg
    assert "SHARE_TAB" not in pg
    assert 'id="share"' not in pg
    # tabs come from the detected agents in the state payload, so a third
    # agent appears with no code change; a single-agent machine (empty
    # s.agents) gets no tab row at all, not a lone toggle
    tabrows_fn = pg[pg.index("function tabRows("):pg.index("function paintTabs(")]
    assert "(s.agents || []).map" in tabrows_fn
    assert "T.title" not in tabrows_fn


def test_refresh_re_reads_the_state_without_a_page_reload():
    pg = U.page({})
    body = pg[pg.index("async function refresh()"):]
    body = body[:body.index('$("refresh").addEventListener')]
    assert "/api/state" in body and "fill(" in body
    assert "location.reload" not in pg


def test_refetching_state_shows_what_another_writer_changed(tmp_path, monkeypatch):
    # what the refresh button does on the server side: /api/state is rebuilt
    # from the config file every time, so a change made by the CLI (or another
    # pet) shows up without restarting the page
    _cfg(tmp_path, monkeypatch, creatures={"claudlet": {"scale": 4}})
    assert U.state_payload()["looks"]["claudlet"]["scale"] == 4
    _cfg(tmp_path, monkeypatch, creatures={"claudlet": {"scale": 9}})
    assert U.state_payload()["looks"]["claudlet"]["scale"] == 9


# ---------- export/import moved onto the creature row (no more Share tab) ----------

def test_export_and_import_buttons_flank_the_dropdown_trigger():
    # mockup layout: import (inward arrow) sits OUTSIDE the dropdown, to its
    # left; export (outward arrow) sits INSIDE the wide bar, at its right
    # end, after the trigger -- the reverse of the old arrangement
    pg = U.page({})
    row = pg[pg.index('<div class="row creature-row">'):pg.index('id="pickPanel"')]
    assert row.index('id="importBtn"') < row.index('<div class="picker">')
    bar = row[row.index('<div class="dropdown-bar">'):]
    assert bar.index('id="pickTrigger"') < bar.index('id="exportBtn"')
    assert "<svg" in row


def test_export_and_import_buttons_carry_localised_title_and_aria_label():
    ko, en = U.page({"lang": "ko"}), U.page({"lang": "en"})
    for pg, export_label, import_label in (
            (ko, U.TEXT["ko"]["export"], U.TEXT["ko"]["import"]),
            (en, U.TEXT["en"]["export"], U.TEXT["en"]["import"])):
        row = pg[pg.index('<div class="row creature-row">'):pg.index('id="pickPanel"')]
        assert ('title="%s"' % export_label) in row
        assert ('aria-label="%s"' % export_label) in row
        assert ('title="%s"' % import_label) in row
        assert ('aria-label="%s"' % import_label) in row


def test_export_click_posts_the_creature_being_viewed_with_optional_destination():
    pg = U.page({})
    fn = pg[pg.index("async function doExport("):pg.index('$("exportBtn")')]
    assert "creature: editing" in fn
    assert "exportOut" in fn        # tucked-away destination field, not required
    assert '$("exportBtn").addEventListener("click", () => doExport(false));' in pg


def test_import_lives_in_a_modal_with_the_same_two_step_flow():
    pg = U.page({})
    assert 'id="importModal" class="modal-backdrop" hidden' in pg
    # today's flow is unchanged: path field -> inspect -> confirm row -> install
    assert 'id="importPath"' in pg and 'id="importInspect"' in pg
    assert 'id="importConfirmRow"' in pg and 'id="importConfirm"' in pg
    assert 'id="importForce"' in pg


def test_import_modal_opens_on_the_import_button_and_closes_three_ways():
    pg = U.page({})
    assert '$("importBtn").addEventListener("click", openImportModal);' in pg
    fn = pg[pg.index("function closeImportModal()"):pg.index("function onImportModalKeydown")]
    assert '$("importModal").hidden = true;' in fn
    assert 'e.key === "Escape"' in pg and "closeImportModal()" in pg
    assert '$("importCancel").addEventListener("click", closeImportModal);' in pg
    backdrop = pg[pg.index('$("importModal").addEventListener("click"'):]
    backdrop = backdrop[:backdrop.index("let pendingImportPath")]
    assert "e.target === $(\"importModal\")" in backdrop


def test_import_confirm_closes_the_modal_and_refreshes_state_on_success():
    pg = U.page({})
    confirm_fn = pg[pg.index('$("importConfirm").addEventListener('):]
    assert "closeImportModal();" in confirm_fn
    assert "fill(await (await fetch(\"/api/state\")).json())" in confirm_fn


def test_the_import_token_and_no_innerHTML_trust_boundary_carries_over():
    # the per-run token and "entry names -> textContent, never innerHTML"
    # discipline must survive the move into the modal unchanged
    pg = U.page({}, import_token="tok-123")
    assert "tok-123" in pg
    assert "token: IMPORT_TOKEN" in pg
    share = pg[pg.index("renderImportInfo("):]
    share = share[:share.index('$("importInspect")')]
    assert "li.textContent = e" in share
    assert "innerHTML = e" not in share
    assert "innerHTML += " not in pg


def test_share_tab_and_sentinel_are_gone():
    pg = U.page({})
    assert "SHARE_TAB" not in pg
    assert 'id="share"' not in pg
    assert "T.share" not in pg
    assert "share" not in U.TEXT["ko"] and "share" not in U.TEXT["en"]




def test_a_silent_connection_does_not_wedge_the_server(monkeypatch):
    """Chrome opens speculative sockets and says nothing on them. This server
    handles one connection at a time, so without a read timeout such a socket
    blocked every later request forever -- the settings page that never
    appears."""
    import socket
    import threading
    from http.server import HTTPServer
    srv = HTTPServer(("127.0.0.1", 0), U._handler_class())
    srv.timeout = 5
    srv.last_seen = __import__("time").monotonic()
    srv.idle_timeout = 5.0
    srv.pages = {}
    stop = threading.Event()

    def pump():
        while not stop.is_set():
            srv.handle_request()

    t = threading.Thread(target=pump, daemon=True)
    t.start()
    silent = socket.create_connection(("127.0.0.1", srv.server_port))
    try:
        ctype, body = _get(srv.server_port, "/api/alive")
        assert json.loads(body)["app"] == U.APP_ID
    finally:
        silent.close()
        stop.set()
        srv.server_close()


def test_the_installed_pwa_is_skipped_when_we_are_not_on_its_origin(monkeypatch):
    """The PWA is keyed by origin: it always opens PREFERRED_PORT. On a
    fallback port it would show a dead page, so the ordinary browser gets the
    real url instead."""
    opened = []
    monkeypatch.setattr(U, "browser_command", lambda url: None)
    monkeypatch.setattr(U, "installed_pwa_command", lambda *a, **kw: ["installed-pwa"])
    import webbrowser
    monkeypatch.setattr(webbrowser, "open", lambda url: opened.append(url))
    U.launch_browser("http://127.0.0.1:41234/", app_window=False)
    assert opened == ["http://127.0.0.1:41234/"]
