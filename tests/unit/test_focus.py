from claudlet.platform import focus


# ---- pure decision (focus_matches): tested with data, no probe patching. The
# active-window class is an INPUT here, not a monkeypatched module internal, so
# renaming/reordering the probe chain can't break these. ----

def test_matches_when_active_matches():
    assert focus.focus_matches(["konsole"], "org.kde.konsole") is True

def test_no_match_when_other_window():
    assert focus.focus_matches(["konsole"], "firefox") is False

def test_matches_when_active_unknown():
    # undetectable active window -> conservative True (suppress celebrate)
    assert focus.focus_matches(["konsole"], None) is True

def test_matches_when_no_classes():
    # unknown host: empty class list -> conservative True, regardless of active
    assert focus.focus_matches([], "firefox") is True

def test_vscode_class_matches():
    assert focus.focus_matches(["code"], "code") is True

def test_macos_frontmost_app_matches():
    # macOS: frontmost app name (e.g. "terminal") matched against host classes
    assert focus.focus_matches(["terminal"], "terminal") is True
    assert focus.focus_matches(["terminal"], "safari") is False


# ---- thin adapter (terminal_focused): one test that it probes the live class
# and defers to focus_matches. This is the only place that touches the probe. ----

def test_terminal_focused_probes_then_delegates(monkeypatch):
    monkeypatch.setattr(focus, "_active_window_class", lambda: "org.kde.konsole")
    assert focus.terminal_focused(["konsole"]) is True
    monkeypatch.setattr(focus, "_active_window_class", lambda: "firefox")
    assert focus.terminal_focused(["konsole"]) is False


def test_applescript_probe_noop_off_darwin(monkeypatch):
    # off macOS the AppleScript probe must not run / must return None
    monkeypatch.setattr(focus.sys, "platform", "linux")
    assert focus._active_via_applescript() is None
