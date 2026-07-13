import json
import os
from claudlet.cli import uninstall as U


def test_stop_running_pets_broadcasts_quit(monkeypatch):
    # broadcasts a single {"cmd":"quit"} JSON line to every pet via the shared
    # motion.send transport, and returns however many pets accepted it.
    sent = []
    monkeypatch.setattr(U.motion, "send", lambda msg: (sent.append(msg), 3)[1])

    n = U.stop_running_pets()

    assert n == 3
    assert len(sent) == 1
    assert sent[0].endswith("\n")
    assert json.loads(sent[0]) == {"cmd": "quit"}


def test_clean_port_files_removes_leftovers(tmp_path, monkeypatch):
    # dead pets that never cleaned up leave claudlet-*.port behind; uninstall
    # sweeps whatever remains after the quit broadcast.
    p1 = tmp_path / "claudlet-a.port"; p1.write_text("111")
    p2 = tmp_path / "claudlet-b.port"; p2.write_text("222")
    monkeypatch.setattr(U.motion, "port_files", lambda: [str(p1), str(p2)])

    n = U.clean_port_files()

    assert n == 2
    assert not p1.exists() and not p2.exists()


def test_clean_port_files_counts_only_removed(tmp_path, monkeypatch):
    # a file a live pet already removed itself (post-quit) is not double-counted
    gone = tmp_path / "claudlet-gone.port"      # never created
    monkeypatch.setattr(U.motion, "port_files", lambda: [str(gone)])

    assert U.clean_port_files() == 0


def test_purge_config_removes_dir(tmp_path, monkeypatch):
    cfgdir = tmp_path / "claudlet"
    cfgdir.mkdir()
    (cfgdir / "config.json").write_text("{}")
    monkeypatch.setattr(U.petconfig, "config_path",
                        lambda: str(cfgdir / "config.json"))

    assert U.purge_config() is True
    assert not cfgdir.exists()


def test_purge_config_missing_is_noop(tmp_path, monkeypatch):
    cfgdir = tmp_path / "claudlet"          # never created
    monkeypatch.setattr(U.petconfig, "config_path",
                        lambda: str(cfgdir / "config.json"))

    assert U.purge_config() is False


def _stub_teardown(monkeypatch, calls):
    """Neutralize every real side effect so main() is safe to run in tests."""
    monkeypatch.setattr(U, "stop_running_pets", lambda: calls.append("stop") or 2)
    monkeypatch.setattr(U.install_hooks, "main",
                        lambda argv=None: calls.append(("hooks", argv)))
    monkeypatch.setattr(U.install, "_unlink_skill",
                        lambda: calls.append("unlink"))
    monkeypatch.setattr(U, "clean_port_files", lambda: calls.append("clean") or 0)
    monkeypatch.setattr(U, "purge_config", lambda: calls.append("purge") or True)


def test_main_default_tears_down_without_purge(monkeypatch, capsys):
    calls = []
    _stub_teardown(monkeypatch, calls)

    rc = U.main([])

    assert rc == 0
    assert "stop" in calls
    assert ("hooks", ["--remove"]) in calls     # hooks removed, not installed
    assert "unlink" in calls
    assert "clean" in calls
    assert "purge" not in calls                 # default must NOT touch config
    # guides the user to remove the package themselves (we never self-uninstall)
    assert "pipx uninstall claudlet" in capsys.readouterr().out


def test_main_purge_removes_config(monkeypatch):
    calls = []
    _stub_teardown(monkeypatch, calls)

    U.main(["--purge"])

    assert "purge" in calls


def test_main_argv_none_reads_sys_argv(monkeypatch):
    calls = []
    _stub_teardown(monkeypatch, calls)
    monkeypatch.setattr(U.sys, "argv", ["claudlet-uninstall", "--purge"])

    U.main()

    assert "purge" in calls
