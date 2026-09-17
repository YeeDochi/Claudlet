import json
import os

from claudlet.cli import install as I


def test_remove_delegates_to_uninstall(monkeypatch):
    # single teardown implementation: `claudlet-install --remove` must route to
    # uninstall.main (passing its argv through, so --purge is honored) rather
    # than keeping a second, divergent removal path.
    seen = []
    monkeypatch.setattr("claudlet.cli.uninstall.main",
                        lambda argv=None: seen.append(argv) or 0)

    rc = I.main(["--remove", "--purge"])

    assert rc == 0
    assert seen == [["--remove", "--purge"]]


def test_install_path_does_not_call_uninstall(monkeypatch):
    # the plain install path must never trigger teardown
    monkeypatch.setattr("claudlet.cli.uninstall.main",
                        lambda argv=None: (_ for _ in ()).throw(
                            AssertionError("uninstall must not run on install")))
    monkeypatch.setattr(I, "_check_deps", lambda: "stubbed")
    monkeypatch.setattr("claudlet.cli.install_hooks.main", lambda argv=None: None)
    monkeypatch.setattr(I, "_link_skill", lambda: (None, None))

    I.main([])          # no exception == install path stayed clear of uninstall


def test_link_skill_keeps_a_junction_pointing_at_the_skill(monkeypatch, tmp_path):
    # Windows junctions are reparse points: os.path.islink() says False, so the
    # junction fallback's own output looked like a foreign directory to every
    # later run, which re-warned "isn't a symlink" on each update.
    skills = tmp_path / "skills"; skills.mkdir()
    link = str(skills / "claudlet")
    os.mkdir(link)                                  # stands in for the junction
    monkeypatch.setattr(I, "SKILLS_DIR", str(skills))
    monkeypatch.setattr(I, "SKILL_LINK", link)
    monkeypatch.setattr(os.path, "samefile", lambda a, b: True)

    assert I._link_skill() == (link, None)
    assert os.path.isdir(link)                      # left in place, not clobbered


def test_already_installed_survives_a_corrupt_file_for_one_agent(monkeypatch, tmp_path):
    # install_hooks.load() raises SystemExit (a BaseException, not caught by a
    # plain `except Exception`) on a corrupt/unreadable settings file. One bad
    # ~/.codex/hooks.json must not abort detection for claude too, or
    # claudlet-install would die before the Claude Code hooks got installed.
    from claudlet.cli import install_hooks

    home = tmp_path
    os.makedirs(home / ".claude", exist_ok=True)
    (home / ".claude" / "settings.json").write_text(json.dumps({"hooks": {
        "Stop": [{"hooks": [{"type": "command", "command": "claudlet-hook Stop"}]}]
    }}))
    os.makedirs(home / ".codex", exist_ok=True)
    (home / ".codex" / "hooks.json").write_text("{ not json")

    monkeypatch.setattr("claudlet.core.agents.detected",
                        lambda home=None: ["claude", "codex"])
    monkeypatch.setattr("claudlet.core.agents.settings_path",
                        lambda name, home=None: str(tmp_path / ("." + name) /
                            ("settings.json" if name == "claude" else "hooks.json")))

    assert I._already_installed(install_hooks) is True   # claude's hook still found


def test_link_skill_warns_on_a_foreign_directory(monkeypatch, tmp_path):
    # a plain directory (an old manual copy) that does NOT resolve to the
    # packaged skill must still be left alone, with the warning
    skills = tmp_path / "skills"; skills.mkdir()
    link = str(skills / "claudlet")
    os.mkdir(link)
    monkeypatch.setattr(I, "SKILLS_DIR", str(skills))
    monkeypatch.setattr(I, "SKILL_LINK", link)
    monkeypatch.setattr(I, "SKILL_SRC", str(tmp_path / "nowhere"))

    path, note = I._link_skill()
    assert path is None and "left as-is" in note
