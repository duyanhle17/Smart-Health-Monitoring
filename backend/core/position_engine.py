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
    if not math.isfinite(value):
        return default
    if minimum is not None and value < minimum:
        return default
    return value


def _env_optional_float(name):
    """Return a finite deployment number, or None when it was not supplied."""
    raw = os.environ.get(name)
    if raw is None or not raw.strip():
        return None
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return None
    return value if math.isfinite(value) else None


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
# A range offset is measured per tag↔anchor link at a known distance, then
# applied before the circles are solved.  It compensates the fixed antenna / RF
# delay bias without pretending that a bad ranging exchange is a location.
# Offsets may be negative, hence no `minimum` is appropriate here.
UWB_D1_OFFSET_M = _env_float("UWB_D1_OFFSET_M", 0.0)
UWB_D2_OFFSET_M = _env_float("UWB_D2_OFFSET_M", 0.0)
WORK_AREA_POINT = _env_point("WORK_AREA_POINT", (50.0, 70.0))
UWB_CALIBRATED = _env_bool("UWB_CALIBRATED", False)

# A small tolerance handles range noise around tangent circles. Larger geometry
# failures are rejected rather than rescaled into a made-up point.
TRIANGLE_TOLERANCE_M = _env_float("UWB_TRIANGLE_TOLERANCE_M", 0.20, minimum=0.0)
RANGE_FILTER_WINDOW = max(1, min(7, int(_env_float("UWB_RANGE_FILTER_WINDOW", 5, minimum=1))))
# The default is deliberately conservative.  A moving worker still reaches a
# new real fix, but a single noisy two-circle solution cannot visibly jump the
# marker across the map before the next ranging cycle confirms it.
ALPHA = _env_float("UWB_SMOOTH_ALPHA", 0.28, minimum=0.01)
ALPHA = min(ALPHA, 1.0)
SMOOTH_BETA = min(_env_float("UWB_SMOOTH_BETA", 0.08, minimum=0.0), 1.0)
STATIONARY_ALPHA = min(_env_float("UWB_STATIONARY_ALPHA", 0.10, minimum=0.01), ALPHA)
LOW_GEOMETRY_ALPHA = min(_env_float("UWB_LOW_GEOMETRY_ALPHA", 0.16, minimum=0.01), ALPHA)
MAX_SPEED_MPS = _env_float("UWB_MAX_SPEED_MPS", 3.0, minimum=0.1)
POSITION_JITTER_M = _env_float("UWB_POSITION_JITTER_M", 0.25, minimum=0.0)
MAX_STEP_UNITS = _env_float("UWB_MAX_STEP_UNITS", 25.0, minimum=0.1)
LOW_GEOMETRY_HEIGHT_M = _env_float("UWB_LOW_GEOMETRY_HEIGHT_M", 0.20, minimum=0.0)

# BNO08x motion gates.  They only control the confidence assigned to a real
# UWB measurement.  They never integrate acceleration into a published
# position, because unaided inertial position drift is unsafe for this use.
IMU_STILL_GYRO_RAD_S = _env_float("UWB_IMU_STILL_GYRO_RAD_S", 0.12, minimum=0.0)
IMU_TURN_GYRO_RAD_S = _env_float("UWB_IMU_TURN_GYRO_RAD_S", 0.45, minimum=0.0)
IMU_TURN_ACCEL_RAD_S2 = _env_float("UWB_IMU_TURN_ACCEL_RAD_S2", 1.2, minimum=0.0)
IMU_STILL_LINEAR_ACCEL_M_S2 = _env_float("UWB_IMU_STILL_LINEAR_ACCEL_M_S2", 0.25, minimum=0.0)

# IMU is deliberately an opt-in *prior*, never a replacement for a failed UWB
# exchange.  `IMU_YAW_A1_TO_A2_DEG` is sampled while the worker's forward axis
# points from anchor 1 toward anchor 2; without that physical heading
# calibration a BNO yaw has no relationship to the map coordinates.
UWB_IMU_FUSION = _env_bool("UWB_IMU_FUSION", False)
IMU_STRIDE_M = _env_float("IMU_STRIDE_M", 0.0, minimum=0.0)
IMU_YAW_A1_TO_A2_DEG = _env_optional_float("IMU_YAW_A1_TO_A2_DEG")
IMU_FORWARD_OFFSET_DEG = _env_float("IMU_FORWARD_OFFSET_DEG", 0.0)
IMU_YAW_SIGN = -1.0 if _env_float("IMU_YAW_SIGN", 1.0) < 0 else 1.0
UWB_BRANCH_MIN_HEIGHT_M = _env_float("UWB_BRANCH_MIN_HEIGHT_M", 0.25, minimum=0.0)
UWB_MAX_STEP_DELTA = max(1, min(20, int(_env_float("UWB_MAX_STEP_DELTA", 4, minimum=1))))

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
        "range_offsets_m": {"d1": UWB_D1_OFFSET_M, "d2": UWB_D2_OFFSET_M},
        "calibrated": UWB_CALIBRATED,
        "work_area_point": {"x": WORK_AREA_POINT[0], "y": WORK_AREA_POINT[1]},
        "triangle_tolerance_m": TRIANGLE_TOLERANCE_M,
        "range_filter_window": RANGE_FILTER_WINDOW,
        "imu_fusion": {
            "enabled": UWB_IMU_FUSION,
            "ready": _imu_fusion_ready(),
            "stride_m": IMU_STRIDE_M,
            "branch_min_height_m": UWB_BRANCH_MIN_HEIGHT_M,
        },
    }


def get_fix_status(worker_id):
    """Latest UWB quality/diagnostic record; safe to return in JSON."""
    return dict(_fix_status.get(worker_id, {
        "valid": False,
        "reason": "no_measurement",
    }))


def is_publishable_uwb_fix(fix, status):
    """Whether a freshly solved UWB coordinate may be shown on the live map.

    ``calibrated`` expresses the *accuracy confidence* of a real two-range
    result; it must not turn that result into the dashboard's default
    coordinate.  A marker is therefore publishable only when the current
    packet produced a finite, geometrically valid circle intersection.  The
    caller still exposes ``calibrated`` so the UI can clearly label an
    uncalibrated estimate instead of presenting it as a surveyed position.
    """
    if fix is None or not isinstance(status, dict) or not status.get("valid"):
        return False
    try:
        x, y = float(fix[0]), float(fix[1])
    except (TypeError, ValueError, IndexError):
        return False
    return math.isfinite(x) and math.isfinite(y)


def _set_status(worker_id, valid, reason, **values):
    status = {"valid": valid, "reason": reason, "calibrated": UWB_CALIBRATED}
    status.update(values)
    _fix_status[worker_id] = status


def _finite_positive(value):
    return math.isfinite(value) and value > 0.0


def _finite_float(value):
    try:
        value = float(value)
    except (TypeError, ValueError):
        return None
    return value if math.isfinite(value) else None


def _normalise_steps(value):
    value = _finite_float(value)
    if value is None or value < 0:
        return None
    return int(value)


def _normalise_stability(value):
    value = _finite_float(value)
    if value is None or value < 0:
        return None
    return int(value)


def _motion_context(previous, steps, gyro_x, gyro_y, gyro_z, linear_accel,
                    stability, yaw_accuracy, gyro_accuracy):
    """Summarise BNO08x motion without turning it into standalone PDR.

    The sensor can reliably tell us that a helmet is stationary or rotating,
    which is useful for rejecting visible UWB jitter.  Its axes and heading
    are not assumed to be aligned with the installed anchor map here.
    """
    gx = _finite_float(gyro_x)
    gy = _finite_float(gyro_y)
    gz = _finite_float(gyro_z)
    gyro_mag = None
    if gx is not None and gy is not None and gz is not None:
        gyro_mag = math.sqrt(gx * gx + gy * gy + gz * gz)
    lin_accel = _finite_float(linear_accel)
    stability = _normalise_stability(stability)
    yaw_accuracy = _normalise_stability(yaw_accuracy)
    gyro_accuracy = _normalise_stability(gyro_accuracy)
    gyro_trusted = gyro_accuracy is None or gyro_accuracy > 0

    step_delta = None
    if previous is not None and steps is not None and previous.get("steps") is not None:
        step_delta = steps - previous["steps"]

    angular_accel = None
    if previous is not None and gyro_mag is not None and previous.get("gyro_mag") is not None:
        elapsed = max(0.05, time.monotonic() - previous.get("at", time.monotonic()))
        angular_accel = (gyro_mag - previous["gyro_mag"]) / elapsed

    # BNO stability values: 1=on-table, 2=stationary, 3=stable, 4=motion.
    # Treat only 1/2 as a zero-velocity cue; "stable" is not necessarily still.
    stationary = (
        stability in {1, 2}
        and (not gyro_trusted or gyro_mag is None or gyro_mag <= IMU_STILL_GYRO_RAD_S)
        and (lin_accel is None or lin_accel <= IMU_STILL_LINEAR_ACCEL_M_S2)
        and (step_delta is None or step_delta <= 0)
    )
    # Even while BNO reports gyro accuracy 0 after boot, a large angular rate
    # is still a useful *soft* indication that the helmet is turning. Raise
    # the threshold in that state and never use it to generate a coordinate.
    # The stability classifier remains the source of zero-velocity decisions.
    turn_multiplier = 1.5 if gyro_accuracy == 0 else 1.0
    turning = (
        (gyro_mag is not None and gyro_mag >= IMU_TURN_GYRO_RAD_S * turn_multiplier)
        or (angular_accel is not None and abs(angular_accel) >= IMU_TURN_ACCEL_RAD_S2 * turn_multiplier)
    )
    state = "stationary" if stationary else ("turning" if turning else "moving")
    return {
        "stationary": stationary,
        "turning": turning,
        "gyro_mag": gyro_mag,
        "angular_accel": angular_accel,
        "linear_accel": lin_accel,
        "stability": stability,
        "yaw_accuracy": yaw_accuracy,
        "step_delta": step_delta,
        "status": {
            "motion_state": state,
            "gyro_rad_s": round(gyro_mag, 3) if gyro_mag is not None else None,
            "angular_accel_rad_s2": round(angular_accel, 3) if angular_accel is not None else None,
            "linear_accel_m_s2": round(lin_accel, 3) if lin_accel is not None else None,
            "imu_stability": stability,
            "yaw_accuracy": yaw_accuracy,
            "gyro_accuracy": gyro_accuracy,
            "gyro_trusted": gyro_trusted,
        },
    }


def _imu_fusion_ready():
    return UWB_IMU_FUSION and IMU_STRIDE_M > 0.0 and IMU_YAW_A1_TO_A2_DEG is not None


def _correct_ranges(raw_d1_m, raw_d2_m):
    """Convert raw DW3000 ranges into link-calibrated physical ranges."""
    return raw_d1_m + UWB_D1_OFFSET_M, raw_d2_m + UWB_D2_OFFSET_M


def _range_status_values(raw_d1_m, raw_d2_m, d1_m, d2_m):
    """Keep both measurement and calibration result visible to operators."""
    return {
        "raw_d1_m": round(raw_d1_m, 3),
        "raw_d2_m": round(raw_d2_m, 3),
        "d1_m": round(d1_m, 3),
        "d2_m": round(d2_m, 3),
        "d1_offset_m": UWB_D1_OFFSET_M,
        "d2_offset_m": UWB_D2_OFFSET_M,
    }


def _circle_candidates(d1_m, d2_m):
    """Return both UWB circle intersections plus quality, without choosing one."""
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

    geometry_quality = min(1.0, h_m / max(baseline_m * 0.5, 0.001))
    return {"plus": plus, "minus": minus}, {
        "reason": "near_tangent" if adjusted else "ok",
        "adjusted": adjusted,
        "geometry_height_m": round(h_m, 3),
        "geometry_quality": round(geometry_quality, 3),
        "low_geometry": h_m < LOW_GEOMETRY_HEIGHT_M,
        "_height_m": h_m,
    }


def _in_configured_map(point):
    return 0.0 <= point[0] <= 100.0 and 0.0 <= point[1] <= 100.0


def _work_area_candidate(candidates):
    """Choose the deployed-side solution, preserving the pre-fusion behavior."""
    a, b = ANCHORS[0], ANCHORS[1]
    ax, ay, bx, by = a["x"], a["y"], b["x"], b["y"]
    plus = candidates["plus"]
    wanted_side = _side(WORK_AREA_POINT[0], WORK_AREA_POINT[1], ax, ay, bx, by)
    plus_side = _side(plus[0], plus[1], ax, ay, bx, by)
    return (plus, "plus") if (wanted_side >= 0) == (plus_side >= 0) else (candidates["minus"], "minus")


def _solve_circles(d1_m, d2_m, pdr_prior=None):
    """Return one logical UWB point; IMU may choose only between valid mirrors."""
    candidates, quality = _circle_candidates(d1_m, d2_m)
    if candidates is None:
        return None, quality

    chosen, branch = _work_area_candidate(candidates)
    branch_source = "work_area"

    # The BNO step/yaw prior can preserve a known side after a previous real
    # UWB fix. It is deliberately ignored near the anchor line: there both
    # candidates collapse together and no heading can add useful geometry.
    if pdr_prior is not None and quality["_height_m"] >= UWB_BRANCH_MIN_HEIGHT_M:
        viable = [(name, point) for name, point in candidates.items() if _in_configured_map(point)]
        if viable:
            branch, chosen = min(
                viable,
                key=lambda item: math.hypot(item[1][0] - pdr_prior[0], item[1][1] - pdr_prior[1]),
            )
            branch_source = "imu_pdr"

    x, y = chosen
    if not _in_configured_map(chosen):
        return None, {
            "reason": "outside_configured_map",
            "raw_x": round(x, 2),
            "raw_y": round(y, 2),
        }

    quality.pop("_height_m", None)
    quality.update({
        "branch": branch,
        "branch_source": branch_source,
        "branch_ambiguous": quality["low_geometry"],
    })
    return (x, y), quality


def dual_anchor_tracking(d1_m, d2_m):
    """Compatibility helper: calibrated two-circle intersection, no filtering."""
    raw_d1_m, raw_d2_m = float(d1_m), float(d2_m)
    d1_m, d2_m = _correct_ranges(raw_d1_m, raw_d2_m)
    fix, _ = _solve_circles(d1_m, d2_m)
    return fix


def _median_filtered_ranges(worker_id, d1_m, d2_m):
    windows = _range_windows.get(worker_id)
    if windows is None:
        windows = (deque(maxlen=RANGE_FILTER_WINDOW), deque(maxlen=RANGE_FILTER_WINDOW))
        _range_windows[worker_id] = windows
    windows[0].append(d1_m)
    windows[1].append(d2_m)
    return statistics.median(windows[0]), statistics.median(windows[1])


def _imu_pdr_prior(previous, yaw, steps, imu_ok):
    """Return an IMU-only continuity prior, never a position to publish."""
    diagnostic = {
        "imu_fusion_enabled": UWB_IMU_FUSION,
        "pdr_available": False,
    }
    if not _imu_fusion_ready():
        diagnostic["pdr_reason"] = "imu_fusion_not_calibrated"
        return None, diagnostic
    if not imu_ok:
        diagnostic["pdr_reason"] = "imu_unavailable"
        return None, diagnostic
    if previous is None or "steps" not in previous:
        diagnostic["pdr_reason"] = "no_previous_uwb_fix"
        return None, diagnostic

    step_count = _normalise_steps(steps)
    yaw_deg = _finite_float(yaw)
    if step_count is None or yaw_deg is None:
        diagnostic["pdr_reason"] = "missing_imu_step_or_yaw"
        return None, diagnostic

    step_delta = step_count - previous["steps"]
    if step_delta <= 0:
        diagnostic.update({"pdr_reason": "no_new_steps", "pdr_step_delta": step_delta})
        return None, diagnostic
    if step_delta > UWB_MAX_STEP_DELTA:
        diagnostic.update({"pdr_reason": "step_delta_too_large", "pdr_step_delta": step_delta})
        return None, diagnostic

    a, b = ANCHORS[0], ANCHORS[1]
    dx, dy = b["x"] - a["x"], b["y"] - a["y"]
    baseline_units = math.hypot(dx, dy)
    if baseline_units <= 0.0:
        diagnostic["pdr_reason"] = "coincident_anchor_coordinates"
        return None, diagnostic

    # theta=0 means the worker's forward axis points A1→A2. A one-metre walk
    # along that line is the deployment check for yaw direction/sign.
    heading_deg = IMU_YAW_SIGN * (yaw_deg - IMU_YAW_A1_TO_A2_DEG) + IMU_FORWARD_OFFSET_DEG
    theta = math.radians(heading_deg)
    ux, uy = dx / baseline_units, dy / baseline_units
    nx, ny = -uy, ux
    distance_m = step_delta * IMU_STRIDE_M
    distance_units = distance_m * units_per_metre()
    move_x = (ux * math.cos(theta) + nx * math.sin(theta)) * distance_units
    move_y = (uy * math.cos(theta) + ny * math.sin(theta)) * distance_units
    prior = previous["x"] + move_x, previous["y"] + move_y
    diagnostic.update({
        "pdr_available": True,
        "pdr_step_delta": step_delta,
        "pdr_heading_deg": round(heading_deg, 1),
        "pdr_dx_m": round(move_x / units_per_metre(), 3),
        "pdr_dy_m": round(move_y / units_per_metre(), 3),
    })
    return prior, diagnostic


def estimate_position(worker_id, d1, d2, yaw=0.0, steps=None, imu_ok=False,
                      gyro_x=None, gyro_y=None, gyro_z=None,
                      linear_accel=None, stability=None, yaw_accuracy=None,
                      gyro_accuracy=None):
    """
    Full live pipeline. Invalid geometry never creates a location: the caller
    keeps the last coordinate and gets a machine-readable `uwb` status instead.
    When explicitly calibrated, yaw + step count can choose between the two
    real UWB circle intersections. It can never create a location by itself.
    """
    try:
        raw_d1, raw_d2 = float(d1), float(d2)
    except (TypeError, ValueError):
        _set_status(worker_id, False, "non_numeric_range")
        return None

    if not math.isfinite(raw_d1) or not math.isfinite(raw_d2):
        _set_status(worker_id, False, "non_finite_raw_range")
        return None

    yaw_deg = _finite_float(yaw)
    step_count = _normalise_steps(steps)
    previous = _smooth_state.get(worker_id)
    motion = _motion_context(previous, step_count, gyro_x, gyro_y, gyro_z,
                              linear_accel, stability, yaw_accuracy, gyro_accuracy)
    pdr_prior, pdr_values = _imu_pdr_prior(previous, yaw_deg, step_count, bool(imu_ok))

    d1_m, d2_m = _correct_ranges(raw_d1, raw_d2)
    range_values = _range_status_values(raw_d1, raw_d2, d1_m, d2_m)

    # Validate this actual *calibrated* ranging cycle before it can pollute the
    # median.  A raw DW3000 ToF estimate can be negative near zero until its
    # fixed link offset is applied; only the corrected physical range belongs
    # in the triangle solver.
    raw_fix, raw_quality = _solve_circles(d1_m, d2_m)
    if raw_fix is None:
        _set_status(worker_id, False, raw_quality["reason"], **range_values,
                    **pdr_values, **motion["status"],
                    **{k: v for k, v in raw_quality.items() if k != "reason"})
        return None

    filtered_d1, filtered_d2 = _median_filtered_ranges(worker_id, d1_m, d2_m)
    fix, quality = _solve_circles(filtered_d1, filtered_d2, pdr_prior=pdr_prior)
    if fix is None:
        _set_status(worker_id, False, quality["reason"], **range_values,
                    **pdr_values, **motion["status"],
                    filtered_d1_m=round(filtered_d1, 3), filtered_d2_m=round(filtered_d2, 3),
                    **{k: v for k, v in quality.items() if k != "reason"})
        return None

    x_raw, y_raw = fix
    now = time.monotonic()
    prev = _smooth_state.get(worker_id)
    if prev is None:
        x_smooth, y_smooth = x_raw, y_raw
        vx, vy = 0.0, 0.0
        smoothing_alpha = ALPHA
    else:
        elapsed = max(0.05, now - prev["at"])
        if motion["stationary"]:
            # Zero-velocity update: a BNO08x stationary classification lets
            # us suppress map jitter instead of chasing every range wobble.
            pred_x, pred_y = prev["x"], prev["y"]
            prior_vx, prior_vy = 0.0, 0.0
            smoothing_alpha = STATIONARY_ALPHA
        else:
            prior_vx = _finite_float(prev.get("vx")) or 0.0
            prior_vy = _finite_float(prev.get("vy")) or 0.0
            pred_x = prev["x"] + prior_vx * elapsed
            pred_y = prev["y"] + prior_vy * elapsed
            smoothing_alpha = LOW_GEOMETRY_ALPHA if quality.get("low_geometry") else ALPHA
            if motion["turning"]:
                # A rapid helmet rotation is a common moment for multipath or
                # magnetic-heading transients. Trust the real UWB update, but
                # blend it more cautiously until the next cycle agrees.
                smoothing_alpha = min(smoothing_alpha, LOW_GEOMETRY_ALPHA)

        innovation_x = x_raw - pred_x
        innovation_y = y_raw - pred_y
        innovation = math.hypot(innovation_x, innovation_y)
        speed_step = (MAX_SPEED_MPS * elapsed + POSITION_JITTER_M) * units_per_metre()
        if motion["stationary"]:
            max_step = max(POSITION_JITTER_M * units_per_metre(), 0.5)
        else:
            max_step = min(MAX_STEP_UNITS, max(speed_step, POSITION_JITTER_M * units_per_metre()))
        if innovation > max_step:
            ratio = max_step / innovation
            innovation_x *= ratio
            innovation_y *= ratio

        x_smooth = pred_x + smoothing_alpha * innovation_x
        y_smooth = pred_y + smoothing_alpha * innovation_y
        if motion["stationary"]:
            vx, vy = 0.0, 0.0
        else:
            beta = SMOOTH_BETA * (0.5 if motion["turning"] else 1.0)
            measured_vx = innovation_x / elapsed
            measured_vy = innovation_y / elapsed
            vx = (1.0 - beta) * prior_vx + beta * measured_vx
            vy = (1.0 - beta) * prior_vy + beta * measured_vy
            max_velocity = MAX_SPEED_MPS * units_per_metre()
            velocity = math.hypot(vx, vy)
            if velocity > max_velocity:
                ratio = max_velocity / velocity
                vx *= ratio
                vy *= ratio

    next_state = {"x": x_smooth, "y": y_smooth, "vx": vx, "vy": vy, "at": now}
    if step_count is not None:
        next_state["steps"] = step_count
    if motion["gyro_mag"] is not None:
        next_state["gyro_mag"] = motion["gyro_mag"]
    _smooth_state[worker_id] = next_state
    _set_status(worker_id, True, quality["reason"], **range_values,
                filtered_d1_m=round(filtered_d1, 3), filtered_d2_m=round(filtered_d2, 3),
                yaw_deg=round(yaw_deg, 1) if yaw_deg is not None else None,
                smoothing_alpha=round(smoothing_alpha, 3),
                **pdr_values, **motion["status"],
                **{k: v for k, v in quality.items() if k != "reason"})
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
