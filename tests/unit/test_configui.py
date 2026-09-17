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
        assert set(look) == {"palette", "scale", "visor"}


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
    save_call = save_call[:save_call.index(");\n$(\"wear\")")]
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
    cmd = U.browser_command("http://127.0.0.1:8770/", which=which, size=(900, 700))
    assert cmd == ["/usr/bin/chromium", "--app=http://127.0.0.1:8770/",
                   "--window-size=900,700"]


def test_browser_command_prefers_the_earlier_browser_in_the_list():
    both = {"google-chrome": "/g", "brave-browser": "/b"}.get
    assert U.browser_command("http://x/", which=both)[0] == "/g"


def test_browser_command_is_none_without_a_chromium_family_browser():
    # macOS / Windows boxes usually have none of these on PATH -- the caller
    # then opens the default browser the old way
    assert U.browser_command("http://x/", which=lambda n: None) is None


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

def test_the_page_has_one_tab_per_agent_plus_share():
    pg = U.page({})
    assert 'id="tabs"' in pg
    assert "function tabRows" in pg and "SHARE_TAB" in pg
    # tabs come from the detected agents in the state payload, so a third
    # agent appears with no code change
    assert "(s.agents || []).map" in pg


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
