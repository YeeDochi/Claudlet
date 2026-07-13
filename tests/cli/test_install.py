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
