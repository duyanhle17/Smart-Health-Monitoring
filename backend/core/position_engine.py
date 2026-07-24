"""
Position Engine — robust two-anchor UWB tracking
================================================

The worker sends d1/d2 in metres. We intersect the two circles defined by the
physical anchor baseline, choose the permitted side of the anchor line, then
apply a small median filter and a speed-aware EMA.

Two anchors never identify a point uniquely in a full 2-D room: the two circle
intersections are mirrored. This deployment therefore requires the working area
to sit entirely on one side of the anchor line (WORK_AREA_POINT selects it).
For coverage on both sides, a third anchor is required.
"""

from collections import deque
import math
import os
import random
import statistics
import time


def _env_float(name, default, minimum=None):
    """Read a numeric deployment setting without making a bad env fatal."""
    try:
        value = float(os.environ.get(name, default))
    except (TypeError, ValueError):
        return default
    if minimum is not None and value < minimum:
        return default
    return value


def _env_point(name, default):
    raw = os.environ.get(name)
    if not raw:
        return default
    try:
        x, y = (float(part.strip()) for part in raw.split(",", 1))
        return x, y
    except (TypeError, ValueError):
        return default


def _env_bool(name, default=False):
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


# Logical coordinates rendered by the frontend map. Physical metric scale comes
# only from ANCHOR_BASELINE_M, which must be tape-measured between antenna phase
# centres before a live position is trusted.
ANCHORS = [
    {"id": "ANC_LEFT", "x": 10.0, "y": 15.0, "name": "Neo trái"},
    {"id": "ANC_RIGHT", "x": 90.0, "y": 15.0, "name": "Neo phải"},
]

ANCHOR_BASELINE_M = _env_float("ANCHOR_BASELINE_M", 6.0, minimum=0.01)
WORK_AREA_POINT = _env_point("WORK_AREA_POINT", (50.0, 70.0))
UWB_CALIBRATED = _env_bool("UWB_CALIBRATED", False)

# A small tolerance handles range noise around tangent circles. Larger geometry
# failures are rejected rather than rescaled into a made-up point.
TRIANGLE_TOLERANCE_M = _env_float("UWB_TRIANGLE_TOLERANCE_M", 0.20, minimum=0.0)
RANGE_FILTER_WINDOW = max(1, min(7, int(_env_float("UWB_RANGE_FILTER_WINDOW", 3, minimum=1))))
ALPHA = _env_float("UWB_SMOOTH_ALPHA", 0.35, minimum=0.01)
ALPHA = min(ALPHA, 1.0)
MAX_SPEED_MPS = _env_float("UWB_MAX_SPEED_MPS", 3.0, minimum=0.1)
POSITION_JITTER_M = _env_float("UWB_POSITION_JITTER_M", 0.25, minimum=0.0)
MAX_STEP_UNITS = _env_float("UWB_MAX_STEP_UNITS", 25.0, minimum=0.1)
LOW_GEOMETRY_HEIGHT_M = _env_float("UWB_LOW_GEOMETRY_HEIGHT_M", 0.20, minimum=0.0)

_smooth_state = {}
_range_windows = {}
_fix_status = {}


def reset_smooth_state(worker_id):
    """Forget tracking/filter state after an operator deliberately resets a node."""
    _smooth_state.pop(worker_id, None)
    _range_windows.pop(worker_id, None)
    _fix_status.pop(worker_id, None)


def _side(px, py, ax, ay, bx, by):
    """Signed 2-D cross product: which side of the A→B line contains P."""
    return (bx - ax) * (py - ay) - (by - ay) * (px - ax)


def units_per_metre():
    """Logical map units per physical metre, inferred from the two anchors."""
    a, b = ANCHORS[0], ANCHORS[1]
    baseline_units = math.hypot(b["x"] - a["x"], b["y"] - a["y"])
    return baseline_units / ANCHOR_BASELINE_M if ANCHOR_BASELINE_M > 0 else 1.0


def get_position_config():
    """Expose the assumptions used for live UWB positions to API/UI callers."""
    return {
        "anchors": [dict(anchor) for anchor in ANCHORS],
        "anchor_baseline_m": ANCHOR_BASELINE_M,
        "calibrated": UWB_CALIBRATED,
        "work_area_point": {"x": WORK_AREA_POINT[0], "y": WORK_AREA_POINT[1]},
        "triangle_tolerance_m": TRIANGLE_TOLERANCE_M,
        "range_filter_window": RANGE_FILTER_WINDOW,
    }


def get_fix_status(worker_id):
    """Latest UWB quality/diagnostic record; safe to return in JSON."""
    return dict(_fix_status.get(worker_id, {
        "valid": False,
        "reason": "no_measurement",
    }))


def _set_status(worker_id, valid, reason, **values):
    status = {"valid": valid, "reason": reason, "calibrated": UWB_CALIBRATED}
    status.update(values)
    _fix_status[worker_id] = status


def _finite_positive(value):
    return math.isfinite(value) and value > 0.0


def _solve_circles(d1_m, d2_m):
    """Return (logical_point, quality) or (None, diagnostic) without filtering."""
    if not _finite_positive(d1_m) or not _finite_positive(d2_m):
        return None, {"reason": "non_positive_or_non_finite_range"}

    baseline_m = ANCHOR_BASELINE_M
    if baseline_m <= 0.0:
        return None, {"reason": "invalid_anchor_baseline"}

    # Triangle feasibility in *physical metres*. Do not silently stretch
    # seriously invalid ranges: that turns a failed ranging cycle into a fake
    # point on the anchor line.
    total = d1_m + d2_m
    diff = abs(d1_m - d2_m)
    if total < baseline_m - TRIANGLE_TOLERANCE_M:
        return None, {
            "reason": "ranges_shorter_than_anchor_baseline",
            "triangle_gap_m": round(baseline_m - total, 3),
        }
    if diff > baseline_m + TRIANGLE_TOLERANCE_M:
        return None, {
            "reason": "one_circle_contains_the_other",
            "triangle_gap_m": round(diff - baseline_m, 3),
        }

    # Only correct the tiny tolerance band to a tangent geometry.
    adjusted = False
    r1, r2 = d1_m, d2_m
    if total < baseline_m:
        correction = (baseline_m - total) / 2.0
        r1 += correction
        r2 += correction
        adjusted = True
    elif diff > baseline_m:
        if r1 > r2:
            r1 = r2 + baseline_m
        else:
            r2 = r1 + baseline_m
        adjusted = True

    # Solve in metres, then map to the logical coordinate system. This keeps
    # the geometry correct even though the UI uses a 0-100 map.
    x_m = (r1 * r1 - r2 * r2 + baseline_m * baseline_m) / (2.0 * baseline_m)
    h_sq_m = r1 * r1 - x_m * x_m
    if h_sq_m < -1e-6:
        return None, {"reason": "negative_circle_height"}
    h_m = math.sqrt(max(0.0, h_sq_m))

    a, b = ANCHORS[0], ANCHORS[1]
    ax, ay, bx, by = a["x"], a["y"], b["x"], b["y"]
    dx, dy = bx - ax, by - ay
    baseline_units = math.hypot(dx, dy)
    if baseline_units <= 0.0:
        return None, {"reason": "coincident_anchor_coordinates"}
    ux, uy = dx / baseline_units, dy / baseline_units
    nx, ny = -uy, ux
    scale = units_per_metre()
    foot_x = ax + ux * x_m * scale
    foot_y = ay + uy * x_m * scale
    height_units = h_m * scale
    plus = (foot_x + nx * height_units, foot_y + ny * height_units)
    minus = (foot_x - nx * height_units, foot_y - ny * height_units)

    wanted_side = _side(WORK_AREA_POINT[0], WORK_AREA_POINT[1], ax, ay, bx, by)
    plus_side = _side(plus[0], plus[1], ax, ay, bx, by)
    chosen, branch = (plus, "plus") if (wanted_side >= 0) == (plus_side >= 0) else (minus, "minus")
    x, y = chosen
    if not (0.0 <= x <= 100.0 and 0.0 <= y <= 100.0):
        return None, {
            "reason": "outside_configured_map",
            "raw_x": round(x, 2),
            "raw_y": round(y, 2),
        }

    geometry_quality = min(1.0, h_m / max(baseline_m * 0.5, 0.001))
    return (x, y), {
        "reason": "near_tangent" if adjusted else "ok",
        "adjusted": adjusted,
        "branch": branch,
        "geometry_height_m": round(h_m, 3),
        "geometry_quality": round(geometry_quality, 3),
        "low_geometry": h_m < LOW_GEOMETRY_HEIGHT_M,
    }


def dual_anchor_tracking(d1_m, d2_m):
    """Compatibility helper: raw two-circle intersection, no filtering."""
    fix, _ = _solve_circles(float(d1_m), float(d2_m))
    return fix


def _median_filtered_ranges(worker_id, d1_m, d2_m):
    windows = _range_windows.get(worker_id)
    if windows is None:
        windows = (deque(maxlen=RANGE_FILTER_WINDOW), deque(maxlen=RANGE_FILTER_WINDOW))
        _range_windows[worker_id] = windows
    windows[0].append(d1_m)
    windows[1].append(d2_m)
    return statistics.median(windows[0]), statistics.median(windows[1])


def estimate_position(worker_id, d1, d2, yaw=0.0):
    """
    Full live pipeline. Invalid geometry never creates a location: the caller
    keeps the last coordinate and gets a machine-readable `uwb` status instead.
    `yaw` is retained for the telemetry contract but does not resolve a
    two-anchor mirror ambiguity; it will be useful only with PDR/fusion later.
    """
    try:
        raw_d1, raw_d2 = float(d1), float(d2)
    except (TypeError, ValueError):
        _set_status(worker_id, False, "non_numeric_range")
        return None

    # Validate this actual ranging cycle before it can pollute the median.
    raw_fix, raw_quality = _solve_circles(raw_d1, raw_d2)
    if raw_fix is None:
        _set_status(worker_id, False, raw_quality["reason"],
                    d1_m=raw_d1, d2_m=raw_d2, **{k: v for k, v in raw_quality.items() if k != "reason"})
        return None

    filtered_d1, filtered_d2 = _median_filtered_ranges(worker_id, raw_d1, raw_d2)
    fix, quality = _solve_circles(filtered_d1, filtered_d2)
    if fix is None:
        _set_status(worker_id, False, quality["reason"], d1_m=raw_d1, d2_m=raw_d2,
                    filtered_d1_m=round(filtered_d1, 3), filtered_d2_m=round(filtered_d2, 3),
                    **{k: v for k, v in quality.items() if k != "reason"})
        return None

    x_raw, y_raw = fix
    now = time.monotonic()
    prev = _smooth_state.get(worker_id)
    if prev is None:
        x_smooth, y_smooth = x_raw, y_raw
    else:
        elapsed = max(0.05, now - prev["at"])
        speed_step = (MAX_SPEED_MPS * elapsed + POSITION_JITTER_M) * units_per_metre()
        max_step = min(MAX_STEP_UNITS, max(speed_step, POSITION_JITTER_M * units_per_metre()))
        step = math.hypot(x_raw - prev["x"], y_raw - prev["y"])
        if step > max_step:
            ratio = max_step / step
            x_raw = prev["x"] + (x_raw - prev["x"]) * ratio
            y_raw = prev["y"] + (y_raw - prev["y"]) * ratio
        x_smooth = ALPHA * x_raw + (1.0 - ALPHA) * prev["x"]
        y_smooth = ALPHA * y_raw + (1.0 - ALPHA) * prev["y"]

    _smooth_state[worker_id] = {"x": x_smooth, "y": y_smooth, "at": now}
    _set_status(worker_id, True, quality["reason"], d1_m=round(raw_d1, 3), d2_m=round(raw_d2, 3),
                filtered_d1_m=round(filtered_d1, 3), filtered_d2_m=round(filtered_d2, 3),
                yaw_deg=round(float(yaw), 1), **{k: v for k, v in quality.items() if k != "reason"})
    return round(x_smooth, 2), round(y_smooth, 2)


def distances_from_position(x, y, noise_std=0.15):
    """Simulator helper: distances in metres for a logical map coordinate."""
    upm = units_per_metre()
    out = []
    for anchor in ANCHORS:
        d_units = math.hypot(x - anchor["x"], y - anchor["y"])
        d_m = d_units / upm + random.gauss(0.0, noise_std)
        out.append(round(max(0.05, d_m), 2))
    return out


def classify_zone(x, y):
    """Classify worker map coordinate into the existing dashboard zones."""
    if y < 35:
        return "GAMMA_STAGE"
    if x < 35 and y >= 35:
        return "ALPHA_LEFT"
    if x > 65 and y >= 35:
        return "BETA_RIGHT"
    if 36 <= x <= 64 and 45 <= y <= 85:
        return "DELTA_CENTER"
    return "CENTER_PATH"


def get_anchor_config():
    """Return frontend anchor locations without exposing mutable globals."""
    return [dict(anchor) for anchor in ANCHORS]
