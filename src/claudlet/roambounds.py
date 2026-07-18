"""Pure geometry for confining the pet to a roam area and out of no-go zones.

No Qt, no pet state — just numbers, so it tests as data (CLAUDE.md: behavior
over interaction). Rectangles are dicts {"x","y","w","h"} in virtual-desktop
pixels. No-go judgment uses the FOOT BAND (design decision A): a zone blocks
the pet only when its FEET are inside the zone's y-range, so perching on a
window that sits above the zone is allowed automatically.
"""


def restrict_span(left, right, roam_area, w):
    """Narrow horizontal bounds (left, right) to the roam_area's x-range,
    keeping the pet (width w) fully inside. Empty intersection -> unchanged."""
    if not roam_area:
        return left, right
    a_left = roam_area["x"]
    a_right = roam_area["x"] + roam_area["w"] - w
    nl, nr = max(left, a_left), min(right, a_right)
    if nl > nr:
        return left, right          # area off-span: don't strand the pet
    return nl, nr


def restrict_floor(top, floor, roam_area, h):
    """Narrow vertical bounds (top, floor) to the roam_area's y-range,
    keeping the pet (height h) fully inside. Empty intersection -> unchanged."""
    if not roam_area:
        return top, floor
    a_top = roam_area["y"]
    a_floor = roam_area["y"] + roam_area["h"] - h
    nt, nf = max(top, a_top), min(floor, a_floor)
    if nt > nf:
        return top, floor
    return nt, nf


def _hits(x, w, foot_y, z):
    return (z["y"] <= foot_y <= z["y"] + z["h"]
            and x < z["x"] + z["w"] and x + w > z["x"])


def _forbidden_intervals(w, foot_y, no_go):
    """Merged x-intervals the pet's LEFT edge must avoid. A pet of width w
    overlaps zone z iff x in (z.x - w, z.x + z.w); merging overlapping/adjacent
    such intervals means an interval's EDGE is clear of every zone — so pushing
    to an edge can't land back inside a neighbour (the greedy per-zone approach
    oscillated between adjacent zones and never cleared both)."""
    ivs = sorted((z["x"] - w, z["x"] + z["w"])
                 for z in no_go if z["y"] <= foot_y <= z["y"] + z["h"])
    merged = []
    for lo, hi in ivs:
        if merged and lo <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], hi))
        else:
            merged.append((lo, hi))
    return merged


def push_out_x(x, w, foot_y, no_go, left=None, right=None):
    """Push x to the nearest zone edge outside any no-go zone the feet are in.
    When left/right (the roam bounds) are given, prefer an escape edge that
    lands within [left, right]; if NEITHER edge is in-bounds, leave x as-is
    (the pet is genuinely trapped — a zone spanning the whole reachable floor,
    a config mistake — and forcing it either way would only jam it at a wall)."""
    if not no_go:
        return x
    for lo, hi in _forbidden_intervals(w, foot_y, no_go):
        if lo < x < hi:
            cands = [lo, hi]
            if left is not None and right is not None:
                in_bounds = [c for c in cands if left <= c <= right]
                if not in_bounds:
                    continue                 # no reachable escape -> leave x
                cands = in_bounds
            x = min(cands, key=lambda c: abs(c - x))
    return x


def blocks_target(x, w, foot_y, no_go):
    """True if a candidate position's feet land inside any no-go zone."""
    return any(_hits(x, w, foot_y, z) for z in no_go)
