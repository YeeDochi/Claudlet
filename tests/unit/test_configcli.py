import json
import os
import zipfile

from claudlet.cli import configcli as C
from claudlet.core import agents, avatars, petconfig


def test_diagnose_separates_accepted_and_ignored():
    raw = {
        "tools": {"Bash": "work_computer", "Grep": "bogus_state"},
        "events": {"prompt": "thinking", "notaslot": "jump"},
        "raw_events": {"PostToolUse": "celebrate"},
        "lang": "fr",
    }

    d = C.diagnose(raw)

    assert d["accepted"]["tool_states"] == {"Bash": "work_computer"}
    assert d["accepted"]["event_states"] == {"prompt": "thinking"}
    assert d["accepted"]["raw_events"] == {"PostToolUse": "celebrate"}
    assert d["accepted"]["lang"] == "auto"        # "fr" invalid -> auto

    joined = " ".join(d["ignored"])
    assert "Grep" in joined and "bogus_state" in joined     # bad state value
    assert "notaslot" in joined                             # unknown event slot
    assert "lang" in joined and "fr" in joined              # invalid lang
    # accepted entries must never be reported as ignored
    assert "Bash" not in joined and "PostToolUse" not in joined


def test_diagnose_clean_config_has_no_ignored():
    raw = {"tools": {"Bash": "work_computer"}, "lang": "ko"}
    d = C.diagnose(raw)
    assert d["ignored"] == []
    assert d["accepted"]["lang"] == "ko"


def test_build_report_found(tmp_path):
    p = tmp_path / "config.json"
    p.write_text(json.dumps({"tools": {"Bash": "jump", "X": "nope"}, "lang": "ko"}))

    r = C.build_report(str(p))

    assert r["status"] == "found"
    assert os.path.isabs(r["path"])
    assert r["accepted"]["tool_states"] == {"Bash": "jump"}
    assert r["accepted"]["lang"] == "ko"
    assert any("X" in s for s in r["ignored"])


def test_build_report_missing(tmp_path):
    r = C.build_report(str(tmp_path / "nope.json"))

    assert r["status"] == "missing"
    assert r["accepted"]["lang"] == "auto"
    assert r["ignored"] == []


def test_build_report_invalid_json(tmp_path):
    p = tmp_path / "config.json"
    p.write_text("{ not json ")

    r = C.build_report(str(p))

    assert r["status"] == "invalid"
    assert r["error"]
    assert r["accepted"]["tool_states"] == {}


def test_init_creates_valid_template(tmp_path):
    p = tmp_path / "sub" / "config.json"      # parent dir does not exist yet

    created = C.init_config(str(p))

    assert created is True
    assert p.exists()
    r = C.build_report(str(p))                # template is clean/valid
    assert r["status"] == "found"
    assert r["ignored"] == []


def test_init_does_not_clobber_existing(tmp_path):
    p = tmp_path / "config.json"
    p.write_text('{"lang": "ko"}')

    created = C.init_config(str(p))

    assert created is False
    assert json.loads(p.read_text()) == {"lang": "ko"}      # left untouched


def test_open_command_per_platform():
    assert C.open_command("/x/c.json", platform="linux", name="posix") == \
        ["xdg-open", "/x/c.json"]
    assert C.open_command("/x/c.json", platform="darwin", name="posix") == \
        ["open", "/x/c.json"]
    assert C.open_command("C:\\x\\c.json", platform="win32", name="nt") == \
        "startfile"


def test_open_config_scaffolds_then_launches(tmp_path, monkeypatch):
    p = tmp_path / "config.json"                # missing
    launched = []
    monkeypatch.setattr(C, "_launch", lambda path: launched.append(path))

    ret = C.open_config(str(p))

    assert p.exists()                           # scaffolded before opening
    assert launched == [os.path.abspath(str(p))]
    assert ret == os.path.abspath(str(p))


def test_main_show_prints_path_status_and_reference(tmp_path, monkeypatch, capsys):
    cfg = tmp_path / "config.json"
    cfg.write_text(json.dumps({"tools": {"Bash": "jump"}}))
    monkeypatch.setattr(C.petconfig, "config_path", lambda: str(cfg))

    rc = C.main([])

    out = capsys.readouterr().out
    assert rc == 0
    assert os.path.abspath(str(cfg)) in out
    assert "found" in out
    assert "work_computer" in out               # valid-state reference


def test_main_path_prints_only_the_path(tmp_path, monkeypatch, capsys):
    cfg = tmp_path / "config.json"
    monkeypatch.setattr(C.petconfig, "config_path", lambda: str(cfg))

    rc = C.main(["--path"])

    assert rc == 0
    assert capsys.readouterr().out.strip() == os.path.abspath(str(cfg))


def test_main_init_creates_file(tmp_path, monkeypatch):
    cfg = tmp_path / "config.json"
    monkeypatch.setattr(C.petconfig, "config_path", lambda: str(cfg))

    rc = C.main(["init"])

    assert rc == 0
    assert cfg.exists()


def test_main_open_invokes_launcher(tmp_path, monkeypatch):
    cfg = tmp_path / "config.json"
    monkeypatch.setattr(C.petconfig, "config_path", lambda: str(cfg))
    launched = []
    monkeypatch.setattr(C, "_launch", lambda p: launched.append(p))

    rc = C.main(["open"])

    assert rc == 0
    assert launched == [os.path.abspath(str(cfg))]


def test_main_ui_threads_the_agent_flag_through_to_configui(monkeypatch):
    # A pet right-clicked on a Codex pet must open the settings page already
    # showing Codex, not always the default agent -- see pet.py's
    # _open_settings, which passes `--agent <self.agent>` into this command.
    calls = []
    from claudlet.cli import configui
    monkeypatch.setattr(configui, "serve",
                        lambda **kw: calls.append(kw) or "http://x")

    rc = C.main(["ui", "--agent", "codex", "--no-open"])

    assert rc == 0
    assert calls == [{"open_browser": False, "agent": "codex"}]


def test_main_ui_agent_flag_is_optional(monkeypatch):
    calls = []
    from claudlet.cli import configui
    monkeypatch.setattr(configui, "serve",
                        lambda **kw: calls.append(kw) or "http://x")

    C.main(["ui"])

    assert calls == [{"open_browser": True, "agent": None}]


# ---------- wear ----------

def test_wear_no_creature_lists_available_and_wearers(monkeypatch, capsys):
    monkeypatch.setattr(agents, "detected", lambda home=None: ["claude"])
    petconfig.save_keys({"avatar": "claudlet"})

    rc = C.main(["wear"])

    out = capsys.readouterr().out
    assert rc == 0
    assert "claudlet" in out and "slime" in out
    assert "worn by: claude" in out


def test_wear_unknown_creature_errors_without_writing(monkeypatch, capsys):
    monkeypatch.setattr(agents, "detected", lambda home=None: ["claude"])
    before = petconfig.load_config()

    rc = C.main(["wear", "nonexistent-creature"])

    out = capsys.readouterr().out
    assert rc == 1
    assert "unknown creature" in out
    assert petconfig.load_config() == before          # nothing written


def test_wear_writes_the_config_and_broadcasts(monkeypatch, capsys):
    from claudlet.cli import configui
    monkeypatch.setattr(agents, "detected", lambda home=None: ["claude"])
    sent = []
    monkeypatch.setattr(configui.hostinfo, "broadcast",
                        lambda line: sent.append(line) or 2)

    rc = C.main(["wear", "slime"])

    out = capsys.readouterr().out
    assert rc == 0
    assert petconfig.avatar_for(petconfig.load_config(), "claude") == "slime"
    assert json.loads(sent[0]) == {"cmd": "restyle"}
    assert "2 pet(s) updated" in out


def test_wear_single_detected_agent_is_used_without_the_flag(monkeypatch):
    from claudlet.cli import configui
    monkeypatch.setattr(agents, "detected", lambda home=None: ["codex"])
    monkeypatch.setattr(configui.hostinfo, "broadcast", lambda line: 0)

    C.main(["wear", "slime"])

    cfg = petconfig.load_config()
    assert petconfig.avatar_for(cfg, "codex") == "slime"
    assert petconfig.avatar_for(cfg, "claude") is None


def test_wear_explicit_agent_flag_overrides_detection(monkeypatch):
    from claudlet.cli import configui
    monkeypatch.setattr(agents, "detected", lambda home=None: ["claude", "codex"])
    monkeypatch.setattr(configui.hostinfo, "broadcast", lambda line: 0)

    C.main(["wear", "slime", "--agent", "codex"])

    cfg = petconfig.load_config()
    assert petconfig.avatar_for(cfg, "codex") == "slime"


def test_wear_promotes_a_legacy_string_avatar_via_configui_apply(monkeypatch):
    # C's spec: reuse configui.apply()'s promotion so a legacy string avatar
    # keeps meaning what it meant for every OTHER agent.
    from claudlet.cli import configui
    monkeypatch.setattr(agents, "detected", lambda home=None: ["claude", "codex"])
    monkeypatch.setattr(configui.hostinfo, "broadcast", lambda line: 0)
    petconfig.save_keys({"avatar": "claudlet"})

    C.main(["wear", "slime", "--agent", "codex"])

    cfg = petconfig.load_config()
    assert petconfig.avatar_for(cfg, "codex") == "slime"
    assert petconfig.avatar_for(cfg, "claude") == "claudlet"   # kept


# ---------- export ----------

def test_export_bundled_creature_round_trips_as_a_package(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    rc = C.main(["export", "slime"])

    assert rc == 0
    zpath = tmp_path / "slime.claudlet-creature.zip"
    assert zpath.exists()
    with zipfile.ZipFile(zpath) as zf:
        assert zf.namelist() == ["slime/__init__.py"]


def test_export_user_creature_zips_its_directory(tmp_path, monkeypatch):
    creatures_dir = tmp_path / "creatures"
    d = creatures_dir / "mycreature"
    d.mkdir(parents=True)
    (d / "__init__.py").write_text("AVATAR = None\n")
    (d / "art.py").write_text("X = 1\n")
    monkeypatch.setattr(avatars, "CREATURES_DIR", str(creatures_dir))
    monkeypatch.setattr(avatars, "available", lambda: ["claudlet", "mycreature"])
    out_dir = tmp_path / "out"
    out_dir.mkdir()

    rc = C.main(["export", "mycreature", "--out", str(out_dir)])

    assert rc == 0
    zpath = out_dir / "mycreature.claudlet-creature.zip"
    assert zpath.exists()
    with zipfile.ZipFile(zpath) as zf:
        names = set(zf.namelist())
    assert names == {"mycreature/__init__.py", "mycreature/art.py"}


def test_export_unknown_creature_errors(capsys):
    rc = C.main(["export", "nope"])
    assert rc == 1
    assert "unknown creature" in capsys.readouterr().out


# ---------- import ----------

def _make_zip(tmp_path, top, files):
    p = tmp_path / "creature.zip"
    with zipfile.ZipFile(p, "w") as zf:
        for rel, content in files.items():
            zf.writestr("%s/%s" % (top, rel), content)
    return p


def test_import_installs_into_creatures_dir(tmp_path, monkeypatch):
    creatures_dir = tmp_path / "creatures"
    monkeypatch.setattr(avatars, "CREATURES_DIR", str(creatures_dir))
    zpath = _make_zip(tmp_path, "cool", {"__init__.py": "AVATAR = None\n"})

    rc = C.main(["import", str(zpath), "--yes"])

    assert rc == 0
    assert (creatures_dir / "cool" / "__init__.py").read_text() == "AVATAR = None\n"


def test_import_refuses_zip_slip(tmp_path, monkeypatch):
    creatures_dir = tmp_path / "creatures"
    monkeypatch.setattr(avatars, "CREATURES_DIR", str(creatures_dir))
    p = tmp_path / "evil.zip"
    with zipfile.ZipFile(p, "w") as zf:
        zf.writestr("cool/__init__.py", "AVATAR = None\n")
        zf.writestr("cool/../../evil.py", "pwned = True\n")

    name, entries, total, err = C.inspect_creature_zip(str(p))

    assert err is not None and "unsafe" in err
    assert not (tmp_path.parent / "evil.py").exists()

    rc = C.main(["import", str(p), "--yes"])
    assert rc == 1
    assert not os.path.isdir(str(creatures_dir))


def test_import_refuses_absolute_path_entry(tmp_path, monkeypatch):
    creatures_dir = tmp_path / "creatures"
    monkeypatch.setattr(avatars, "CREATURES_DIR", str(creatures_dir))
    p = tmp_path / "evil.zip"
    with zipfile.ZipFile(p, "w") as zf:
        zf.writestr("cool/__init__.py", "AVATAR = None\n")
        zf.writestr("/etc/evil.py", "pwned = True\n")

    name, entries, total, err = C.inspect_creature_zip(str(p))
    assert err is not None


def test_import_refuses_symlink_entry(tmp_path, monkeypatch):
    creatures_dir = tmp_path / "creatures"
    monkeypatch.setattr(avatars, "CREATURES_DIR", str(creatures_dir))
    p = tmp_path / "evil.zip"
    with zipfile.ZipFile(p, "w") as zf:
        info = zipfile.ZipInfo("cool/link")
        info.external_attr = (0o120777 << 16)   # S_IFLNK
        zf.writestr(info, "/etc/passwd")

    name, entries, total, err = C.inspect_creature_zip(str(p))
    assert err is not None and "symlink" in err


def test_import_refuses_multiple_top_level_dirs(tmp_path, monkeypatch):
    p = tmp_path / "evil.zip"
    with zipfile.ZipFile(p, "w") as zf:
        zf.writestr("one/__init__.py", "x = 1\n")
        zf.writestr("two/__init__.py", "x = 1\n")

    name, entries, total, err = C.inspect_creature_zip(str(p))
    assert err is not None and "top-level" in err


def test_import_shows_contents_and_requires_confirmation(tmp_path, monkeypatch,
                                                          capsys):
    creatures_dir = tmp_path / "creatures"
    monkeypatch.setattr(avatars, "CREATURES_DIR", str(creatures_dir))
    zpath = _make_zip(tmp_path, "cool", {"__init__.py": "AVATAR = None\n"})
    monkeypatch.setattr("builtins.input", lambda prompt="": "n")

    rc = C.main(["import", str(zpath)])

    out = capsys.readouterr().out
    assert rc == 1
    assert "cool/__init__.py" in out
    assert not (creatures_dir / "cool").exists()


def test_import_yes_flag_skips_the_prompt(tmp_path, monkeypatch):
    creatures_dir = tmp_path / "creatures"
    monkeypatch.setattr(avatars, "CREATURES_DIR", str(creatures_dir))
    zpath = _make_zip(tmp_path, "cool", {"__init__.py": "AVATAR = None\n"})

    def boom(prompt=""):
        raise AssertionError("should not prompt with --yes")
    monkeypatch.setattr("builtins.input", boom)

    rc = C.main(["import", str(zpath), "--yes"])
    assert rc == 0


def test_import_refuses_to_overwrite_without_force(tmp_path, monkeypatch):
    creatures_dir = tmp_path / "creatures"
    (creatures_dir / "cool").mkdir(parents=True)
    (creatures_dir / "cool" / "__init__.py").write_text("old = 1\n")
    monkeypatch.setattr(avatars, "CREATURES_DIR", str(creatures_dir))
    zpath = _make_zip(tmp_path, "cool", {"__init__.py": "new = 1\n"})

    rc = C.main(["import", str(zpath), "--yes"])
    assert rc == 1
    assert (creatures_dir / "cool" / "__init__.py").read_text() == "old = 1\n"


def test_import_force_overwrites(tmp_path, monkeypatch):
    creatures_dir = tmp_path / "creatures"
    (creatures_dir / "cool").mkdir(parents=True)
    (creatures_dir / "cool" / "__init__.py").write_text("old = 1\n")
    monkeypatch.setattr(avatars, "CREATURES_DIR", str(creatures_dir))
    zpath = _make_zip(tmp_path, "cool", {"__init__.py": "new = 1\n"})

    rc = C.main(["import", str(zpath), "--yes", "--force"])
    assert rc == 0
    assert (creatures_dir / "cool" / "__init__.py").read_text() == "new = 1\n"


def test_import_never_fetches_a_url(tmp_path):
    # takes a local file only -- downloading is the caller's job
    import inspect
    src = inspect.getsource(C.cmd_import) + inspect.getsource(C.import_creature)
    for bad in ("urlopen", "requests.", "http.client"):
        assert bad not in src
