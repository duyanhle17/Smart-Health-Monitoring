"""Stationary, known-point capture for per-link DW3000 range calibration.

The capture deliberately produces a recommendation rather than changing an
active deployment setting by itself.  A bad known-point entry or a worker that
was moved during collection must never silently change live location math.
"""

from __future__ import annotations

import math
import statistics
import time
from dataclasses import dataclass, field
from typing import Any


def _finite_positive(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) and number > 0.0 else None


def _finite(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _stationary(imu_stability: Any, gx: Any, gy: Any, gz: Any, linear_accel: Any,
                max_gyro_rad_s: float, max_linear_accel_m_s2: float) -> bool:
    """Require the BNO08x's own still state plus small measured motion."""
    try:
        stability = int(float(imu_stability))
    except (TypeError, ValueError):
        return False
    if stability not in {1, 2}:  # on-table / stationary
        return False

    components = (_finite(gx), _finite(gy), _finite(gz))
    linear = _finite(linear_accel)
    if any(component is None for component in components) or linear is None:
        return False
    gyro = math.sqrt(sum(component * component for component in components if component is not None))
    return gyro <= max_gyro_rad_s and abs(linear) <= max_linear_accel_m_s2


@dataclass
class RangeCalibrationCapture:
    """Collect a robust raw-range median at one tape-measured location."""

    worker_id: str
    known_d1_m: float
    known_d2_m: float
    min_samples: int = 80
    max_mad_m: float = 0.04
    max_gyro_rad_s: float = 0.08
    max_linear_accel_m_s2: float = 0.12
    created_at: float = field(default_factory=time.time)
    raw_d1_samples: list[float] = field(default_factory=list)
    raw_d2_samples: list[float] = field(default_factory=list)
    rejected_nonstationary: int = 0
    rejected_bad_range: int = 0
    rejected_stale_range: int = 0
    rejected_stale_imu: int = 0
    rejected_duplicate_range: int = 0
    rejected_step_change: int = 0
    last_range_seq: int | None = None
    range_epoch: str | None = None
    initial_steps: int | None = None
    restarted_range_epoch: int = 0

    def __post_init__(self) -> None:
        self.known_d1_m = _finite_positive(self.known_d1_m) or 0.0
        self.known_d2_m = _finite_positive(self.known_d2_m) or 0.0
        self.min_samples = max(10, min(300, int(self.min_samples)))
        self.max_mad_m = max(0.005, min(1.0, float(self.max_mad_m)))
        if not self.worker_id or not self.known_d1_m or not self.known_d2_m:
            raise ValueError("worker_id and both known distances must be finite positive values")

    def add(self, raw_d1_m: Any, raw_d2_m: Any, *, imu_stability: Any,
            gx: Any, gy: Any, gz: Any, linear_accel: Any,
            range_seq: Any = None, range_age_ms: Any = None, steps: Any = None,
            range_epoch: Any = None, imu_age_ms: Any = None) -> bool:
        """Add one sample only when it is a physically still, valid reading."""
        d1 = _finite_positive(raw_d1_m)
        d2 = _finite_positive(raw_d2_m)
        if d1 is None or d2 is None:
            self.rejected_bad_range += 1
            return False
        age_ms = _finite(range_age_ms)
        if age_ms is not None and (age_ms < 0.0 or age_ms > 700.0):
            self.rejected_stale_range += 1
            return False
        imu_age = _finite(imu_age_ms)
        if imu_age is not None and (imu_age < 0.0 or imu_age > 250.0):
            self.rejected_stale_imu += 1
            return False
        sequence = _finite(range_seq)
        if sequence is not None:
            if sequence < 0.0 or not math.isclose(sequence, round(sequence), abs_tol=1e-6):
                self.rejected_duplicate_range += 1
                return False
            sequence_int = int(sequence)
        else:
            sequence_int = None
        epoch = str(range_epoch).strip()[:96] if range_epoch is not None else ""
        epoch = epoch or None
        if epoch is not None and self.range_epoch is not None and epoch != self.range_epoch:
            self._restart_for_new_radio_epoch(epoch)
        elif (sequence_int is not None and self.last_range_seq is not None
              and sequence_int <= self.last_range_seq):
            restart = sequence_int <= 2 and self.last_range_seq >= 8
            if restart:
                self._restart_for_new_radio_epoch(epoch or self.range_epoch)
            else:
                self.rejected_duplicate_range += 1
                return False
        if not _stationary(
            imu_stability, gx, gy, gz, linear_accel,
            self.max_gyro_rad_s, self.max_linear_accel_m_s2,
        ):
            self.rejected_nonstationary += 1
            return False
        step_value = _finite(steps)
        if step_value is not None:
            step_int = int(step_value)
            if self.initial_steps is None:
                self.initial_steps = step_int
            elif step_int != self.initial_steps:
                self.rejected_step_change += 1
                return False
        self.raw_d1_samples.append(d1)
        self.raw_d2_samples.append(d2)
        if sequence_int is not None:
            self.last_range_seq = sequence_int
        if epoch is not None:
            self.range_epoch = epoch
        return True

    def _restart_for_new_radio_epoch(self, epoch: str | None) -> None:
        """Avoid mixing a partial calibration capture across a worker reboot."""
        self.raw_d1_samples.clear()
        self.raw_d2_samples.clear()
        self.last_range_seq = None
        self.initial_steps = None
        self.range_epoch = epoch
        self.restarted_range_epoch += 1

    @staticmethod
    def _summary(values: list[float]) -> dict[str, float] | None:
        if not values:
            return None
        median = statistics.median(values)
        mad = statistics.median(abs(value - median) for value in values)
        return {
            "median_m": round(median, 4),
            "mad_m": round(mad, 4),
            "min_m": round(min(values), 4),
            "max_m": round(max(values), 4),
        }

    def status(self) -> dict[str, Any]:
        d1 = self._summary(self.raw_d1_samples)
        d2 = self._summary(self.raw_d2_samples)
        count = min(len(self.raw_d1_samples), len(self.raw_d2_samples))
        stable = bool(
            d1 and d2 and d1["mad_m"] <= self.max_mad_m and d2["mad_m"] <= self.max_mad_m
        )
        ready = count >= self.min_samples and stable
        result: dict[str, Any] = {
            "worker_id": self.worker_id,
            "known_distances_m": {"d1": self.known_d1_m, "d2": self.known_d2_m},
            "accepted_samples": count,
            "required_samples": self.min_samples,
            "max_mad_m": self.max_mad_m,
            "raw_d1": d1,
            "raw_d2": d2,
            "rejected_nonstationary": self.rejected_nonstationary,
            "rejected_bad_range": self.rejected_bad_range,
            "rejected_stale_range": self.rejected_stale_range,
            "rejected_stale_imu": self.rejected_stale_imu,
            "rejected_duplicate_range": self.rejected_duplicate_range,
            "rejected_step_change": self.rejected_step_change,
            "restarted_range_epoch": self.restarted_range_epoch,
            "ready": ready,
            "action": "apply_only_after_operator_review",
        }
        if d1 and d2:
            result["recommended_offsets_m"] = {
                "d1": round(self.known_d1_m - d1["median_m"], 4),
                "d2": round(self.known_d2_m - d2["median_m"], 4),
            }
        if count >= self.min_samples and not stable:
            result["reason"] = "range_spread_too_large_keep_worker_still_or_fix_rf"
        elif not ready:
            result["reason"] = "collecting_stationary_samples"
        else:
            result["reason"] = "review_recommended_offsets"
        return result
