"""Opening a terminal window. The dispatch is pure; the window is not."""
from claudlet.platform import termlaunch as T


def test_the_applescript_runs_the_command():
    assert "echo hi" in T.mac_script("echo hi")


def test_a_quote_in_the_command_is_escaped():
    script = T.mac_script('say "hello"')
    assert '\\"hello\\"' in script


def test_a_backslash_is_escaped():
    assert "\\\\" in T.mac_script("a\\b")


def test_iterm_gets_its_own_script():
    assert "iTerm" in T.mac_script("x", "iTerm")


def test_an_unknown_app_falls_back_to_terminal():
    assert "Terminal" in T.mac_script("x", "NoSuchTerm")


def test_iterm_is_preferred_when_present():
    assert T.pick_mac_terminal(exists=lambda p: "iTerm" in p) == "iTerm"


def test_apple_terminal_is_the_fallback():
    assert T.pick_mac_terminal(exists=lambda p: "Utilities" in p) == "Terminal"


def test_no_known_terminal_reports_none():
    assert T.pick_mac_terminal(exists=lambda p: False) is None


def test_launch_uses_the_injected_runner():
    seen = []
    assert T.launch("echo hi", run=lambda argv: seen.append(argv) or True)
    assert seen and isinstance(seen[0], list)


def test_a_failing_runner_is_reported_not_raised():
    assert T.launch("echo hi", run=lambda argv: False) is False


def test_a_raising_runner_is_swallowed():
    def boom(_argv):
        raise OSError("no such app")
    assert T.launch("echo hi", run=boom) is False


def test_available_answers_without_raising():
    assert T.available() in (True, False)
