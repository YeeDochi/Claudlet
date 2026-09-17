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
    monkeypatch.setattr(I, "_link_skills", lambda home=None: [])
    monkeypatch.setattr(I, "install_desktop_entry", lambda home=None: (None, None))

    I.main([])          # no exception == install path stayed clear of uninstall


def test_link_skill_keeps_a_junction_pointing_at_the_skill(monkeypatch, tmp_path):
    # Windows junctions are reparse points: os.path.islink() says False, so the
    # junction fallback's own output looked like a foreign directory to every
    # later run, which re-warned "isn't a symlink" on each update.
    skills = tmp_path / "skills"; skills.mkdir()
    link = str(skills / "claudlet")
    os.mkdir(link)                                  # stands in for the junction
    monkeypatch.setattr(os.path, "samefile", lambda a, b: True)

    assert I._link_skill_at(link) == (link, None)
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
    monkeypatch.setattr(I, "SKILL_SRC", str(tmp_path / "nowhere"))

    path, note = I._link_skill_at(link)
    assert path is None and "left as-is" in note


def _detect_both(home):
    os.makedirs(home / ".claude", exist_ok=True)
    os.makedirs(home / ".codex", exist_ok=True)


def _linked_to_skill(path):
    """The link landed AND resolves to the packaged skill.

    Asserting os.path.islink() would only pass on POSIX: creating a symlink on
    Windows needs privilege, so _link_skill_at falls back to a directory
    junction, and a junction is a reparse point that islink() reports as False.
    What every caller actually depends on is where the path RESOLVES, not which
    of the two mechanisms produced it -- same reason _link_is_ours uses
    samefile."""
    return os.path.exists(path) and os.path.samefile(str(path), I.SKILL_SRC)


def test_link_skills_lands_in_every_detected_agent(tmp_path):
    _detect_both(tmp_path)

    results = I._link_skills(home=str(tmp_path))

    assert {label for label, _p, _n in results} == {"Claude Code", "Codex"}
    assert all(note is None for _l, _p, note in results)
    assert _linked_to_skill(tmp_path / ".claude" / "skills" / "claudlet")
    assert _linked_to_skill(tmp_path / ".codex" / "skills" / "claudlet")


def test_link_skills_only_touches_detected_agents(tmp_path):
    os.makedirs(tmp_path / ".claude", exist_ok=True)   # codex NOT detected

    I._link_skills(home=str(tmp_path))

    assert _linked_to_skill(tmp_path / ".claude" / "skills" / "claudlet")
    assert not (tmp_path / ".codex").exists()


def test_link_skills_foreign_dir_on_one_agent_does_not_block_the_other(tmp_path):
    _detect_both(tmp_path)
    codex_skills = tmp_path / ".codex" / "skills"
    os.makedirs(codex_skills, exist_ok=True)
    os.mkdir(codex_skills / "claudlet")   # foreign directory, not a link to us

    results = I._link_skills(home=str(tmp_path))

    by_label = {label: (p, n) for label, p, n in results}
    assert by_label["Codex"][0] is None and "left as-is" in by_label["Codex"][1]
    assert by_label["Claude Code"] == (
        str(tmp_path / ".claude" / "skills" / "claudlet"), None)
    assert _linked_to_skill(tmp_path / ".claude" / "skills" / "claudlet")


def test_link_skills_no_agents_detected_does_nothing(tmp_path):
    assert I._link_skills(home=str(tmp_path)) == []


def test_unlink_skills_removes_every_detected_agents_link(tmp_path):
    _detect_both(tmp_path)
    I._link_skills(home=str(tmp_path))

    I._unlink_skills(home=str(tmp_path))

    assert not os.path.exists(tmp_path / ".claude" / "skills" / "claudlet")
    assert not os.path.exists(tmp_path / ".codex" / "skills" / "claudlet")


def test_link_skills_permission_error_on_one_agent_does_not_block_the_other(
        tmp_path, monkeypatch):
    # A 0o500 ~/.codex (or any OSError from makedirs/unlink/symlink) used to
    # escape _link_skill_at uncaught, aborting _link_skills() before it ever
    # reached the other agents.
    _detect_both(tmp_path)
    real_makedirs = os.makedirs

    def flaky_makedirs(path, exist_ok=False):
        if ".codex" in path:
            raise PermissionError("no")
        return real_makedirs(path, exist_ok=exist_ok)
    monkeypatch.setattr(os, "makedirs", flaky_makedirs)

    results = I._link_skills(home=str(tmp_path))   # must not raise

    by_label = {label: (p, n) for label, p, n in results}
    assert by_label["Codex"][0] is None and by_label["Codex"][1]
    assert by_label["Claude Code"] == (
        str(tmp_path / ".claude" / "skills" / "claudlet"), None)
    assert _linked_to_skill(tmp_path / ".claude" / "skills" / "claudlet")


def test_unlink_skills_survives_permission_error_on_one_agent(tmp_path, monkeypatch):
    _detect_both(tmp_path)
    I._link_skills(home=str(tmp_path))
    real_unlink = os.unlink

    def flaky_unlink(path):
        if ".codex" in path:
            raise PermissionError("no")
        return real_unlink(path)
    monkeypatch.setattr(os, "unlink", flaky_unlink)

    I._unlink_skills(home=str(tmp_path))   # must not raise

    assert not os.path.exists(tmp_path / ".claude" / "skills" / "claudlet")


def _fake_icon(path):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as f:
        f.write(b"\x89PNGfake")
    return True


def test_desktop_entry_is_a_noop_off_linux(tmp_path, monkeypatch):
    monkeypatch.setattr(I.sys, "platform", "darwin")

    assert I.install_desktop_entry(home=str(tmp_path)) == (None, None)
    assert not (tmp_path / ".local").exists()


def test_desktop_entry_written_on_linux(tmp_path, monkeypatch):
    monkeypatch.setattr(I.sys, "platform", "linux")
    monkeypatch.setattr(I, "_write_desktop_icon", lambda p: False)   # no Qt here
    monkeypatch.setattr(I.shutil, "which", lambda n: None)
    monkeypatch.setattr(I.os.path, "exists",
                        lambda p, _real=I.os.path.exists: False if p.endswith(
                            "bin/claudlet-config") else _real(p))

    path, note = I.install_desktop_entry(home=str(tmp_path))

    assert note is None
    assert path == str(tmp_path / ".local" / "share" / "applications" / "claudlet.desktop")
    text = open(path, encoding="utf-8").read()
    assert "StartupWMClass=claudlet" in text
    assert "Name=claudlet" in text
    assert "Exec=" in text and " ui" in text
    # no Qt available -> falls back to a theme icon name instead of failing
    assert ("Icon=%s" % I.DESKTOP_ICON_FALLBACK) in text


def test_desktop_entry_uses_the_rendered_icon_when_qt_is_available(tmp_path, monkeypatch):
    monkeypatch.setattr(I.sys, "platform", "linux")
    monkeypatch.setattr(I, "_write_desktop_icon", _fake_icon)

    path, note = I.install_desktop_entry(home=str(tmp_path))

    icon_path = str(tmp_path / ".local" / "share" / "icons" / "hicolor" /
                    "256x256" / "apps" / "claudlet.png")
    assert note is None
    assert os.path.isfile(icon_path)
    assert ("Icon=%s" % I.DESKTOP_ICON_NAME) in open(path, encoding="utf-8").read()


def test_desktop_entry_does_not_clobber_a_foreign_file(tmp_path, monkeypatch):
    monkeypatch.setattr(I.sys, "platform", "linux")
    apps = tmp_path / ".local" / "share" / "applications"
    apps.mkdir(parents=True)
    (apps / "claudlet.desktop").write_text("[Desktop Entry]\nName=someone else\n")

    path, note = I.install_desktop_entry(home=str(tmp_path))

    assert path is None and "left as-is" in note
    assert "someone else" in (apps / "claudlet.desktop").read_text()


def test_desktop_entry_is_idempotent(tmp_path, monkeypatch):
    monkeypatch.setattr(I.sys, "platform", "linux")
    monkeypatch.setattr(I, "_write_desktop_icon", lambda p: False)

    first = I.install_desktop_entry(home=str(tmp_path))
    second = I.install_desktop_entry(home=str(tmp_path))

    assert first == second == (
        str(tmp_path / ".local" / "share" / "applications" / "claudlet.desktop"), None)


def test_uninstall_desktop_entry_removes_both_files(tmp_path, monkeypatch):
    monkeypatch.setattr(I.sys, "platform", "linux")
    monkeypatch.setattr(I, "_write_desktop_icon", _fake_icon)
    path, _note = I.install_desktop_entry(home=str(tmp_path))
    icon_path = str(tmp_path / ".local" / "share" / "icons" / "hicolor" /
                    "256x256" / "apps" / "claudlet.png")
    assert os.path.isfile(path) and os.path.isfile(icon_path)

    I.uninstall_desktop_entry(home=str(tmp_path))

    assert not os.path.exists(path)
    assert not os.path.exists(icon_path)


def test_uninstall_desktop_entry_is_a_noop_off_linux(tmp_path, monkeypatch):
    monkeypatch.setattr(I.sys, "platform", "darwin")
    apps = tmp_path / ".local" / "share" / "applications"
    apps.mkdir(parents=True)
    (apps / "claudlet.desktop").write_text("kept")

    I.uninstall_desktop_entry(home=str(tmp_path))   # must not raise or touch it

    assert (apps / "claudlet.desktop").read_text() == "kept"


def test_config_argv_prefers_the_installed_console_script(monkeypatch):
    monkeypatch.setattr(I.shutil, "which",
                        lambda n: "/usr/bin/claudlet-config" if n == "claudlet-config" else None)

    assert I._config_argv() == ["/usr/bin/claudlet-config", "ui"]


def test_config_argv_falls_back_to_the_module_when_nothing_else_resolves(monkeypatch):
    monkeypatch.setattr(I.shutil, "which", lambda n: None)
    monkeypatch.setattr(I.os.path, "exists", lambda p: False)

    assert I._config_argv() == [I.sys.executable, "-m", "claudlet.cli.configcli", "ui"]


def test_link_skills_is_idempotent(tmp_path):
    _detect_both(tmp_path)

    first = I._link_skills(home=str(tmp_path))
    second = I._link_skills(home=str(tmp_path))

    assert first == second
    assert _linked_to_skill(tmp_path / ".claude" / "skills" / "claudlet")
    assert _linked_to_skill(tmp_path / ".codex" / "skills" / "claudlet")
