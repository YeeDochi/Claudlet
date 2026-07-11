from claudlet import versioncli as V


def test_compare_states():
    assert V.compare("0.1.1", "0.1.1") == "up-to-date"
    assert V.compare("0.1.0", "0.1.1") == "update-available"
    assert V.compare("0.2.0", "0.1.1") == "ahead"      # unreleased/dev build
    assert V.compare("0.1.0", None) == "unknown"       # couldn't reach PyPI


def test_compare_handles_multidigit_and_uneven_lengths():
    assert V.compare("0.9.0", "0.10.0") == "update-available"   # 9 < 10, not string cmp
    assert V.compare("1.0", "1.0.0") == "up-to-date"            # padded equal
    assert V.compare("1.2", "1.2.1") == "update-available"


def test_render_shows_versions_and_status():
    out = V.render("0.1.0", "0.1.1")
    assert "0.1.0" in out and "0.1.1" in out
    assert "update" in out.lower()


def test_render_unknown_when_offline():
    out = V.render("0.1.0", None)
    assert "0.1.0" in out
    assert "unknown" in out.lower() or "offline" in out.lower()


def test_main_prints_installed_and_fetched_latest(monkeypatch, capsys):
    monkeypatch.setattr(V, "latest_pypi_version", lambda timeout=2.0: "9.9.9")

    rc = V.main([])

    out = capsys.readouterr().out
    assert rc == 0
    assert V.__version__ in out            # the installed version
    assert "9.9.9" in out and "update available" in out
