from claudlet.cli import window


def test_raised_means_shown_and_topmost():
    assert window.raised([{"id": "a", "state": "shown"}, {"id": "b", "state": "min"}], "a")
    assert not window.raised([{"id": "a", "state": "min"}], "a")
    assert not window.raised([{"id": "b", "state": "shown"}, {"id": "a", "state": "shown"}], "a")
    assert not window.raised(None, "a")


class _Clock:
    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t

    def sleep(self, d):
        self.t += d


def _run(monkeypatch, feed):
    """`feed(t)` is the window list the pet reports at time t."""
    clock = _Clock()
    def reply():
        got = feed(clock.t)
        return got if isinstance(got, dict) else {"windows": got}
    monkeypatch.setattr(window, "_windows", reply)
    return window._wait_raised("a", clock=clock, sleep=clock.sleep)


def test_wait_succeeds_once_the_window_comes_up(monkeypatch):
    up = [{"id": "a", "state": "shown"}]
    assert _run(monkeypatch, lambda t: up if t > 3 else [{"id": "a", "state": "min"}]) == 0


def test_wait_reports_the_state_it_got_stuck_in(monkeypatch, capsys):
    assert _run(monkeypatch, lambda t: [{"id": "a", "state": "min"}]) == 3
    assert "(min)" in capsys.readouterr().err
    assert _run(monkeypatch, lambda t: [{"id": "b", "state": "shown"},
                                        {"id": "a", "state": "shown"}]) == 3
    assert "not in front" in capsys.readouterr().err


def test_wait_holds_until_the_pet_has_brought_it_over(monkeypatch):
    up = [{"id": "a", "state": "shown"}]
    # an open window is in front from the first tug; done only once it rides
    feed = lambda t: {"windows": up, "fetching": "a",
                      "fetch_phase": "pull" if t < 5 else "ride"}
    clock_end = []
    assert _run(monkeypatch, lambda t: clock_end.append(t) or feed(t)) == 0
    assert clock_end[-1] >= 5
    assert not window.delivered({"windows": up, "fetching": "a", "fetch_phase": "leap"}, "a")
    assert window.delivered({"windows": up, "fetching": "b", "fetch_phase": "leap"}, "a")
    assert window.delivered({"windows": up}, "a")                 # older pet: no fetch info
