import claudlet.roambounds as rb


def test_restrict_span_intersects_roam_area():
    # screen span 0..1000 (pet w=100), roam_area x=200 w=500 -> 200..600
    left, right = rb.restrict_span(0.0, 900.0, {"x": 200, "y": 0, "w": 500, "h": 800}, 100.0)
    assert (left, right) == (200.0, 600.0)


def test_restrict_span_no_area_unchanged():
    assert rb.restrict_span(0.0, 900.0, None, 100.0) == (0.0, 900.0)


def test_restrict_span_empty_intersection_falls_back():
    # roam_area entirely off the screen span -> keep original (pet never vanishes)
    left, right = rb.restrict_span(0.0, 900.0, {"x": 5000, "y": 0, "w": 100, "h": 100}, 100.0)
    assert (left, right) == (0.0, 900.0)


def test_restrict_floor_intersects():
    top, floor = rb.restrict_floor(0.0, 1000.0, {"x": 0, "y": 300, "w": 800, "h": 400}, 120.0)
    assert (top, floor) == (300.0, 580.0)


def test_push_out_x_pushes_to_nearest_edge():
    # zone x 400..1500 at y-band 900..1080; pet w=100 currently at x=1000, foot in band
    # nearest edge: right edge is 1500 (dist 500), left edge is 300 (dist 700) -> push right
    x = rb.push_out_x(1000.0, 100.0, 950.0, [{"x": 400, "y": 900, "w": 1100, "h": 180}])
    assert x == 1500.0


def test_push_out_x_pushes_left_when_closer():
    x = rb.push_out_x(450.0, 100.0, 950.0, [{"x": 400, "y": 900, "w": 1100, "h": 180}])
    assert x == 300.0     # left edge = zx - w = 400 - 100


def test_push_out_x_no_op_when_feet_above_zone():
    # feet at y=100 (above the zone's 900..1080 band) -> can perch over the zone
    x = rb.push_out_x(1000.0, 100.0, 100.0, [{"x": 400, "y": 900, "w": 1100, "h": 180}])
    assert x == 1000.0


def test_push_out_x_handles_multiple_zones():
    zones = [{"x": 400, "y": 900, "w": 300, "h": 180},
             {"x": 700, "y": 900, "w": 300, "h": 180}]
    x = rb.push_out_x(650.0, 100.0, 950.0, zones)
    # must land clear of BOTH zones
    assert not rb.blocks_target(x, 100.0, 950.0, zones)


def test_blocks_target_true_and_false():
    zones = [{"x": 400, "y": 900, "w": 1100, "h": 180}]
    assert rb.blocks_target(1000.0, 100.0, 950.0, zones) is True
    assert rb.blocks_target(1000.0, 100.0, 100.0, zones) is False   # above band
    assert rb.blocks_target(50.0, 100.0, 950.0, zones) is False     # left of zone
