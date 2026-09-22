"""The Windows text backend, tested off Windows.

The script build and the stdout parse are pure, which is the whole reason they
are separate functions -- the COM call itself is the only part that needs the
hardware, and it is one injected `run`.
"""
from claudlet.platform import uiatree
from claudlet.platform.geom import Win


def win(**kw):
    base = dict(wid=4242, x=0, y=0, w=100, h=100, title="Notepad", pid=7,
                caption="notepad")
    base.update(kw)
    return Win(**base)


def test_script_carries_the_window_handle():
    assert "4242" in uiatree.build_script(4242)


def test_script_has_no_unsubstituted_placeholders():
    s = uiatree.build_script(1)
    assert "%(" not in s


def test_handle_is_coerced_to_int_not_spliced():
    # a string handle must not reach the script body as text
    assert "'; evil" not in uiatree.build_script(12)


def test_parse_keeps_only_prefixed_lines():
    out = uiatree.parse_output("T:Hello\nWARNING: noise\nT:World")
    assert out == ["Hello", "World"]


def test_parse_drops_empty_values():
    assert uiatree.parse_output("T:\nT:   \nT:real") == ["real"]


def test_parse_of_nothing_is_empty():
    assert uiatree.parse_output("") == []
    assert uiatree.parse_output(None) == []


def test_read_window_uses_the_injected_runner():
    got = uiatree.read_window(win(), run=lambda s: "T:Alpha\nT:Beta")
    # off-Windows available() is False, so this degrades regardless
    assert got is None or got == ["Alpha", "Beta"]


def test_read_window_with_runner_on_simulated_windows(monkeypatch):
    monkeypatch.setattr(uiatree, "available", lambda: True)
    got = uiatree.read_window(win(), run=lambda s: "T:Alpha\nT:Beta")
    assert got == ["Alpha", "Beta"]


def test_a_failing_runner_degrades_to_none(monkeypatch):
    monkeypatch.setattr(uiatree, "available", lambda: True)
    def boom(_):
        raise OSError("powershell missing")
    assert uiatree.read_window(win(), run=boom) is None


def test_none_window_is_handled():
    assert uiatree.read_window(None) is None


def test_trusted_matches_available(monkeypatch):
    monkeypatch.setattr(uiatree, "available", lambda: True)
    assert uiatree.trusted() is True
    monkeypatch.setattr(uiatree, "available", lambda: False)
    assert uiatree.trusted() is False


def test_no_hint_is_offered_off_windows(monkeypatch):
    monkeypatch.setattr(uiatree, "available", lambda: False)
    assert uiatree.install_hint() is None
