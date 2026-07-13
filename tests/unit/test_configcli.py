import json
import os
from claudlet.cli import configcli as C


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
    assert C._open_command("/x/c.json", platform="linux", name="posix") == \
        ["xdg-open", "/x/c.json"]
    assert C._open_command("/x/c.json", platform="darwin", name="posix") == \
        ["open", "/x/c.json"]
    assert C._open_command("C:\\x\\c.json", platform="win32", name="nt") == \
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
