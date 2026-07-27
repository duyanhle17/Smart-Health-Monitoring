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

For the explicitly declared ``on-anchor-line`` commissioning setup only, an
opt-in degraded mode can also estimate the *along-line* coordinate when a
short range pair cannot form two circles.  It is never a 2-D position: the
perpendicular coordinate is the declared physical constraint and callers must
render it as a 1-D line estimate.
"""

from collections import deque
import math
import os
import random
import statistics
import time

from backend.core import heading_offset
from backend.core.uwb_imu_filter import UwbImuFilter, UwbImuFilterConfig


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
# Vertical phase-centre separation (anchor_i height minus tag height) in
# metres. DW3000 measures slant range; the 2-D floor solver must use the
# corresponding horizontal range. Keep all nodes level/equal-height when
# possible, otherwise survey these values rather than letting height bias y.
UWB_D1_HEIGHT_DELTA_M = _env_float("UWB_D1_HEIGHT_DELTA_M", 0.0)
UWB_D2_HEIGHT_DELTA_M = _env_float("UWB_D2_HEIGHT_DELTA_M", 0.0)
WORK_AREA_POINT = _env_point("WORK_AREA_POINT", (50.0, 70.0))
UWB_CALIBRATED = _env_bool("UWB_CALIBRATED", False)
# A two-anchor line fallback is useful only for a declared on-line deployment.
# It derives the along-baseline coordinate from two real ranges but deliberately
# does not pretend to know the perpendicular coordinate.
UWB_LINE_FALLBACK = _env_bool("UWB_LINE_FALLBACK", False)
LINE_FALLBACK_TOLERANCE_M = _env_float("UWB_LINE_FALLBACK_TOLERANCE_M", 0.35, minimum=0.0)

# Direct two-range EKF. It works in metric coordinates and is opt-in until
# surveyed link calibration and the allowed working side have been verified.
# Unlike the older position EMA, it consumes d1/d2 as measurements directly.
UWB_2D_FUSION = _env_bool("UWB_2D_FUSION", False)
UWB_2D_RANGE_STD_M = _env_float("UWB_2D_RANGE_STD_M", 0.18, minimum=0.01)
UWB_2D_IMU_HOLD_SECONDS = _env_float("UWB_2D_IMU_HOLD_SECONDS", 1.5, minimum=0.1)
UWB_2D_INNOVATION_GATE = _env_float("UWB_2D_INNOVATION_GATE", 9.21, minimum=0.1)
UWB_2D_MAX_RANGE_AGE_MS = _env_float("UWB_2D_MAX_RANGE_AGE_MS", 700.0, minimum=0.0)
UWB_2D_MAX_IMU_AGE_MS = _env_float("UWB_2D_MAX_IMU_AGE_MS", 250.0, minimum=1.0)
# Current firmware publishes an atomic range sequence and sample age. Require
# both when enabling the production direct filter so a repeated HTTP payload
# cannot look like a new radio measurement. Older firmware can be admitted
# deliberately for lab work by setting this false.
UWB_2D_REQUIRE_RANGE_METADATA = _env_bool("UWB_2D_REQUIRE_RANGE_METADATA", True)
# The worker emits a random non-zero ``range_epoch`` at boot.  Retain a small
# history of retired epochs so a delayed packet from the previous boot cannot
# rewind the direct tracker after a real reboot.  The epoch, not a decreasing
# sequence number, is the authority for accepting a source reset.
UWB_2D_RETIRED_RANGE_EPOCHS = max(1, min(16, int(_env_float(
    "UWB_2D_RETIRED_RANGE_EPOCHS", 4, minimum=1
))))

# A small tolerance handles range noise around tangent circles. Larger geometry
# failures are rejected rather than rescaled into a made-up point.
TRIANGLE_TOLERANCE_M = _env_float("UWB_TRIANGLE_TOLERANCE_M", 0.20, minimum=0.0)
# Window 3, not 5: the tag already medians five raw SS-TWR samples inside each
# 200 ms cycle, so this cross-cycle median only has to absorb the rare bad
# *pair*. At the 1-2.5 Hz pair rate actually reaching the server, a 5-sample
# window meant ~2 s of group delay - a walking worker's marker trailed metres
# behind them, which costs more accuracy than the outliers it suppressed.
RANGE_FILTER_WINDOW = max(1, min(7, int(_env_float("UWB_RANGE_FILTER_WINDOW", 3, minimum=1))))
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
# Linear acceleration is only allowed to move the EKF after the operator has
# commissioned the BNO08x mounting/axis frame. Yaw alignment alone is not
# enough when the helmet can tilt, so this stays fail-closed by default.
IMU_ACCEL_FRAME_CALIBRATED = _env_bool("IMU_ACCEL_FRAME_CALIBRATED", False)
IMU_STRIDE_M = _env_float("IMU_STRIDE_M", 0.0, minimum=0.0)
IMU_YAW_A1_TO_A2_DEG = _env_optional_float("IMU_YAW_A1_TO_A2_DEG")
IMU_FORWARD_OFFSET_DEG = _env_float("IMU_FORWARD_OFFSET_DEG", 0.0)
IMU_YAW_SIGN = -1.0 if _env_float("IMU_YAW_SIGN", 1.0) < 0 else 1.0
UWB_BRANCH_MIN_HEIGHT_M = _env_float("UWB_BRANCH_MIN_HEIGHT_M", 0.25, minimum=0.0)
UWB_MAX_STEP_DELTA = max(1, min(20, int(_env_float("UWB_MAX_STEP_DELTA", 4, minimum=1))))
# Game RV accuracy is gyro-derived; the learner's own straight-segment residual
# gating is the real protection, so this floor stays permissive by default.
YAW_GAME_MIN_ACCURACY = max(0, int(_env_float("UWB_YAW_GAME_MIN_ACCURACY", 1, minimum=0)))
# Historical (batched) range pairs may back-date the EKF up to this far; the
# live-pair freshness boundary stays UWB_2D_MAX_RANGE_AGE_MS.
UWB_BATCH_MAX_AGE_MS = _env_float("UWB_BATCH_MAX_AGE_MS", 3000.0, minimum=0.0)

_smooth_state = {}
_range_windows = {}
_line_range_windows = {}
_fix_status = {}
_uwb_imu_filters = {}
_fusion_range_sequences = {}


def reset_smooth_state(worker_id):
    """Forget tracking/filter state after an operator deliberately resets a node."""
    _smooth_state.pop(worker_id, None)
    _range_windows.pop(worker_id, None)
    _line_range_windows.pop(worker_id, None)
    _fix_status.pop(worker_id, None)
    _uwb_imu_filters.pop(worker_id, None)
    _fusion_range_sequences.pop(worker_id, None)
    heading_offset.reset(worker_id)


def apply_range_offsets(d1_offset_m, d2_offset_m):
    """Replace the per-link range offsets at runtime (operator-approved).

    Every worker's tracking state is reset: median windows and EKF states were
    built from ranges corrected with the OLD offsets and must not blend with
    newly corrected ones.  Raises ValueError on non-finite or absurd values —
    an offset larger than a few metres is a measurement mistake, not a
    calibration.
    """
    global UWB_D1_OFFSET_M, UWB_D2_OFFSET_M
    d1 = _finite_float(d1_offset_m)
    d2 = _finite_float(d2_offset_m)
    if d1 is None or d2 is None or abs(d1) > 5.0 or abs(d2) > 5.0:
        raise ValueError("range offsets must be finite and within ±5 m")
    UWB_D1_OFFSET_M = d1
    UWB_D2_OFFSET_M = d2
    for worker_id in set().union(
        _smooth_state, _range_windows, _line_range_windows,
        _fix_status, _uwb_imu_filters, _fusion_range_sequences,
    ):
        reset_smooth_state(worker_id)
    return {"d1": d1, "d2": d2}


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
    fusion_block_reason = None
    if UWB_LINE_FALLBACK:
        fusion_block_reason = "line_fallback_enabled"
    elif _allowed_metric_side() is None:
        fusion_block_reason = "work_area_point_on_anchor_baseline"
    return {
        "anchors": [dict(anchor) for anchor in ANCHORS],
        "anchor_baseline_m": ANCHOR_BASELINE_M,
        "range_offsets_m": {"d1": UWB_D1_OFFSET_M, "d2": UWB_D2_OFFSET_M},
        "range_height_delta_m": {"d1": UWB_D1_HEIGHT_DELTA_M, "d2": UWB_D2_HEIGHT_DELTA_M},
        "calibrated": UWB_CALIBRATED,
        "work_area_point": {"x": WORK_AREA_POINT[0], "y": WORK_AREA_POINT[1]},
        "triangle_tolerance_m": TRIANGLE_TOLERANCE_M,
        "range_filter_window": RANGE_FILTER_WINDOW,
        "line_fallback_enabled": UWB_LINE_FALLBACK,
        "line_fallback_tolerance_m": LINE_FALLBACK_TOLERANCE_M,
        "two_d_fusion": {
            "enabled": UWB_2D_FUSION,
            "active": UWB_2D_FUSION and fusion_block_reason is None,
            "blocked_reason": fusion_block_reason if UWB_2D_FUSION else None,
            "range_std_m": UWB_2D_RANGE_STD_M,
            "imu_prediction_configured": _imu_accel_fusion_ready() or bool(
                UWB_IMU_FUSION and IMU_ACCEL_FRAME_CALIBRATED
                and heading_offset.commissioned_workers()
            ),
            "max_imu_age_ms": UWB_2D_MAX_IMU_AGE_MS,
            "requires_fresh_range_metadata": UWB_2D_REQUIRE_RANGE_METADATA,
            "requires_source_epoch_for_reset": True,
            "requires_line_fallback_disabled": True,
        },
        "imu_fusion": {
            "enabled": UWB_IMU_FUSION,
            # "Ready" means at least one usable yaw→map mapping exists: the
            # manual env commissioning, or an online-commissioned worker.
            "ready": _imu_fusion_ready() or bool(
                UWB_IMU_FUSION and IMU_STRIDE_M > 0.0
                and heading_offset.commissioned_workers()
            ),
            "stride_m": IMU_STRIDE_M,
            "branch_min_height_m": UWB_BRANCH_MIN_HEIGHT_M,
            "online_yaw_learner": heading_offset.YAW_OFFSET_LEARNER,
            "learned_workers": heading_offset.commissioned_workers(),
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


def _imu_fusion_ready(worker_id=None):
    """A yaw→map mapping exists: manual commissioning or the online learner."""
    if not (UWB_IMU_FUSION and IMU_STRIDE_M > 0.0):
        return False
    if IMU_YAW_A1_TO_A2_DEG is not None:
        return True
    return worker_id is not None and heading_offset.commissioned(worker_id)


def _imu_accel_fusion_ready(worker_id=None):
    """Whether BNO body acceleration has a commissioned map-heading frame."""
    if not (UWB_IMU_FUSION and IMU_ACCEL_FRAME_CALIBRATED):
        return False
    if IMU_YAW_A1_TO_A2_DEG is not None:
        return True
    return worker_id is not None and heading_offset.commissioned(worker_id)


def _imu_epoch_key(value):
    """Normalise the firmware's numeric imu_epoch into a stable comparison key."""
    epoch = _finite_float(value)
    if epoch is None or epoch <= 0.0 or not math.isclose(epoch, round(epoch), abs_tol=1e-6):
        return None
    return int(round(epoch))


def _baseline_angle_logical_deg():
    a, b = ANCHORS[0], ANCHORS[1]
    return math.degrees(math.atan2(b["y"] - a["y"], b["x"] - a["x"]))


def _resolve_map_heading(worker_id, yaw_deg, yaw_game_deg, yaw_game_accuracy,
                         yaw_game_age_ms, imu_epoch):
    """Best available A1→A2-frame heading and its source label.

    Prefers the online-learned Game RV mapping (gyro-only, unaffected by the
    magnetic environment that starves the RotationVector accuracy gate in a
    steel workshop); falls back to the manually commissioned
    IMU_YAW_A1_TO_A2_DEG ritual.  Returns ``(None, None)`` when neither
    mapping is usable — a heading must never be guessed.
    """
    game_yaw = _finite_float(yaw_game_deg)
    game_age = _finite_float(yaw_game_age_ms)
    game_accuracy = _normalise_stability(yaw_game_accuracy)
    if (
        game_yaw is not None
        and game_age is not None and 0.0 <= game_age <= UWB_2D_MAX_IMU_AGE_MS
        and (game_accuracy is None or game_accuracy >= YAW_GAME_MIN_ACCURACY)
    ):
        learned = heading_offset.map_heading(
            worker_id, yaw_game_deg=game_yaw, imu_epoch=_imu_epoch_key(imu_epoch)
        )
        if learned is not None:
            # The learner works in the logical map frame; consumers want the
            # A1→A2 metric frame (0° = along the baseline).
            return learned - _baseline_angle_logical_deg(), "yaw_game_learned"
    if IMU_YAW_A1_TO_A2_DEG is not None and yaw_deg is not None:
        return (
            IMU_YAW_SIGN * (yaw_deg - IMU_YAW_A1_TO_A2_DEG) + IMU_FORWARD_OFFSET_DEG,
            "yaw_static",
        )
    return None, None


def _allowed_metric_side():
    """Map the configured logical work side onto the EKF's +metric-y side."""
    a, b = ANCHORS[0], ANCHORS[1]
    side = _side(WORK_AREA_POINT[0], WORK_AREA_POINT[1], a["x"], a["y"], b["x"], b["y"])
    if abs(side) <= 1e-7:
        return None
    return 1 if side > 0.0 else -1


def _metric_to_logical(point_m):
    """Convert (along-baseline, permitted-normal) metres to map coordinates."""
    x_m, y_m = point_m
    a, b = ANCHORS[0], ANCHORS[1]
    ax, ay, bx, by = a["x"], a["y"], b["x"], b["y"]
    dx, dy = bx - ax, by - ay
    baseline_units = math.hypot(dx, dy)
    if baseline_units <= 0.0:
        return None
    ux, uy = dx / baseline_units, dy / baseline_units
    nx, ny = -uy, ux
    scale = units_per_metre()
    return ax + (ux * x_m + nx * y_m) * scale, ay + (uy * x_m + ny * y_m) * scale


def _fusion_tracker(worker_id):
    """Get an isolated direct-range tracker for one physical worker."""
    tracker = _uwb_imu_filters.get(worker_id)
    if tracker is None:
        allowed_side = _allowed_metric_side()
        if allowed_side is None:
            raise ValueError("WORK_AREA_POINT must be strictly off the anchor baseline for two-anchor fusion")
        tracker = UwbImuFilter(
            ((0.0, 0.0), (ANCHOR_BASELINE_M, 0.0)),
            allowed_side=allowed_side,
            config=UwbImuFilterConfig(
                range_std_m=UWB_2D_RANGE_STD_M,
                innovation_gate_chi2=UWB_2D_INNOVATION_GATE,
                hold_seconds=UWB_2D_IMU_HOLD_SECONDS,
            ),
        )
        _uwb_imu_filters[worker_id] = tracker
    return tracker


def _yaw_accuracy_degrees(yaw_accuracy_rad):
    accuracy = _finite_float(yaw_accuracy_rad)
    if accuracy is None or accuracy < 0.0:
        return None
    return math.degrees(accuracy)


def _range_epoch_token(value):
    """Return a stable, non-empty source range-epoch token when supplied.

    The ESP32 sends an unsigned random boot token.  Normalising numeric JSON
    values avoids treating ``123`` and ``123.0`` as two separate worker boots;
    a zero epoch is reserved for legacy/unknown firmware and must not authorise
    a sequence reset.
    """
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, int):
        return str(value) if value > 0 else None
    if isinstance(value, float):
        if not math.isfinite(value) or value <= 0.0 or not value.is_integer():
            return None
        return str(int(value))
    token = str(value).strip()
    if not token or token.lower() in {"none", "null", "nan", "0"}:
        return None
    # A proxy or form client can turn the JSON number into text. Keep its
    # numeric identity stable as well, while preserving non-numeric boot IDs.
    try:
        numeric = float(token)
    except ValueError:
        return token[:96]
    if not math.isfinite(numeric) or not numeric.is_integer() or numeric <= 0.0:
        return None
    return str(int(numeric))


def _range_sequence_state(sequence, epoch, previous=None):
    """Build sequence bookkeeping without accidentally forgetting an epoch."""
    retired_epochs = []
    inherited_epoch = None
    inherited_sample_time = None
    if previous is not None:
        inherited_epoch = previous.get("epoch")
        retired_epochs = list(previous.get("retired_epochs", ()))
        inherited_sample_time = previous.get("sample_time_s")
    state = {
        "sequence": sequence,
        # A packet which omits its epoch must not erase an already established
        # source identity; it is still accepted only when its sequence moves
        # forward below.
        "epoch": epoch if epoch is not None else inherited_epoch,
        "retired_epochs": tuple(retired_epochs[-UWB_2D_RETIRED_RANGE_EPOCHS:]),
    }
    if inherited_sample_time is not None:
        # The per-worker monotonic sample-time floor must survive sequence
        # bookkeeping rebuilds, or a back-dated batch pair computes a sample
        # time older than the filter clock and is dropped as out-of-order.
        state["sample_time_s"] = inherited_sample_time
    return state


def _fresh_unseen_range_sequence(worker_id, range_seq, range_age_ms, range_epoch=None,
                                 historical=False):
    """Reject stale snapshots; accept a reboot only from a source epoch change.

    ``range_seq`` is monotonic only within one ESP32 boot, so a lower sequence
    is not enough evidence to reset a live tracker.  Current firmware pairs it
    with a non-zero random ``range_epoch`` generated at boot.  That source
    identity is required for a reset, and recently retired identities are
    rejected to avoid a delayed pre-reboot HTTP packet rewinding the filter.

    ``historical`` marks a back-dated pair from a telemetry batch: it may be
    older than the live freshness boundary (up to UWB_BATCH_MAX_AGE_MS) because
    it updates the filter at its own back-dated timestamp, never as "now".
    Sequence/epoch replay protection applies unchanged.
    """
    age = _finite_float(range_age_ms)
    if age is None:
        if UWB_2D_REQUIRE_RANGE_METADATA:
            return False, "range_age_required", False
    elif age < 0.0 or age > (UWB_BATCH_MAX_AGE_MS if historical else UWB_2D_MAX_RANGE_AGE_MS):
        return False, "range_snapshot_stale", False
    sequence = _finite_float(range_seq)
    if sequence is None:
        if UWB_2D_REQUIRE_RANGE_METADATA:
            return False, "range_sequence_required", False
        # Older firmware lacks a sequence; arrival order remains usable only
        # when the operator deliberately permits that lab compatibility mode.
        return True, "range_sequence_unavailable", False
    if sequence < 0.0 or not math.isclose(sequence, round(sequence), abs_tol=1e-6):
        return False, "invalid_range_sequence", False
    sequence = int(sequence)
    epoch = _range_epoch_token(range_epoch)
    previous = _fusion_range_sequences.get(worker_id)
    if previous is None:
        _fusion_range_sequences[worker_id] = _range_sequence_state(sequence, epoch)
        return True, "range_sequence_fresh", False

    previous_sequence = previous.get("sequence")
    previous_epoch = previous.get("epoch")
    retired_epochs = set(previous.get("retired_epochs", ()))
    if epoch is not None and epoch in retired_epochs:
        return False, "range_epoch_retired", False

    # The source changed its boot identity.  Start a clean EKF even if its
    # first delivered packet already has a sequence above zero (for example
    # after Wi-Fi reconnect).  Remember the old identity to reject delayed
    # packets from it later.
    if epoch is not None and epoch != previous_epoch:
        next_state = _range_sequence_state(sequence, epoch, previous)
        if previous_epoch is not None:
            history = list(next_state["retired_epochs"])
            history.append(previous_epoch)
            next_state["retired_epochs"] = tuple(history[-UWB_2D_RETIRED_RANGE_EPOCHS:])
        _fusion_range_sequences[worker_id] = next_state
        return True, "range_epoch_changed", True

    if sequence == previous_sequence:
        return False, "range_snapshot_duplicate_or_out_of_order", False
    if sequence < previous_sequence:
        # Do not use a numeric reset heuristic here.  It accepts stale packets
        # after reboot and can leave a worker on an old map point.  A current
        # firmware source must publish a new range_epoch to authorise reset.
        return False, "range_sequence_reset_requires_epoch", False

    _fusion_range_sequences[worker_id] = _range_sequence_state(sequence, epoch, previous)
    return True, "range_sequence_fresh", False


def _range_sample_timestamp(worker_id, now_s, range_age_ms):
    """Approximate RF-snapshot time while preserving per-worker monotonicity."""
    age_ms = _finite_float(range_age_ms)
    sample_time = now_s - (max(0.0, age_ms) / 1000.0 if age_ms is not None else 0.0)
    sequence_state = _fusion_range_sequences.get(worker_id)
    if sequence_state is None:
        return sample_time
    previous_sample_time = sequence_state.get("sample_time_s")
    if previous_sample_time is not None:
        sample_time = max(sample_time, previous_sample_time + 1e-4)
    sequence_state["sample_time_s"] = sample_time
    return sample_time


def _metric_velocity_to_logical(velocity_mps):
    """Rotate metric EKF velocity into the frontend's arbitrary anchor frame."""
    vx_mps, vy_mps = velocity_mps
    a, b = ANCHORS[0], ANCHORS[1]
    dx, dy = b["x"] - a["x"], b["y"] - a["y"]
    baseline_units = math.hypot(dx, dy)
    if baseline_units <= 0.0:
        return 0.0, 0.0
    ux, uy = dx / baseline_units, dy / baseline_units
    nx, ny = -uy, ux
    scale = units_per_metre()
    return (ux * vx_mps + nx * vy_mps) * scale, (uy * vx_mps + ny * vy_mps) * scale


def _correct_ranges(raw_d1_m, raw_d2_m):
    """Apply fixed per-link RF offsets to raw *slant* DW3000 ranges."""
    return raw_d1_m + UWB_D1_OFFSET_M, raw_d2_m + UWB_D2_OFFSET_M


def _horizontal_range(slant_range_m, height_delta_m):
    """Convert calibrated slant range to a horizontal 2-D range safely."""
    if not math.isfinite(slant_range_m):
        return float("nan")
    squared = slant_range_m * slant_range_m - height_delta_m * height_delta_m
    # A range shorter than its surveyed vertical separation is physically
    # impossible; return NaN so the normal geometry rejection remains visible.
    return math.sqrt(squared) if squared >= 0.0 else float("nan")


def _horizontal_ranges(slant_d1_m, slant_d2_m):
    return (
        _horizontal_range(slant_d1_m, UWB_D1_HEIGHT_DELTA_M),
        _horizontal_range(slant_d2_m, UWB_D2_HEIGHT_DELTA_M),
    )


def _range_status_values(raw_d1_m, raw_d2_m, slant_d1_m, slant_d2_m, d1_m, d2_m):
    """Keep both measurement and calibration result visible to operators."""
    return {
        "raw_d1_m": round(raw_d1_m, 3),
        "raw_d2_m": round(raw_d2_m, 3),
        "d1_slant_m": round(slant_d1_m, 3),
        "d2_slant_m": round(slant_d2_m, 3),
        "d1_m": round(d1_m, 3) if math.isfinite(d1_m) else None,
        "d2_m": round(d2_m, 3) if math.isfinite(d2_m) else None,
        "d1_offset_m": UWB_D1_OFFSET_M,
        "d2_offset_m": UWB_D2_OFFSET_M,
        "d1_height_delta_m": UWB_D1_HEIGHT_DELTA_M,
        "d2_height_delta_m": UWB_D2_HEIGHT_DELTA_M,
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


def _declared_line_point(along_m):
    """Map a finite physical along-baseline coordinate into the UI frame."""
    baseline_m = ANCHOR_BASELINE_M
    if not math.isfinite(along_m) or baseline_m <= 0.0:
        return None, {"reason": "invalid_anchor_baseline"}

    a, b = ANCHORS[0], ANCHORS[1]
    ax, ay, bx, by = a["x"], a["y"], b["x"], b["y"]
    dx, dy = bx - ax, by - ay
    baseline_units = math.hypot(dx, dy)
    if baseline_units <= 0.0:
        return None, {"reason": "coincident_anchor_coordinates"}
    ux, uy = dx / baseline_units, dy / baseline_units
    scale = units_per_metre()
    point = ax + ux * along_m * scale, ay + uy * along_m * scale
    if not _in_configured_map(point):
        return None, {
            "reason": "outside_configured_map",
            "raw_x": round(point[0], 2),
            "raw_y": round(point[1], 2),
        }
    return point, None


def _solve_declared_line(d1_m, d2_m):
    """Solve the constrained 1-D setup without disguising it as 2-D.

    When the worker is known to be physically *between* the two anchors on
    their connecting line, ideal ranges obey ``d1 + d2 == baseline`` and the
    along-line location is ``d1``.  A short pair is projected onto that
    constraint with an equal-error least-squares estimate:

        x = (baseline + d1 - d2) / 2

    This is intentionally narrower than the normal two-circle solver.  It is
    allowed only after a positive pair was rejected because its sum is too
    short, only inside a bounded residual, and reports a degraded status.  It
    cannot recover lateral position, so a caller must never call it a 2-D UWB
    fix.
    """
    if not _finite_positive(d1_m) or not _finite_positive(d2_m):
        return None, {"reason": "non_positive_or_non_finite_range"}

    baseline_m = ANCHOR_BASELINE_M
    if baseline_m <= 0.0:
        return None, {"reason": "invalid_anchor_baseline"}

    total = d1_m + d2_m
    shortfall_m = baseline_m - total
    if shortfall_m <= TRIANGLE_TOLERANCE_M:
        # Normal circle geometry owns valid and near-tangent samples.  Keeping
        # this mode exclusive avoids silently downgrading a genuine 2-D fix.
        return None, {"reason": "line_fallback_not_needed"}
    if shortfall_m > LINE_FALLBACK_TOLERANCE_M:
        return None, {
            "reason": "ranges_shorter_than_anchor_baseline",
            "triangle_gap_m": round(shortfall_m, 3),
            "line_fallback_rejected": "gap_too_large",
        }

    # A position between anchors requires both ranges to differ by no more
    # than the physical baseline (plus this mode's bounded error allowance).
    range_difference = abs(d1_m - d2_m)
    if range_difference > baseline_m + LINE_FALLBACK_TOLERANCE_M:
        return None, {
            "reason": "ranges_shorter_than_anchor_baseline",
            "triangle_gap_m": round(shortfall_m, 3),
            "line_fallback_rejected": "outside_anchor_segment",
        }

    along_m = (baseline_m + d1_m - d2_m) / 2.0
    if along_m < -LINE_FALLBACK_TOLERANCE_M or along_m > baseline_m + LINE_FALLBACK_TOLERANCE_M:
        return None, {
            "reason": "ranges_shorter_than_anchor_baseline",
            "triangle_gap_m": round(shortfall_m, 3),
            "line_fallback_rejected": "outside_anchor_segment",
        }
    # The tiny tolerated overshoot is only measurement noise at an endpoint;
    # clamp it rather than publishing a point beyond a physical anchor.
    along_m = min(baseline_m, max(0.0, along_m))

    point, point_error = _declared_line_point(along_m)
    if point is None:
        return None, point_error

    return point, {
        "reason": "line_estimate",
        "degraded": True,
        "geometry_mode": "line",
        "geometry_height_m": 0.0,
        "geometry_quality": 0.0,
        "low_geometry": True,
        "branch": "line",
        "branch_source": "declared_line_constraint",
        "branch_ambiguous": True,
        "perpendicular_unobserved": True,
        "geometry_height_assumed": True,
        "line_position_m": round(along_m, 3),
        "triangle_gap_m": round(shortfall_m, 3),
        "line_range_residual_m": round(shortfall_m, 3),
        "line_fallback_tolerance_m": LINE_FALLBACK_TOLERANCE_M,
    }


def dual_anchor_tracking(d1_m, d2_m):
    """Compatibility helper: calibrated two-circle intersection, no filtering."""
    raw_d1_m, raw_d2_m = float(d1_m), float(d2_m)
    slant_d1_m, slant_d2_m = _correct_ranges(raw_d1_m, raw_d2_m)
    d1_m, d2_m = _horizontal_ranges(slant_d1_m, slant_d2_m)
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


def _median_filtered_line_position(worker_id, along_m):
    """Median-filter only declared-line estimates, never normal 2-D ranges."""
    window = _line_range_windows.get(worker_id)
    if window is None:
        window = deque(maxlen=RANGE_FILTER_WINDOW)
        _line_range_windows[worker_id] = window
    window.append(along_m)
    return statistics.median(window)


def _imu_pdr_prior(worker_id, previous, yaw, steps, imu_ok,
                   yaw_game=None, yaw_game_accuracy=None,
                   yaw_game_age_ms=None, imu_epoch=None):
    """Return an IMU-only continuity prior, never a position to publish."""
    diagnostic = {
        "imu_fusion_enabled": UWB_IMU_FUSION,
        "pdr_available": False,
    }
    if not _imu_fusion_ready(worker_id):
        diagnostic["pdr_reason"] = "imu_fusion_not_calibrated"
        return None, diagnostic
    if not imu_ok:
        diagnostic["pdr_reason"] = "imu_unavailable"
        return None, diagnostic
    if previous is None or "steps" not in previous:
        diagnostic["pdr_reason"] = "no_previous_uwb_fix"
        return None, diagnostic

    step_count = _normalise_steps(steps)
    if step_count is None:
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
    heading_deg, heading_source = _resolve_map_heading(
        worker_id, _finite_float(yaw), yaw_game, yaw_game_accuracy,
        yaw_game_age_ms, imu_epoch,
    )
    if heading_deg is None:
        diagnostic["pdr_reason"] = "missing_imu_step_or_yaw"
        return None, diagnostic
    diagnostic["pdr_heading_source"] = heading_source
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


def _apply_historical_range_pair(worker_id, d1_m, d2_m, range_seq, range_age_ms,
                                 range_epoch, range_trusted, nlos_flags):
    """Absorb one back-dated pair from a telemetry batch without publishing.

    EKF mode: the pair updates the tracker at its own back-dated timestamp
    (sequence/epoch replay protection unchanged).  Legacy mode: a solvable
    pair only pre-fills the cross-cycle median window.  Neither path touches
    the published fix status — only the live pair of the packet does that.
    """
    if UWB_2D_FUSION:
        if UWB_LINE_FALLBACK or _allowed_metric_side() is None:
            return
        now = time.monotonic()
        fresh, _reason, reset_for_new_epoch = _fresh_unseen_range_sequence(
            worker_id, range_seq, range_age_ms, range_epoch, historical=True
        )
        tracker = _fusion_tracker(worker_id)
        if reset_for_new_epoch:
            tracker.reset()
            _smooth_state.pop(worker_id, None)
        if not fresh:
            return
        sample_timestamp = _range_sample_timestamp(worker_id, now, range_age_ms)
        # No IMU pairing exists for a backlogged pair; this is a pure range
        # update.  Rejections (gates, NLOS bootstrap) are silently fine here.
        tracker.update_ranges(
            d1_m, d2_m,
            timestamp_s=sample_timestamp,
            range_std_m=UWB_2D_RANGE_STD_M,
            range_trusted=range_trusted,
            nlos_flags=nlos_flags,
        )
        return
    if UWB_LINE_FALLBACK:
        return
    # The median window needs the same replay/staleness protection as the
    # EKF: without it one duplicated HTTP POST (or a spoofed array) refills
    # the window with old ranges and drags the next live fix toward where
    # the worker was minutes ago.
    fresh, _reason, reset_for_new_epoch = _fresh_unseen_range_sequence(
        worker_id, range_seq, range_age_ms, range_epoch, historical=True
    )
    if reset_for_new_epoch:
        # A rebooted tag must not keep pre-reboot ranges in the median window.
        _range_windows.pop(worker_id, None)
    if not fresh:
        return
    if _solve_circles(d1_m, d2_m)[0] is not None:
        _median_filtered_ranges(worker_id, d1_m, d2_m)


def _estimate_position_with_direct_range_ekf(
        worker_id, d1_m, d2_m, range_values, motion,
        pdr_values, yaw_deg, step_count, imu_ok, lin_ax, lin_ay,
        yaw_accuracy, yaw_accuracy_rad, range_seq, range_age_ms,
        range_epoch=None, imu_age_ms=None, range_trusted=None,
        nlos_flags=None, yaw_age_ms=None, linear_accel_age_ms=None,
        imu_epoch=None, linear_accel_accuracy=None,
        yaw_game=None, yaw_game_accuracy=None, yaw_game_age_ms=None):
    """Run the opt-in metric EKF without publishing an IMU-only coordinate."""
    if UWB_LINE_FALLBACK:
        _set_status(
            worker_id, False, "two_d_fusion_requires_line_fallback_disabled",
            **range_values, **pdr_values, **motion["status"],
        )
        return None

    if _allowed_metric_side() is None:
        _set_status(
            worker_id, False, "work_area_point_on_anchor_baseline",
            **range_values, **pdr_values, **motion["status"],
        )
        return None

    now = time.monotonic()
    range_fresh, sequence_reason, reset_for_new_epoch = _fresh_unseen_range_sequence(
        worker_id, range_seq, range_age_ms, range_epoch
    )
    tracker = _fusion_tracker(worker_id)
    if reset_for_new_epoch:
        tracker.reset()
        _smooth_state.pop(worker_id, None)

    # A duplicate/stale snapshot must not be re-used as a radio measurement.
    # Current telemetry cannot pair independently timestamped BNO and UWB
    # events precisely enough to make an IMU-only state transition useful
    # here, so leave the filter untouched until a new atomic range pair arrives.
    if not range_fresh:
        sequence_state = _fusion_range_sequences.get(worker_id, {})
        _set_status(
            worker_id, False, sequence_reason,
            **range_values, **pdr_values, **motion["status"],
            fusion_mode="direct_two_range_ekf",
            fusion_accepted_uwb=False,
            fusion_held=False,
            fusion_reason=sequence_reason,
            fusion_range_sequence=sequence_reason,
            fusion_range_epoch=sequence_state.get("epoch"),
            fusion_range_sample_age_ms=round(_finite_float(range_age_ms), 1)
                if _finite_float(range_age_ms) is not None else None,
            imu_accel_prediction=False,
            imu_accel_reason="waiting_for_fresh_atomic_range_pair",
            imu_heading_calibrated=False,
            imu_zupt_applied=False,
        )
        previous = _smooth_state.get(worker_id, {})
        next_motion = {"at": now, "steps": step_count}
        if motion["gyro_mag"] is not None:
            next_motion["gyro_mag"] = motion["gyro_mag"]
        if "x" in previous and "y" in previous:
            next_motion.update({"x": previous["x"], "y": previous["y"]})
        _smooth_state[worker_id] = next_motion
        return None

    sample_timestamp = _range_sample_timestamp(worker_id, now, range_age_ms)

    if _imu_accel_fusion_ready(worker_id):
        heading, heading_source = _resolve_map_heading(
            worker_id, yaw_deg, yaw_game, yaw_game_accuracy,
            yaw_game_age_ms, imu_epoch,
        )
    else:
        heading, heading_source = None, None
    imu_age = _finite_float(imu_age_ms)
    imu_fresh = imu_age is not None and 0.0 <= imu_age <= UWB_2D_MAX_IMU_AGE_MS
    yaw_age = _finite_float(yaw_age_ms)
    linear_accel_age = _finite_float(linear_accel_age_ms)
    linear_accuracy = _normalise_stability(linear_accel_accuracy)
    imu_pair_fresh = bool(
        yaw_age is not None and linear_accel_age is not None
        and 0.0 <= yaw_age <= UWB_2D_MAX_IMU_AGE_MS
        and 0.0 <= linear_accel_age <= UWB_2D_MAX_IMU_AGE_MS
    )
    if heading_source == "yaw_game_learned":
        # Game RV freshness is already enforced by _resolve_map_heading; the
        # magnetic RotationVector accuracy gates would only starve this
        # magnetometer-free path in exactly the environments it exists for.
        heading_calibrated = bool(
            heading is not None
            and linear_accuracy is not None and linear_accuracy >= 2
            and linear_accel_age is not None
            and 0.0 <= linear_accel_age <= UWB_2D_MAX_IMU_AGE_MS
        )
    else:
        heading_calibrated = bool(
            heading is not None
            and yaw_accuracy is not None and yaw_accuracy >= 2
            and linear_accuracy is not None and linear_accuracy >= 2
            and _yaw_accuracy_degrees(yaw_accuracy_rad) is not None
            and imu_pair_fresh
        )
    body_accel = (_finite_float(lin_ax), _finite_float(lin_ay))
    if body_accel[0] is None or body_accel[1] is None:
        body_accel = None
    # The magnetic yaw-accuracy estimate does not describe the learned Game RV
    # mapping; passing it would let a disturbed magnetometer veto a heading it
    # never produced.
    heading_accuracy_deg = (
        None if heading_source == "yaw_game_learned"
        else _yaw_accuracy_degrees(yaw_accuracy_rad)
    )
    # A turning helmet or low heading confidence must not inject a potentially
    # misaligned body acceleration into map coordinates. The filter still uses
    # its constant-velocity model and BNO stationary ZUPT in that state.
    accel_trusted = bool(
        heading_calibrated
        and not motion["turning"]
        and body_accel is not None
    )
    range_std = UWB_2D_RANGE_STD_M * (1.5 if motion["turning"] else 1.0)
    result = tracker.step(
        timestamp_s=sample_timestamp,
        d1_m=d1_m,
        d2_m=d2_m,
        body_linear_accel_mps2=body_accel,
        map_heading_deg=heading,
        imu_ok=bool(imu_ok),
        heading_calibrated=heading_calibrated,
        heading_accuracy_deg=heading_accuracy_deg,
        acceleration_trusted=accel_trusted,
        stationary=motion["stationary"],
        stationary_trusted=motion["stability"] in {1, 2} and imu_fresh,
        range_std_m=range_std,
        range_trusted=range_trusted,
        nlos_flags=nlos_flags,
    )

    sequence_state = _fusion_range_sequences.get(worker_id, {})
    filter_values = {
        "fusion_mode": "direct_two_range_ekf",
        "fusion_accepted_uwb": result.accepted_uwb,
        "fusion_held": result.held,
        "fusion_reason": result.reason,
        "fusion_range_sequence": sequence_reason,
        "fusion_range_sample_age_ms": round(_finite_float(range_age_ms), 1)
            if _finite_float(range_age_ms) is not None else None,
        # Use the established source identity, rather than dropping it from
        # diagnostics if one otherwise-fresh packet omitted the optional field.
        "fusion_range_epoch": sequence_state.get("epoch"),
        "imu_epoch": _range_epoch_token(imu_epoch),
        "fusion_nis": round(result.nis, 3) if result.nis is not None else None,
        "fusion_uwb_age_ms": round(result.uwb_age_s * 1000) if result.uwb_age_s is not None else None,
        "fusion_velocity_mps": [round(value, 3) for value in result.velocity_mps]
            if result.velocity_mps is not None else None,
        "imu_accel_prediction": bool(result.imu_used),
        "imu_accel_reason": result.imu_reason,
        "imu_heading_calibrated": heading_calibrated,
        "imu_heading_source": heading_source,
        "yaw_offset_learner": heading_offset.diagnostics(worker_id),
        "imu_sample_fresh": imu_fresh,
        "imu_pair_fresh": imu_pair_fresh,
        "imu_yaw_age_ms": round(yaw_age, 1) if yaw_age is not None else None,
        "imu_linear_accel_age_ms": round(linear_accel_age, 1)
            if linear_accel_age is not None else None,
        "imu_linear_accel_accuracy": linear_accuracy,
        "imu_heading_accuracy_deg": round(heading_accuracy_deg, 2)
            if heading_accuracy_deg is not None else None,
        "imu_zupt_applied": result.zupt_applied,
        "fusion_side_constrained": bool(result.details.get("side_constrained")),
        # NLOS never vetoes an update any more (flag, don't drop), so the
        # suspicion must surface here or a fix built from flagged ranges
        # would present as clean on the dashboard.
        "nlos_suspected": bool(result.nlos_suspected),
        "nlos_flags": result.details.get("nlos_flags"),
    }
    if result.geometry_height_m is not None:
        filter_values["geometry_height_m"] = round(result.geometry_height_m, 3)
        filter_values["geometry_quality"] = round(
            min(1.0, result.geometry_height_m / max(ANCHOR_BASELINE_M * 0.5, 0.001)), 3
        )
    filter_values["low_geometry"] = bool(result.low_geometry)

    if not result.accepted_uwb or result.position_m is None:
        _set_status(
            worker_id, False,
            result.reason,
            **range_values, **pdr_values, **motion["status"], **filter_values,
        )
        # Preserve just enough BNO history for turn/stationary gating on the
        # next packet. This is not a published coordinate.
        previous = _smooth_state.get(worker_id, {})
        next_motion = {"at": now, "steps": step_count}
        if motion["gyro_mag"] is not None:
            next_motion["gyro_mag"] = motion["gyro_mag"]
        if "x" in previous and "y" in previous:
            next_motion.update({"x": previous["x"], "y": previous["y"]})
        _smooth_state[worker_id] = next_motion
        return None

    logical = _metric_to_logical(result.position_m)
    if logical is None or not _in_configured_map(logical):
        # The direct update already mutated the filter. A geometrically valid
        # point outside this deployment's map must not become the prior for a
        # later in-map packet, so reset rather than retaining a poisoned state.
        tracker.reset()
        _smooth_state.pop(worker_id, None)
        _set_status(
            worker_id, False, "ekf_outside_configured_map",
            **range_values, **pdr_values, **motion["status"], **filter_values,
        )
        return None

    x, y = logical
    velocity_mps = result.velocity_mps or (0.0, 0.0)
    velocity_units = _metric_velocity_to_logical(velocity_mps)
    next_state = {
        "x": x,
        "y": y,
        "vx": velocity_units[0],
        "vy": velocity_units[1],
        "at": now,
    }
    if step_count is not None:
        next_state["steps"] = step_count
    if motion["gyro_mag"] is not None:
        next_state["gyro_mag"] = motion["gyro_mag"]
    _smooth_state[worker_id] = next_state

    _set_status(
        worker_id, True, "range_ekf",
        **range_values,
        yaw_deg=round(yaw_deg, 1) if yaw_deg is not None else None,
        **pdr_values, **motion["status"], **filter_values,
        geometry_mode="two_anchor_ekf",
        branch="ekf_allowed_side",
        branch_source="direct_range_ekf",
        branch_ambiguous=bool(result.low_geometry),
        # An inflated-std NLOS update converges toward the biased range over
        # time; the coordinate is usable but must display as degraded.
        degraded=bool(result.nlos_suspected),
    )
    if not result.nlos_suspected:
        # A shadowed link drags the track toward its bias; such travel
        # directions must not teach the yaw learner.
        heading_offset.observe_fix(
            worker_id,
            t_s=now,
            x_units=x,
            y_units=y,
            units_per_metre=units_per_metre(),
            yaw_game_deg=_finite_float(yaw_game),
            yaw_game_age_ms=_finite_float(yaw_game_age_ms),
            imu_epoch=_imu_epoch_key(imu_epoch),
        )
    return round(x, 2), round(y, 2)


def estimate_position(worker_id, d1, d2, yaw=0.0, steps=None, imu_ok=False,
                      gyro_x=None, gyro_y=None, gyro_z=None,
                      linear_accel=None, stability=None, yaw_accuracy=None,
                      gyro_accuracy=None, linear_accel_x=None,
                      linear_accel_y=None, yaw_accuracy_rad=None,
                      range_seq=None, range_age_ms=None, range_epoch=None,
                      imu_age_ms=None, range_trusted=None, nlos_flags=None,
                      yaw_age_ms=None, linear_accel_age_ms=None,
                      imu_epoch=None, linear_accel_accuracy=None,
                      yaw_game=None, yaw_game_accuracy=None,
                      yaw_game_age_ms=None, historical=False):
    """
    Full live pipeline. Invalid geometry never creates a location: the caller
    keeps the last coordinate and gets a machine-readable `uwb` status instead.
    When explicitly calibrated, yaw + step count can choose between the two
    real UWB circle intersections. In direct-EKF mode the two calibrated
    ranges update the metric state atomically; BNO data can only predict or
    damp that state and can never create a published location by itself.
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

    slant_d1_m, slant_d2_m = _correct_ranges(raw_d1, raw_d2)
    d1_m, d2_m = _horizontal_ranges(slant_d1_m, slant_d2_m)
    range_values = _range_status_values(
        raw_d1, raw_d2, slant_d1_m, slant_d2_m, d1_m, d2_m
    )

    if historical:
        _apply_historical_range_pair(
            worker_id, d1_m, d2_m, range_seq, range_age_ms,
            range_epoch, range_trusted, nlos_flags,
        )
        return None

    if UWB_2D_FUSION:
        # The legacy step/stride prior chooses a circle mirror only. The
        # direct filter already has an explicit permitted side and consumes
        # each range pair atomically, so do not let a separate PDR path imply
        # that it produced the coordinate.
        pdr_values = {
            "imu_fusion_enabled": UWB_IMU_FUSION,
            "pdr_available": False,
            "pdr_reason": "not_used_in_direct_range_ekf",
        }
        return _estimate_position_with_direct_range_ekf(
            worker_id, d1_m, d2_m, range_values, motion, pdr_values,
            yaw_deg, step_count, bool(imu_ok), linear_accel_x,
            linear_accel_y, yaw_accuracy, yaw_accuracy_rad,
            range_seq, range_age_ms, range_epoch, imu_age_ms,
            range_trusted, nlos_flags, yaw_age_ms,
            linear_accel_age_ms, imu_epoch, linear_accel_accuracy,
            yaw_game, yaw_game_accuracy, yaw_game_age_ms,
        )

    pdr_prior, pdr_values = _imu_pdr_prior(
        worker_id, previous, yaw_deg, step_count, bool(imu_ok),
        yaw_game=yaw_game, yaw_game_accuracy=yaw_game_accuracy,
        yaw_game_age_ms=yaw_game_age_ms, imu_epoch=imu_epoch,
    )

    # Validate this actual *calibrated* ranging cycle before it can pollute the
    # median.  A raw DW3000 ToF estimate can be negative near zero until its
    # fixed link offset is applied; only the corrected physical range belongs
    # in the triangle solver.
    raw_fix, raw_quality = _solve_circles(d1_m, d2_m)
    line_mode = False
    if (raw_fix is None and UWB_LINE_FALLBACK and
            raw_quality.get("reason") == "ranges_shorter_than_anchor_baseline"):
        # This is intentionally an opt-in commissioning/degraded path.  It
        # accepts only a bounded shortfall for a worker declared to travel on
        # the A1-A2 line; it does not turn arbitrary bad ranges into a point.
        line_fix, line_quality = _solve_declared_line(d1_m, d2_m)
        if line_fix is not None:
            raw_fix, raw_quality = line_fix, line_quality
            line_mode = True
        else:
            raw_quality = line_quality

    if raw_fix is None:
        _set_status(worker_id, False, raw_quality["reason"], **range_values,
                    **pdr_values, **motion["status"],
                    **{k: v for k, v in raw_quality.items() if k != "reason"})
        return None

    if line_mode:
        # Filter the physically meaningful 1-D coordinate itself.  Medians of
        # d1 and d2 from different moments can form a range pair never
        # observed by the radio while the tag is walking.
        filtered_line_position = _median_filtered_line_position(
            worker_id, raw_quality["line_position_m"]
        )
        fix, line_error = _declared_line_point(filtered_line_position)
        if fix is None:
            _set_status(worker_id, False, line_error["reason"], **range_values,
                        **pdr_values, **motion["status"],
                        **{k: v for k, v in line_error.items() if k != "reason"})
            return None
        quality = dict(raw_quality)
        quality["filtered_line_position_m"] = round(filtered_line_position, 3)
        filtered_d1 = filtered_d2 = None
    else:
        filtered_d1, filtered_d2 = _median_filtered_ranges(worker_id, d1_m, d2_m)
        fix, quality = _solve_circles(filtered_d1, filtered_d2, pdr_prior=pdr_prior)
        if fix is None:
            _set_status(worker_id, False, quality["reason"], **range_values,
                        **pdr_values, **motion["status"],
                        filtered_d1_m=round(filtered_d1, 3), filtered_d2_m=round(filtered_d2, 3),
                        **{k: v for k, v in quality.items() if k != "reason"})
            return None

    x_raw, y_raw = fix
    line_frame = None
    if line_mode:
        a, b = ANCHORS[0], ANCHORS[1]
        ax, ay = a["x"], a["y"]
        dx, dy = b["x"] - ax, b["y"] - ay
        baseline_units = math.hypot(dx, dy)
        if baseline_units <= 0.0:
            _set_status(worker_id, False, "coincident_anchor_coordinates", **range_values,
                        **pdr_values, **motion["status"])
            return None
        # (u) is the allowed direction; (n) is intentionally unobserved in
        # degraded mode.  Projecting the filter state onto u prevents an old
        # 2-D velocity from drifting a 1-D estimate off the anchor line.
        ux, uy = dx / baseline_units, dy / baseline_units
        line_frame = (ax, ay, ux, uy, -uy, ux)

    now = time.monotonic()
    prev = _smooth_state.get(worker_id)
    if prev is None:
        x_smooth, y_smooth = x_raw, y_raw
        vx, vy = 0.0, 0.0
        smoothing_alpha = LOW_GEOMETRY_ALPHA if quality.get("low_geometry") else ALPHA
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

        if line_frame is not None:
            ax, ay, ux, uy, _, _ = line_frame
            # The predecessor may have been a normal 2-D fix. Its perpendicular
            # component is not valid input to a declared-line calculation.
            along_pred = (pred_x - ax) * ux + (pred_y - ay) * uy
            pred_x, pred_y = ax + ux * along_pred, ay + uy * along_pred
            along_velocity = prior_vx * ux + prior_vy * uy
            prior_vx, prior_vy = ux * along_velocity, uy * along_velocity

        innovation_x = x_raw - pred_x
        innovation_y = y_raw - pred_y
        if line_frame is not None:
            # Keep only the innovation that lies along the declared physical
            # line.  The normal component is unmeasured, not a zero reading.
            _, _, _, _, nx, ny = line_frame
            normal_innovation = innovation_x * nx + innovation_y * ny
            innovation_x -= nx * normal_innovation
            innovation_y -= ny * normal_innovation
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
        if line_frame is not None:
            ax, ay, ux, uy, _, _ = line_frame
            along_smooth = (x_smooth - ax) * ux + (y_smooth - ay) * uy
            x_smooth, y_smooth = ax + ux * along_smooth, ay + uy * along_smooth
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
            if line_frame is not None:
                _, _, ux, uy, _, _ = line_frame
                along_velocity = vx * ux + vy * uy
                vx, vy = ux * along_velocity, uy * along_velocity

    next_state = {"x": x_smooth, "y": y_smooth, "vx": vx, "vy": vy, "at": now}
    if step_count is not None:
        next_state["steps"] = step_count
    if motion["gyro_mag"] is not None:
        next_state["gyro_mag"] = motion["gyro_mag"]
    _smooth_state[worker_id] = next_state
    filtered_values = ({
        "filtered_d1_m": round(filtered_d1, 3),
        "filtered_d2_m": round(filtered_d2, 3),
    } if filtered_d1 is not None else {})
    _set_status(worker_id, True, quality["reason"], **range_values, **filtered_values,
                yaw_deg=round(yaw_deg, 1) if yaw_deg is not None else None,
                smoothing_alpha=round(smoothing_alpha, 3),
                **pdr_values, **motion["status"],
                **{k: v for k, v in quality.items() if k != "reason"})
    try:
        nlos_any = any(bool(flag) for flag in nlos_flags) if nlos_flags is not None else False
    except TypeError:
        nlos_any = bool(nlos_flags)
    if not line_mode and not nlos_any:
        # A degraded 1-D estimate has no observed perpendicular axis, and an
        # NLOS-suspected pair drags the fix toward its bias — neither may
        # teach the yaw learner a track heading it never measured cleanly.
        heading_offset.observe_fix(
            worker_id,
            t_s=now,
            x_units=x_smooth,
            y_units=y_smooth,
            units_per_metre=units_per_metre(),
            yaw_game_deg=_finite_float(yaw_game),
            yaw_game_age_ms=_finite_float(yaw_game_age_ms),
            imu_epoch=_imu_epoch_key(imu_epoch),
        )
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
