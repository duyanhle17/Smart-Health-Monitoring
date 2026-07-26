"""Safe two-anchor UWB + IMU tracker.

This module deliberately keeps the estimator separate from the HTTP/API layer.
It is intended to be fed with *calibrated metre* ranges and BNO08x linear
acceleration.  The filter has a small state ``[x, y, vx, vy]`` and performs a
direct EKF update against the two range observations; it does **not** first
triangulate a point and then smooth that point.

Two anchors cannot resolve the mirror ambiguity by themselves.  A caller must
therefore declare the permitted side of the A1->A2 line when bootstrapping a
new tracker.  The BNO08x may predict the state between accepted UWB updates,
but it never bootstraps or extends the UWB freshness window.  Consequently an
IMU-only trajectory is never returned as a publishable location.

No third-party numerical package is used here so that the safety checks and
matrix operations are easy to audit in the deployed backend image.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import math
from typing import Any, Iterable, Mapping, Optional, Sequence, Tuple


Point = Tuple[float, float]
Vector2 = Tuple[float, float]
Matrix4 = list[list[float]]


def _finite_float(value: Any) -> Optional[float]:
    """Return a finite float, or ``None`` for malformed telemetry."""
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def _finite_pair(value: Any) -> Optional[Vector2]:
    """Read exactly two finite values without accepting an acceleration norm."""
    if isinstance(value, (str, bytes)):
        return None
    try:
        x, y = value
    except (TypeError, ValueError):
        return None
    x = _finite_float(x)
    y = _finite_float(y)
    return (x, y) if x is not None and y is not None else None


def _identity(size: int) -> list[list[float]]:
    return [[1.0 if row == column else 0.0 for column in range(size)] for row in range(size)]


def _zeros(rows: int, columns: int) -> list[list[float]]:
    return [[0.0 for _ in range(columns)] for _ in range(rows)]


def _transpose(matrix: Sequence[Sequence[float]]) -> list[list[float]]:
    return [list(column) for column in zip(*matrix)]


def _matmul(left: Sequence[Sequence[float]], right: Sequence[Sequence[float]]) -> list[list[float]]:
    """Small, explicit matrix multiplication used only for 2x/4x EKF math."""
    if not left or not right:
        return []
    right_columns = len(right[0])
    result = _zeros(len(left), right_columns)
    for row, values in enumerate(left):
        for inner, left_value in enumerate(values):
            if left_value == 0.0:
                continue
            for column in range(right_columns):
                result[row][column] += left_value * right[inner][column]
    return result


def _add(left: Sequence[Sequence[float]], right: Sequence[Sequence[float]]) -> list[list[float]]:
    return [[a + b for a, b in zip(left_row, right_row)] for left_row, right_row in zip(left, right)]


def _subtract(left: Sequence[Sequence[float]], right: Sequence[Sequence[float]]) -> list[list[float]]:
    return [[a - b for a, b in zip(left_row, right_row)] for left_row, right_row in zip(left, right)]


def _symmetrise_and_floor(matrix: Matrix4, floor: float = 1e-9) -> Matrix4:
    """Keep covariance symmetric positive on its diagonal after round-off."""
    size = len(matrix)
    result = _zeros(size, size)
    for row in range(size):
        for column in range(size):
            result[row][column] = 0.5 * (matrix[row][column] + matrix[column][row])
        result[row][row] = max(floor, result[row][row])
    return result


def _inverse_2x2(matrix: Sequence[Sequence[float]]) -> Optional[list[list[float]]]:
    determinant = matrix[0][0] * matrix[1][1] - matrix[0][1] * matrix[1][0]
    if not math.isfinite(determinant) or determinant <= 1e-12:
        return None
    inverse_determinant = 1.0 / determinant
    return [
        [matrix[1][1] * inverse_determinant, -matrix[0][1] * inverse_determinant],
        [-matrix[1][0] * inverse_determinant, matrix[0][0] * inverse_determinant],
    ]


def _normalise_flag_pair(value: Any, *, default: bool) -> Optional[Tuple[bool, bool]]:
    """Normalise telemetry quality flags while rejecting malformed sequences."""
    if value is None:
        return default, default
    if isinstance(value, bool):
        return value, value
    if isinstance(value, (str, bytes)):
        return None
    try:
        first, second = value
    except (TypeError, ValueError):
        return None
    return bool(first), bool(second)


def _normalise_range_std(value: Any, default: float, minimum: float) -> Optional[Tuple[float, float]]:
    if value is None:
        return default, default
    if isinstance(value, bool):
        return None
    scalar = _finite_float(value)
    if scalar is not None:
        if scalar <= 0.0:
            return None
        return max(minimum, scalar), max(minimum, scalar)
    pair = _finite_pair(value)
    if pair is None:
        return None
    if pair[0] <= 0.0 or pair[1] <= 0.0:
        return None
    return max(minimum, pair[0]), max(minimum, pair[1])


@dataclass(frozen=True)
class UwbImuFilterConfig:
    """Tunable estimator safeguards, expressed in SI units.

    Defaults intentionally favour a stable, safety-labelled track over a fast
    response to an isolated range spike.  ``hold_seconds`` is a presentation
    safety boundary: prediction and ZUPT do not reset it.
    """

    use_imu: bool = True
    range_std_m: float = 0.18
    minimum_range_std_m: float = 0.03
    # Std substituted for a link the firmware flags as NLOS.  The flagged link
    # still updates the filter (flag, don't drop): a body-worn tag shadows one
    # anchor for much of a shift, and rejecting the whole pair on the flag
    # means losing the fix exactly while the worker moves.  Inflation slows
    # convergence but does NOT bound a persistent bias — a link flagged for
    # many consecutive updates still pulls the state toward its biased range,
    # which is why the engine publishes such fixes as degraded.
    nlos_range_std_m: float = 0.60
    initial_position_std_m: float = 1.5
    initial_velocity_std_mps: float = 1.0
    process_accel_std_mps2: float = 1.2
    imu_accel_std_mps2: float = 0.45
    max_imu_accel_mps2: float = 5.0
    max_speed_mps: float = 4.0
    max_prediction_dt_s: float = 0.50
    # 99% chi-square gate for a two-dimensional range innovation.
    innovation_gate_chi2: float = 9.21
    max_range_residual_m: float = 2.0
    geometry_tolerance_m: float = 0.08
    min_geometry_height_m: float = 0.15
    reject_low_geometry_bootstrap: bool = True
    reject_low_geometry_updates: bool = False
    hold_seconds: float = 1.5
    zupt_velocity_std_mps: float = 0.06
    max_heading_accuracy_deg: float = 20.0


@dataclass(frozen=True)
class FilterResult:
    """A serialisable result for one prediction, update, or hold decision."""

    position_m: Optional[Point]
    velocity_mps: Optional[Vector2]
    covariance: Optional[Tuple[Tuple[float, ...], ...]]
    valid: bool
    accepted_uwb: bool
    held: bool
    reason: str
    timestamp_s: Optional[float]
    uwb_age_s: Optional[float]
    nis: Optional[float] = None
    geometry_height_m: Optional[float] = None
    low_geometry: bool = False
    nlos_suspected: bool = False
    imu_used: bool = False
    imu_reason: Optional[str] = None
    zupt_applied: bool = False
    details: Mapping[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        """Return JSON-friendly diagnostics without exposing mutable state."""
        return {
            "position_m": list(self.position_m) if self.position_m is not None else None,
            "velocity_mps": list(self.velocity_mps) if self.velocity_mps is not None else None,
            "covariance": [list(row) for row in self.covariance] if self.covariance is not None else None,
            "valid": self.valid,
            "accepted_uwb": self.accepted_uwb,
            "held": self.held,
            "reason": self.reason,
            "timestamp_s": self.timestamp_s,
            "uwb_age_s": self.uwb_age_s,
            "nis": self.nis,
            "geometry_height_m": self.geometry_height_m,
            "low_geometry": self.low_geometry,
            "nlos_suspected": self.nlos_suspected,
            "imu_used": self.imu_used,
            "imu_reason": self.imu_reason,
            "zupt_applied": self.zupt_applied,
            "details": dict(self.details),
        }


class UwbImuFilter:
    """EKF-style 2-D range tracker for exactly two known anchors.

    Parameters
    ----------
    anchors_m:
        Exactly two ``(x, y)`` positions in metres.  Their order is A1 then
        A2 and matches the order of ``d1_m`` and ``d2_m``.
    allowed_side:
        ``+1`` or ``-1`` selecting the declared working side of A1->A2 for
        initial UWB bootstrap.  It is required: with only two anchors there is
        no safe way to choose a mirror intersection automatically.
    config:
        :class:`UwbImuFilterConfig` overrides.

    Heading convention used by :meth:`predict`: after commissioning, a map
    heading of 0 degrees points along +map-x and +90 points along +map-y.  The
    caller must pass horizontal BNO body accelerations in the sensor/body x-y
    plane, with body +x aligned to the yaw reference used at calibration.
    """

    def __init__(
        self,
        anchors_m: Sequence[Sequence[float]],
        *,
        allowed_side: int,
        config: Optional[UwbImuFilterConfig] = None,
    ) -> None:
        if len(anchors_m) != 2:
            raise ValueError("exactly two anchors are required")
        anchor_1 = _finite_pair(anchors_m[0])
        anchor_2 = _finite_pair(anchors_m[1])
        if anchor_1 is None or anchor_2 is None:
            raise ValueError("anchor coordinates must be finite (x, y) pairs")
        baseline = math.hypot(anchor_2[0] - anchor_1[0], anchor_2[1] - anchor_1[1])
        if baseline <= 1e-6:
            raise ValueError("anchor coordinates must not coincide")
        if allowed_side not in (-1, 1):
            raise ValueError("allowed_side must be +1 or -1 for two-anchor bootstrap")

        self.anchors_m: Tuple[Point, Point] = (anchor_1, anchor_2)
        self.allowed_side = int(allowed_side)
        self.config = config or UwbImuFilterConfig()
        self._validate_config()
        self._baseline_m = baseline
        self._state: Optional[list[float]] = None
        self._covariance: Optional[Matrix4] = None
        self._last_timestamp_s: Optional[float] = None
        self._last_accepted_uwb_s: Optional[float] = None
        self._last_imu_diagnostic: dict[str, Any] = {
            "imu_used": False,
            "imu_reason": "not_predicted",
        }
        self._last_update_diagnostic: dict[str, Any] = {}

    def _validate_config(self) -> None:
        cfg = self.config
        positive = (
            "range_std_m", "minimum_range_std_m", "initial_position_std_m",
            "initial_velocity_std_mps", "process_accel_std_mps2",
            "imu_accel_std_mps2", "max_imu_accel_mps2", "max_speed_mps",
            "max_prediction_dt_s", "innovation_gate_chi2", "max_range_residual_m",
            "geometry_tolerance_m", "min_geometry_height_m", "hold_seconds",
            "zupt_velocity_std_mps", "max_heading_accuracy_deg",
        )
        for name in positive:
            value = getattr(cfg, name)
            if not math.isfinite(value) or value <= 0.0:
                raise ValueError(f"{name} must be a positive finite number")

    @property
    def initialized(self) -> bool:
        """Whether one accepted two-range UWB update has initialized state."""
        return self._state is not None and self._covariance is not None

    @property
    def last_accepted_uwb_s(self) -> Optional[float]:
        return self._last_accepted_uwb_s

    def reset(self) -> None:
        """Forget all state; subsequent IMU-only packets remain unpublished."""
        self._state = None
        self._covariance = None
        self._last_timestamp_s = None
        self._last_accepted_uwb_s = None
        self._last_imu_diagnostic = {"imu_used": False, "imu_reason": "reset"}
        self._last_update_diagnostic = {}

    def state_vector(self) -> Optional[Tuple[float, float, float, float]]:
        """Immutable state snapshot for tests/diagnostics, not a publish API."""
        return tuple(self._state) if self._state is not None else None

    def covariance_matrix(self) -> Optional[Tuple[Tuple[float, ...], ...]]:
        if self._covariance is None:
            return None
        return tuple(tuple(value for value in row) for row in self._covariance)

    def _timestamp(self, timestamp_s: Any) -> Optional[float]:
        return _finite_float(timestamp_s)

    def _covariance_snapshot(self) -> Optional[Tuple[Tuple[float, ...], ...]]:
        return self.covariance_matrix()

    def _output(self, *, now_s: Optional[float], accepted_uwb: bool, reason: str,
                nis: Optional[float] = None, geometry_height_m: Optional[float] = None,
                low_geometry: bool = False, nlos_suspected: bool = False,
                imu_used: Optional[bool] = None, imu_reason: Optional[str] = None,
                zupt_applied: bool = False, details: Optional[Mapping[str, Any]] = None) -> FilterResult:
        """Build a result while enforcing the UWB freshness/hold boundary."""
        now = now_s if now_s is not None else self._last_timestamp_s
        age: Optional[float] = None
        if now is not None and self._last_accepted_uwb_s is not None:
            age = max(0.0, now - self._last_accepted_uwb_s)

        valid = (
            self._state is not None
            and age is not None
            and age <= self.config.hold_seconds
        )
        held = valid and not accepted_uwb
        if valid:
            position: Optional[Point] = (self._state[0], self._state[1])
            velocity: Optional[Vector2] = (self._state[2], self._state[3])
            covariance = self._covariance_snapshot()
        else:
            position = None
            velocity = None
            covariance = None
            # Preserve a concrete rejected-UWB diagnosis (for example NLOS or
            # bootstrap_low_geometry) even before the first good fix.  Only
            # generic request-for-output paths are rewritten to the clearer
            # "no accepted UWB" state.
            if self._state is None and reason in {
                "uwb_hold", "no_uwb_measurement", "zupt", "not_stationary",
            }:
                reason = "no_accepted_uwb_fix"
            elif age is not None and age > self.config.hold_seconds:
                reason = "uwb_hold_expired"

        if imu_used is None:
            imu_used = bool(self._last_imu_diagnostic.get("imu_used"))
        if imu_reason is None:
            imu_reason = self._last_imu_diagnostic.get("imu_reason")
        merged_details = dict(self._last_update_diagnostic)
        if details:
            merged_details.update(details)
        return FilterResult(
            position_m=position,
            velocity_mps=velocity,
            covariance=covariance,
            valid=valid,
            accepted_uwb=accepted_uwb,
            held=held,
            reason=reason,
            timestamp_s=now,
            uwb_age_s=age,
            nis=nis,
            geometry_height_m=geometry_height_m,
            low_geometry=low_geometry,
            nlos_suspected=nlos_suspected,
            imu_used=bool(imu_used),
            imu_reason=imu_reason,
            zupt_applied=zupt_applied,
            details=merged_details,
        )

    def _advance(self, timestamp_s: float, acceleration_map_mps2: Optional[Vector2],
                 process_std_mps2: float) -> dict[str, Any]:
        """Apply the kinematic prediction and process covariance once."""
        if self._last_timestamp_s is None:
            self._last_timestamp_s = timestamp_s
            return {"dt_s": 0.0, "time_gap_capped": False}

        raw_dt = timestamp_s - self._last_timestamp_s
        if raw_dt <= 0.0:
            # Out-of-order packets cannot safely roll the state backwards.
            return {"dt_s": 0.0, "time_gap_capped": False, "out_of_order": raw_dt < 0.0}

        dt = min(raw_dt, self.config.max_prediction_dt_s)
        capped = raw_dt > dt
        self._last_timestamp_s = timestamp_s
        if self._state is None or self._covariance is None:
            return {"dt_s": dt, "time_gap_capped": capped}

        previous_state = list(self._state)
        previous_covariance = self._covariance
        ax, ay = acceleration_map_mps2 if acceleration_map_mps2 is not None else (0.0, 0.0)
        x, y, vx, vy = self._state
        x += vx * dt + 0.5 * ax * dt * dt
        y += vy * dt + 0.5 * ay * dt * dt
        vx += ax * dt
        vy += ay * dt
        speed = math.hypot(vx, vy)
        speed_limited = speed > self.config.max_speed_mps
        if speed_limited:
            scale = self.config.max_speed_mps / speed
            vx *= scale
            vy *= scale
        self._state = [x, y, vx, vy]

        f = [
            [1.0, 0.0, dt, 0.0],
            [0.0, 1.0, 0.0, dt],
            [0.0, 0.0, 1.0, 0.0],
            [0.0, 0.0, 0.0, 1.0],
        ]
        q = process_std_mps2 * process_std_mps2
        dt2, dt3, dt4 = dt * dt, dt * dt * dt, dt * dt * dt * dt
        process_covariance = [
            [0.25 * dt4 * q, 0.0, 0.5 * dt3 * q, 0.0],
            [0.0, 0.25 * dt4 * q, 0.0, 0.5 * dt3 * q],
            [0.5 * dt3 * q, 0.0, dt2 * q, 0.0],
            [0.0, 0.5 * dt3 * q, 0.0, dt2 * q],
        ]
        covariance = _add(_matmul(_matmul(f, self._covariance), _transpose(f)), process_covariance)

        # If telemetry skipped a large interval, acknowledge that unmodelled
        # motion could be materially larger than the capped propagation.
        if capped:
            skipped = raw_dt - dt
            extra_position_variance = (self.config.process_accel_std_mps2 * skipped * skipped) ** 2
            covariance[0][0] += extra_position_variance
            covariance[1][1] += extra_position_variance
        candidate_covariance = _symmetrise_and_floor(covariance)
        if not self._on_allowed_side((x, y)):
            # With exactly two anchors, a trajectory crossing the baseline is
            # indistinguishable from its mirror in range space.  The declared
            # work side is an invariant, not merely a bootstrap hint.  Do not
            # clamp to the baseline (which would manufacture a lateral value);
            # retain the last legitimate state until real geometry resolves it.
            self._state = previous_state
            self._covariance = previous_covariance
            return {
                "dt_s": dt,
                "time_gap_capped": capped,
                "speed_limited": speed_limited,
                "side_constrained": True,
            }
        self._covariance = candidate_covariance
        return {"dt_s": dt, "time_gap_capped": capped, "speed_limited": speed_limited}

    def predict(
        self,
        *,
        timestamp_s: Any,
        body_linear_accel_mps2: Any = None,
        map_heading_deg: Any = None,
        imu_ok: bool = False,
        heading_calibrated: bool = False,
        heading_accuracy_deg: Any = None,
        acceleration_trusted: bool = True,
    ) -> Mapping[str, Any]:
        """Predict from a BNO08x acceleration sample when it is trusted.

        Invalid/disabled IMU input falls back to a constant-velocity model; it
        does not fail an otherwise good UWB track.  A scalar ``lin_acc`` is
        intentionally not accepted: directionless acceleration cannot be used
        safely for a 2-D prediction.
        """
        timestamp = self._timestamp(timestamp_s)
        if timestamp is None:
            self._last_imu_diagnostic = {"imu_used": False, "imu_reason": "invalid_timestamp"}
            return dict(self._last_imu_diagnostic)

        acceleration_map: Optional[Vector2] = None
        imu_reason: Optional[str] = None
        if not self.config.use_imu:
            imu_reason = "imu_disabled"
        elif not imu_ok:
            imu_reason = "imu_unavailable"
        elif not acceleration_trusted:
            imu_reason = "acceleration_untrusted"
        elif not heading_calibrated:
            imu_reason = "map_heading_uncalibrated"
        else:
            body_acceleration = _finite_pair(body_linear_accel_mps2)
            heading = _finite_float(map_heading_deg)
            accuracy = _finite_float(heading_accuracy_deg)
            if body_acceleration is None:
                imu_reason = "invalid_body_acceleration"
            elif heading is None:
                imu_reason = "invalid_map_heading"
            elif accuracy is not None and accuracy > self.config.max_heading_accuracy_deg:
                imu_reason = "heading_accuracy_too_low"
            elif math.hypot(*body_acceleration) > self.config.max_imu_accel_mps2:
                imu_reason = "acceleration_out_of_bounds"
            else:
                radians = math.radians(heading)
                cos_heading = math.cos(radians)
                sin_heading = math.sin(radians)
                body_x, body_y = body_acceleration
                # Body +x forward / +y left, map heading CCW from +map-x.
                acceleration_map = (
                    body_x * cos_heading - body_y * sin_heading,
                    body_x * sin_heading + body_y * cos_heading,
                )

        diagnostic = self._advance(
            timestamp,
            acceleration_map,
            self.config.imu_accel_std_mps2 if acceleration_map is not None else self.config.process_accel_std_mps2,
        )
        diagnostic.update({
            "imu_used": acceleration_map is not None,
            "imu_reason": None if acceleration_map is not None else imu_reason,
        })
        if acceleration_map is not None:
            diagnostic["acceleration_map_mps2"] = acceleration_map
        self._last_imu_diagnostic = diagnostic
        return dict(diagnostic)

    def _geometry(self, d1_m: float, d2_m: float) -> tuple[bool, Optional[float], bool, str]:
        """Validate two physical ranges without manufacturing an intersection."""
        if d1_m <= 0.0 or d2_m <= 0.0:
            return False, None, False, "non_positive_range"
        total = d1_m + d2_m
        difference = abs(d1_m - d2_m)
        if total < self._baseline_m - self.config.geometry_tolerance_m:
            return False, None, False, "ranges_shorter_than_baseline"
        if difference > self._baseline_m + self.config.geometry_tolerance_m:
            return False, None, False, "one_circle_contains_the_other"

        # A pair inside the tiny tolerance band can be used by an *existing*
        # direct range filter, but it cannot bootstrap an intersection.
        along = (d1_m * d1_m - d2_m * d2_m + self._baseline_m * self._baseline_m) / (2.0 * self._baseline_m)
        height_squared = d1_m * d1_m - along * along
        if height_squared < -1e-8:
            return True, 0.0, True, "near_tangent"
        height = math.sqrt(max(0.0, height_squared))
        low_geometry = height < self.config.min_geometry_height_m
        return True, height, low_geometry, "ok"

    def _bootstrap_point(self, d1_m: float, d2_m: float) -> tuple[Optional[Point], Optional[float], str]:
        """Find the declared-side circle intersection used only to initialise."""
        along = (d1_m * d1_m - d2_m * d2_m + self._baseline_m * self._baseline_m) / (2.0 * self._baseline_m)
        height_squared = d1_m * d1_m - along * along
        if height_squared < -1e-8:
            return None, None, "bootstrap_geometry_no_intersection"
        height = math.sqrt(max(0.0, height_squared))
        if height < self.config.min_geometry_height_m and self.config.reject_low_geometry_bootstrap:
            return None, height, "bootstrap_low_geometry"

        a1, a2 = self.anchors_m
        ux = (a2[0] - a1[0]) / self._baseline_m
        uy = (a2[1] - a1[1]) / self._baseline_m
        nx, ny = -uy, ux
        candidates = (
            (a1[0] + ux * along + nx * height, a1[1] + uy * along + ny * height),
            (a1[0] + ux * along - nx * height, a1[1] + uy * along - ny * height),
        )
        for candidate in candidates:
            if self._on_allowed_side(candidate):
                return candidate, height, "bootstrap"
        return None, height, "bootstrap_side_unavailable"

    def _on_allowed_side(self, point: Point) -> bool:
        """Whether a metric point remains in the declared half-plane.

        A point on the baseline is permitted for an already initialized state
        (a noisy update can approach it), but a bootstrap is separately
        prevented at low geometry.  Do not permit even a tiny negative-side
        tolerance here: after an off-line bootstrap, crossing the baseline
        would silently turn the estimate into its unobservable mirror.  A
        near-zero point is instead exposed as low geometry by the range path.
        """
        a1, a2 = self.anchors_m
        cross = (
            (a2[0] - a1[0]) * (point[1] - a1[1])
            - (a2[1] - a1[1]) * (point[0] - a1[0])
        )
        return cross * self.allowed_side >= 0.0

    def _measurement_model(self) -> tuple[Optional[Vector2], Optional[list[list[float]]], Optional[str]]:
        if self._state is None:
            return None, None, "no_state"
        x, y = self._state[0], self._state[1]
        expected: list[float] = []
        jacobian: list[list[float]] = []
        for anchor_x, anchor_y in self.anchors_m:
            dx, dy = x - anchor_x, y - anchor_y
            distance = math.hypot(dx, dy)
            if distance <= 1e-6:
                return None, None, "predicted_at_anchor"
            expected.append(distance)
            jacobian.append([dx / distance, dy / distance, 0.0, 0.0])
        return (expected[0], expected[1]), jacobian, None

    def _apply_range_update(self, d1_m: float, d2_m: float, range_std_m: Tuple[float, float]) -> tuple[bool, Optional[float], str, bool, Mapping[str, Any]]:
        """Perform an atomic two-range EKF correction with a chi-square gate."""
        if self._state is None or self._covariance is None:
            return False, None, "no_state", False, {}
        expected, h, model_error = self._measurement_model()
        if expected is None or h is None:
            return False, None, model_error or "invalid_measurement_model", False, {}

        innovation = [d1_m - expected[0], d2_m - expected[1]]
        max_residual = max(abs(innovation[0]), abs(innovation[1]))
        details = {
            "predicted_ranges_m": (expected[0], expected[1]),
            "innovation_m": (innovation[0], innovation[1]),
            "range_std_m": range_std_m,
        }
        if max_residual > self.config.max_range_residual_m:
            return False, None, "range_residual_too_large", True, details

        r = [[range_std_m[0] ** 2, 0.0], [0.0, range_std_m[1] ** 2]]
        hp = _matmul(h, self._covariance)
        s = _add(_matmul(hp, _transpose(h)), r)
        inverse_s = _inverse_2x2(s)
        if inverse_s is None:
            return False, None, "singular_innovation_covariance", False, details

        nis = (
            innovation[0] * (inverse_s[0][0] * innovation[0] + inverse_s[0][1] * innovation[1])
            + innovation[1] * (inverse_s[1][0] * innovation[0] + inverse_s[1][1] * innovation[1])
        )
        details["innovation_covariance"] = tuple(tuple(value for value in row) for row in s)
        if not math.isfinite(nis) or nis > self.config.innovation_gate_chi2:
            return False, nis, "innovation_gate_rejected", True, details

        previous_state = list(self._state)
        previous_covariance = self._covariance
        ph_t = _matmul(self._covariance, _transpose(h))
        gain = _matmul(ph_t, inverse_s)  # 4x2
        for row in range(4):
            self._state[row] += gain[row][0] * innovation[0] + gain[row][1] * innovation[1]

        # Joseph covariance form is more numerically stable than P-KHP.
        identity = _identity(4)
        kh = _matmul(gain, h)
        i_minus_kh = _subtract(identity, kh)
        joseph_left = _matmul(_matmul(i_minus_kh, self._covariance), _transpose(i_minus_kh))
        joseph_right = _matmul(_matmul(gain, r), _transpose(gain))
        self._covariance = _symmetrise_and_floor(_add(joseph_left, joseph_right))

        speed = math.hypot(self._state[2], self._state[3])
        if speed > self.config.max_speed_mps:
            scale = self.config.max_speed_mps / speed
            self._state[2] *= scale
            self._state[3] *= scale
            details["speed_limited"] = True
        if not self._on_allowed_side((self._state[0], self._state[1])):
            self._state = previous_state
            self._covariance = previous_covariance
            details.update({
                "allowed_side": self.allowed_side,
                "side_constrained": True,
            })
            return False, nis, "allowed_side_violation", True, details
        return True, nis, "uwb_update", False, details

    def update_ranges(
        self,
        d1_m: Any,
        d2_m: Any,
        *,
        timestamp_s: Any,
        range_std_m: Any = None,
        range_trusted: Any = None,
        nlos_flags: Any = None,
    ) -> FilterResult:
        """Apply one direct, atomic two-range UWB update.

        Every accepted result used two ranges from the same packet.  An
        untrusted pair or an innovation gate failure rejects the whole pair.
        An NLOS flag does NOT reject: the flagged link updates with the
        inflated :attr:`UwbImuFilterConfig.nlos_range_std_m` (flag, don't
        drop), except before the first fix, where a flagged pair may not
        bootstrap the track.  The caller may still receive a clearly held
        last UWB fix until :attr:`UwbImuFilterConfig.hold_seconds` expires.
        """
        timestamp = self._timestamp(timestamp_s)
        if timestamp is None:
            self._last_update_diagnostic = {}
            return self._output(now_s=self._last_timestamp_s, accepted_uwb=False, reason="invalid_timestamp")

        if self._last_timestamp_s is not None and timestamp < self._last_timestamp_s:
            self._last_update_diagnostic = {"packet_timestamp_s": timestamp, "state_timestamp_s": self._last_timestamp_s}
            return self._output(now_s=self._last_timestamp_s, accepted_uwb=False, reason="out_of_order_timestamp")

        # Advance time without inventing an IMU input if the caller did not
        # explicitly call predict() for this timestamp.
        if self._last_timestamp_s is None or timestamp > self._last_timestamp_s:
            self._advance(timestamp, None, self.config.process_accel_std_mps2)

        d1 = _finite_float(d1_m)
        d2 = _finite_float(d2_m)
        if d1 is None or d2 is None:
            self._last_update_diagnostic = {}
            return self._output(now_s=timestamp, accepted_uwb=False, reason="non_finite_range")

        trusted = _normalise_flag_pair(range_trusted, default=True)
        nlos = _normalise_flag_pair(nlos_flags, default=False)
        standard_deviation = _normalise_range_std(
            range_std_m, self.config.range_std_m, self.config.minimum_range_std_m
        )
        if trusted is None or nlos is None or standard_deviation is None:
            self._last_update_diagnostic = {}
            return self._output(now_s=timestamp, accepted_uwb=False, reason="invalid_range_quality")
        if not all(trusted):
            self._last_update_diagnostic = {"range_trusted": trusted}
            return self._output(now_s=timestamp, accepted_uwb=False, reason="range_untrusted")
        nlos_any = any(nlos)
        if nlos_any and self._state is None:
            # Never seed the track from suspected geometry: a bootstrap sits
            # exactly on the two circles, so an NLOS-biased pair would place
            # the first fix metres off with nothing to regularise it.  Once a
            # state exists, flagged pairs update it with an inflated std.
            self._last_update_diagnostic = {"nlos_flags": nlos}
            return self._output(now_s=timestamp, accepted_uwb=False, reason="nlos_bootstrap_deferred", nlos_suspected=True)
        if nlos_any:
            inflated = max(self.config.nlos_range_std_m, self.config.minimum_range_std_m)
            standard_deviation = (
                max(standard_deviation[0], inflated) if nlos[0] else standard_deviation[0],
                max(standard_deviation[1], inflated) if nlos[1] else standard_deviation[1],
            )

        geometry_valid, height, low_geometry, geometry_reason = self._geometry(d1, d2)
        if not geometry_valid:
            self._last_update_diagnostic = {"d1_m": d1, "d2_m": d2}
            return self._output(
                now_s=timestamp,
                accepted_uwb=False,
                reason=geometry_reason,
                geometry_height_m=height,
                low_geometry=low_geometry,
            )

        if self._state is None:
            point, bootstrap_height, bootstrap_reason = self._bootstrap_point(d1, d2)
            if point is None:
                self._last_update_diagnostic = {"d1_m": d1, "d2_m": d2}
                return self._output(
                    now_s=timestamp,
                    accepted_uwb=False,
                    reason=bootstrap_reason,
                    geometry_height_m=bootstrap_height,
                    low_geometry=low_geometry,
                )
            position_variance = self.config.initial_position_std_m ** 2
            velocity_variance = self.config.initial_velocity_std_mps ** 2
            self._state = [point[0], point[1], 0.0, 0.0]
            self._covariance = [
                [position_variance, 0.0, 0.0, 0.0],
                [0.0, position_variance, 0.0, 0.0],
                [0.0, 0.0, velocity_variance, 0.0],
                [0.0, 0.0, 0.0, velocity_variance],
            ]
            accepted, nis, reason, nlos_suspected, details = self._apply_range_update(d1, d2, standard_deviation)
            # A bootstrap state lies exactly on the ranges.  An unexpected
            # failure here should never become a visible coordinate.
            if not accepted:
                self._state = None
                self._covariance = None
                self._last_update_diagnostic = dict(details)
                return self._output(
                    now_s=timestamp,
                    accepted_uwb=False,
                    reason=reason,
                    nis=nis,
                    geometry_height_m=bootstrap_height,
                    low_geometry=low_geometry,
                    nlos_suspected=nlos_suspected,
                )
            self._last_accepted_uwb_s = timestamp
            self._last_update_diagnostic = {"bootstrap": True, **details}
            return self._output(
                now_s=timestamp,
                accepted_uwb=True,
                reason="uwb_bootstrap",
                nis=nis,
                geometry_height_m=bootstrap_height,
                low_geometry=low_geometry,
                details={"geometry_reason": geometry_reason},
            )

        if low_geometry and self.config.reject_low_geometry_updates:
            self._last_update_diagnostic = {"d1_m": d1, "d2_m": d2}
            return self._output(
                now_s=timestamp,
                accepted_uwb=False,
                reason="low_geometry_rejected",
                geometry_height_m=height,
                low_geometry=True,
            )

        accepted, nis, reason, nlos_suspected, details = self._apply_range_update(d1, d2, standard_deviation)
        self._last_update_diagnostic = dict(details)
        if nlos_any:
            self._last_update_diagnostic["nlos_flags"] = nlos
            nlos_suspected = True
        if accepted:
            self._last_accepted_uwb_s = timestamp
        return self._output(
            now_s=timestamp,
            accepted_uwb=accepted,
            reason=reason,
            nis=nis,
            geometry_height_m=height,
            low_geometry=low_geometry,
            nlos_suspected=nlos_suspected,
            details={"geometry_reason": geometry_reason},
        )

    def apply_stationary_zupt(
        self,
        *,
        timestamp_s: Any,
        stationary: bool,
        imu_ok: bool,
        stationary_trusted: bool = True,
    ) -> FilterResult:
        """Apply a zero-velocity update from a trusted BNO08x still cue.

        This reduces velocity and jitter covariance only.  It deliberately
        does not refresh ``last_accepted_uwb_s``; after the UWB hold window,
        the result remains unpublished even if the IMU still says stationary.
        """
        timestamp = self._timestamp(timestamp_s)
        if timestamp is None:
            return self._output(now_s=self._last_timestamp_s, accepted_uwb=False, reason="invalid_timestamp")
        if self._last_timestamp_s is not None and timestamp < self._last_timestamp_s:
            return self._output(now_s=self._last_timestamp_s, accepted_uwb=False, reason="out_of_order_timestamp")
        if self._last_timestamp_s is None or timestamp > self._last_timestamp_s:
            self._advance(timestamp, None, self.config.process_accel_std_mps2)
        if self._state is None or self._covariance is None:
            return self._output(now_s=timestamp, accepted_uwb=False, reason="no_accepted_uwb_fix")
        if not self.config.use_imu:
            return self._output(now_s=timestamp, accepted_uwb=False, reason="imu_disabled")
        if not imu_ok:
            return self._output(now_s=timestamp, accepted_uwb=False, reason="imu_unavailable")
        if not stationary_trusted:
            return self._output(now_s=timestamp, accepted_uwb=False, reason="stationary_untrusted")
        if not stationary:
            return self._output(now_s=timestamp, accepted_uwb=False, reason="not_stationary")

        # Measurement h(x) = [vx, vy], z = [0, 0].
        h = [[0.0, 0.0, 1.0, 0.0], [0.0, 0.0, 0.0, 1.0]]
        r_value = self.config.zupt_velocity_std_mps ** 2
        r = [[r_value, 0.0], [0.0, r_value]]
        hp = _matmul(h, self._covariance)
        s = _add(_matmul(hp, _transpose(h)), r)
        inverse_s = _inverse_2x2(s)
        if inverse_s is None:
            return self._output(now_s=timestamp, accepted_uwb=False, reason="singular_zupt_covariance")
        innovation = [-self._state[2], -self._state[3]]
        gain = _matmul(_matmul(self._covariance, _transpose(h)), inverse_s)
        for row in range(4):
            self._state[row] += gain[row][0] * innovation[0] + gain[row][1] * innovation[1]
        identity = _identity(4)
        i_minus_kh = _subtract(identity, _matmul(gain, h))
        self._covariance = _symmetrise_and_floor(_add(
            _matmul(_matmul(i_minus_kh, self._covariance), _transpose(i_minus_kh)),
            _matmul(_matmul(gain, r), _transpose(gain)),
        ))
        return self._output(
            now_s=timestamp,
            accepted_uwb=False,
            reason="zupt",
            zupt_applied=True,
            details={"stationary": True},
        )

    def estimate(self, *, now_s: Any) -> FilterResult:
        """Return only a fresh UWB fix or a bounded-duration held prediction."""
        timestamp = self._timestamp(now_s)
        if timestamp is None:
            return self._output(now_s=self._last_timestamp_s, accepted_uwb=False, reason="invalid_timestamp")
        return self._output(now_s=timestamp, accepted_uwb=False, reason="uwb_hold")

    def step(
        self,
        *,
        timestamp_s: Any,
        d1_m: Any = None,
        d2_m: Any = None,
        body_linear_accel_mps2: Any = None,
        map_heading_deg: Any = None,
        imu_ok: bool = False,
        heading_calibrated: bool = False,
        heading_accuracy_deg: Any = None,
        acceleration_trusted: bool = True,
        stationary: bool = False,
        stationary_trusted: bool = True,
        range_std_m: Any = None,
        range_trusted: Any = None,
        nlos_flags: Any = None,
    ) -> FilterResult:
        """Convenience single-packet path: predict, optional ZUPT, then UWB.

        Use this when BNO and DW3000 telemetry share the same timestamp.  UWB
        remains optional, but no-UWB calls return a hold only if a prior UWB
        update was accepted.
        """
        prediction = self.predict(
            timestamp_s=timestamp_s,
            body_linear_accel_mps2=body_linear_accel_mps2,
            map_heading_deg=map_heading_deg,
            imu_ok=imu_ok,
            heading_calibrated=heading_calibrated,
            heading_accuracy_deg=heading_accuracy_deg,
            acceleration_trusted=acceleration_trusted,
        )
        if stationary:
            self.apply_stationary_zupt(
                timestamp_s=timestamp_s,
                stationary=True,
                imu_ok=imu_ok,
                stationary_trusted=stationary_trusted,
            )
        if d1_m is None or d2_m is None:
            return self._output(
                now_s=self._timestamp(timestamp_s),
                accepted_uwb=False,
                reason="no_uwb_measurement",
                imu_used=bool(prediction.get("imu_used")),
                imu_reason=prediction.get("imu_reason"),
            )
        return self.update_ranges(
            d1_m,
            d2_m,
            timestamp_s=timestamp_s,
            range_std_m=range_std_m,
            range_trusted=range_trusted,
            nlos_flags=nlos_flags,
        )


__all__ = ["FilterResult", "UwbImuFilter", "UwbImuFilterConfig"]
