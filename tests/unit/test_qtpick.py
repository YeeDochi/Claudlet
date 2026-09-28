"""When the pet should hop onto the distro's PyQt6 (fcitx Hangul input)."""
from claudlet.core import qtpick as Q


def _ls(names):
    def listdir(path):
        assert path.endswith("platforminputcontexts")
        return names
    return listdir


def test_a_plugin_dir_is_judged_by_its_fcitx_input_context():
    assert Q.has_fcitx("/qt", _ls([Q.FCITX_PLUGIN, "libcompose.so"]))
    assert not Q.has_fcitx("/qt", _ls(["libibusplatforminputcontextplugin.so"]))


def test_a_missing_plugin_dir_is_just_no():
    def gone(_p):
        raise OSError
    assert not Q.has_fcitx("/nowhere", gone)


def test_switches_only_for_fcitx_on_linux_when_it_would_help():
    go = dict(platform="linux", xmodifiers="@im=fcitx", ours=False,
              theirs=True)
    assert Q.should_switch(**go)
    for k, v in [("platform", "darwin"), ("xmodifiers", "@im=ibus"),
                 ("xmodifiers", None), ("ours", True), ("theirs", False)]:
        assert not Q.should_switch(**dict(go, **{k: v})), k
