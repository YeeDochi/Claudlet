from claudlet.platform import winterm


# --- normalize_title: strip the ANIMATED status glyph ---------------------
# The glyphs are the ones Windows Terminal really shows; the titles they are
# attached to are made up, since only the glyph matters to these tests.

def test_strips_the_status_glyph():
    assert winterm.normalize_title("✳ fix-retry-backoff") == "fix-retry-backoff"
    assert winterm.normalize_title("⠂ Claudlet 위치") == "Claudlet 위치"
    assert winterm.normalize_title("⠐ 캐시 만료 버그") == "캐시 만료 버그"


def test_the_glyph_may_change_between_capture_and_click():
    # the whole reason we normalize: the hook captured one frame of the spinner,
    # the tab is showing another by the time the user clicks.
    captured = winterm.normalize_title("✳ 설정 화면 정리")
    later = winterm.normalize_title("⠐ 설정 화면 정리")
    assert captured == later == "설정 화면 정리"


def test_leaves_a_plain_title_alone():
    assert winterm.normalize_title("release-checklist") == "release-checklist"


def test_keeps_a_leading_bracket():
    # a title can legitimately start with punctuation; brackets are common
    assert winterm.normalize_title("[WIP] refactor") == "[WIP] refactor"
    assert winterm.normalize_title("✳ [WIP] refactor") == "[WIP] refactor"


def test_empty_and_glyph_only_titles_yield_nothing_to_match_on():
    for junk in (None, "", "   ", "✳", "✳ ", "— · —"):
        assert winterm.normalize_title(junk) == ""


def test_trailing_whitespace_trimmed():
    assert winterm.normalize_title("  ✳  spaced out  ") == "spaced out"


# --- focus: orchestration with a fake runner ------------------------------

def _recorder():
    calls = []
    return calls, lambda want: calls.append(want)


def test_focus_dispatches_the_normalized_title():
    calls, run = _recorder()
    assert winterm.focus("✳ investigate-flaky-test", run) == \
        "investigate-flaky-test"
    assert calls == ["investigate-flaky-test"]


def test_focus_skips_the_lookup_when_there_is_nothing_to_match():
    # a bare glyph would normalize to "" -- dispatching that would be a wildcard
    # matching every tab, so it must not reach the runner at all.
    for junk in (None, "", "   ", "✳"):
        calls, run = _recorder()
        assert winterm.focus(junk, run) is None
        assert calls == []


def test_focus_survives_a_runner_error():
    def run(_want):
        raise RuntimeError("powershell missing")
    assert winterm.focus("✳ anything", run) is None


# --- the PowerShell payload ------------------------------------------------

def test_title_is_never_spliced_into_the_script():
    # titles are prose and routinely contain quotes/$/backticks; the script must
    # read them from the environment instead.
    assert "$env:" + winterm.TITLE_ENV in winterm.SELECT_PS
    assert winterm.WT_WINDOW_CLASS in winterm.SELECT_PS


def test_script_matches_by_containment_not_wildcard():
    # -like would treat *, ? and [ in a conversation title as wildcards
    assert ".Contains($want)" in winterm.SELECT_PS
    assert '-like "*' not in winterm.SELECT_PS      # the wildcard form, not the comment


def test_script_refuses_to_guess_between_duplicate_titles():
    assert "$hits.Count -ne 1" in winterm.SELECT_PS


def test_script_never_fails_the_caller():
    assert winterm.SELECT_PS.rstrip().endswith("exit 0")
