from claudlet.pet import point_in_notch


def test_none_notch_never_hits():
    assert point_in_notch(700, 5, None) is False


def test_point_inside_notch():
    assert point_in_notch(700, 10, (656, 0, 200, 38)) is True


def test_point_outside_notch():
    assert point_in_notch(700, 100, (656, 0, 200, 38)) is False
    assert point_in_notch(100, 10, (656, 0, 200, 38)) is False
