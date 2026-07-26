"""Online map-frame offset learner for the magnetometer-free Game RV heading.

The BNO08x Game Rotation Vector yaw is gyro-integrated: immune to the magnetic
disturbance of a steel workshop, but its zero direction is arbitrary at every
boot and drifts slowly.  This module learns, per worker, the transform

    map_heading_deg = sign * yaw_game_deg + offset_deg      (0 = +map-x, +90 = +map-y)

by comparing the direction the worker actually travelled (consecutive
published UWB fixes) with the yaw the tag reported while walking straight.
It replaces the manual IMU_YAW_A1_TO_A2_DEG commissioning ritual for the
Game RV path.

Safety properties:
- Straight segments only: enough net displacement, a straight path, and a
  steady yaw within the window; anything else teaches nothing.
- Both sign hypotheses (mounting chirality) are scored; commissioning needs
  several segments spanning different walk directions, so a single walk
  direction can never fake agreement between the hypotheses.
- ``imu_epoch`` changes discard everything learned: a BNO re-init draws a new
  arbitrary yaw reference.
- The learned mapping is advisory (heading prior / mirror-branch evidence);
  it never becomes a position source by itself.
"""

from __future__ import annotations

import math
import os
from collections import deque
from dataclasses import dataclass, field
from typing import Deque, Dict, List, Optional, Tuple


def _env_float(name: str, default: float, minimum: Optional[float] = None) -> float:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        value = float(raw)
    except ValueError:
        return default
    if minimum is not None:
        value = max(minimum, value)
    return value


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


# Master switch.  Learning itself is passive and cheap; consumers additionally
# gate on UWB_IMU_FUSION before the learned heading influences anything.
YAW_OFFSET_LEARNER = _env_bool("UWB_YAW_OFFSET_LEARNER", True)
# A learnable segment: at least this much net displacement...
MIN_SEGMENT_M = _env_float("UWB_YAW_OFFSET_MIN_SEGMENT_M", 1.0, minimum=0.3)
# ...accumulated within this window (older points are discarded)...
SEGMENT_WINDOW_S = _env_float("UWB_YAW_OFFSET_SEGMENT_WINDOW_S", 4.0, minimum=1.0)
# ...with net/path straightness at least this...
MIN_STRAIGHTNESS = _env_float("UWB_YAW_OFFSET_MIN_STRAIGHTNESS", 0.85, minimum=0.5)
# ...and the reported yaw steady to within this circular spread.
MAX_YAW_SPREAD_DEG = _env_float("UWB_YAW_OFFSET_MAX_YAW_SPREAD_DEG", 15.0, minimum=2.0)
# Yaw samples older than this cannot be paired with a fix.
MAX_YAW_AGE_MS = _env_float("UWB_YAW_OFFSET_MAX_YAW_AGE_MS", 1000.0, minimum=100.0)
# Commissioning gates.
MIN_SEGMENTS = max(2, int(_env_float("UWB_YAW_OFFSET_MIN_SEGMENTS", 3, minimum=2)))
MIN_DIVERSITY_DEG = _env_float("UWB_YAW_OFFSET_MIN_DIVERSITY_DEG", 45.0, minimum=10.0)
MAX_RESIDUAL_DEG = _env_float("UWB_YAW_OFFSET_MAX_RESIDUAL_DEG", 20.0, minimum=5.0)
MIN_MARGIN_DEG = _env_float("UWB_YAW_OFFSET_MIN_MARGIN_DEG", 10.0, minimum=0.0)
# Post-commission drift tracking / self-revocation.
OFFSET_EMA_ALPHA = _env_float("UWB_YAW_OFFSET_EMA_ALPHA", 0.25, minimum=0.01)
DECOMMISSION_RESIDUAL_DEG = _env_float("UWB_YAW_OFFSET_DECOMMISSION_RESIDUAL_DEG", 35.0, minimum=10.0)
DECOMMISSION_STRIKES = max(1, int(_env_float("UWB_YAW_OFFSET_DECOMMISSION_STRIKES", 3, minimum=1)))

_MAX_POINTS = 64
_MAX_TRACK_HEADINGS = 12


def _wrap_deg(angle: float) -> float:
    return ((angle + 180.0) % 360.0) - 180.0


def _circular_mean_deg(angles: List[float]) -> Optional[float]:
    if not angles:
        return None
    x = sum(math.cos(math.radians(a)) for a in angles)
    y = sum(math.sin(math.radians(a)) for a in angles)
    if math.hypot(x, y) < 1e-9:
        return None
    return math.degrees(math.atan2(y, x))


@dataclass
class _Hypothesis:
    """One sign hypothesis: unit-vector EMA of the offset + residual EMA."""

    ex: float = 0.0
    ey: float = 0.0
    residual_ema_deg: float = 0.0
    samples: int = 0

    def offset_deg(self) -> Optional[float]:
        if self.samples == 0 or math.hypot(self.ex, self.ey) < 1e-9:
            return None
        return math.degrees(math.atan2(self.ey, self.ex))

    def add(self, offset_sample_deg: float) -> None:
        current = self.offset_deg()
        if current is not None:
            residual = abs(_wrap_deg(offset_sample_deg - current))
            self.residual_ema_deg += OFFSET_EMA_ALPHA * (residual - self.residual_ema_deg)
        sx = math.cos(math.radians(offset_sample_deg))
        sy = math.sin(math.radians(offset_sample_deg))
        if self.samples == 0:
            self.ex, self.ey = sx, sy
        else:
            self.ex += OFFSET_EMA_ALPHA * (sx - self.ex)
            self.ey += OFFSET_EMA_ALPHA * (sy - self.ey)
        self.samples += 1


@dataclass
class _WorkerLearner:
    epoch: Optional[int] = None
    points: Deque[Tuple[float, float, float, float]] = field(default_factory=lambda: deque(maxlen=_MAX_POINTS))
    track_headings: Deque[float] = field(default_factory=lambda: deque(maxlen=_MAX_TRACK_HEADINGS))
    plus: _Hypothesis = field(default_factory=_Hypothesis)
    minus: _Hypothesis = field(default_factory=_Hypothesis)
    commissioned: bool = False
    sign: int = 0
    strikes: int = 0

    def reset_learning(self) -> None:
        self.points.clear()
        self.track_headings.clear()
        self.plus = _Hypothesis()
        self.minus = _Hypothesis()
        self.commissioned = False
        self.sign = 0
        self.strikes = 0


_learners: Dict[str, _WorkerLearner] = {}


def _learner(worker_id: str) -> _WorkerLearner:
    learner = _learners.get(worker_id)
    if learner is None:
        learner = _WorkerLearner()
        _learners[worker_id] = learner
    return learner


def reset(worker_id: str) -> None:
    _learners.pop(worker_id, None)


def _reset_all() -> None:
    _learners.clear()


def _heading_diversity_deg(headings: Deque[float]) -> float:
    values = list(headings)
    best = 0.0
    for i in range(len(values)):
        for j in range(i + 1, len(values)):
            best = max(best, abs(_wrap_deg(values[i] - values[j])))
    return best


def observe_fix(
    worker_id: str,
    *,
    t_s: float,
    x_units: float,
    y_units: float,
    units_per_metre: float,
    yaw_game_deg: Optional[float],
    yaw_game_age_ms: Optional[float],
    imu_epoch: Optional[int],
) -> None:
    """Feed one published UWB fix paired with the yaw reported alongside it."""
    if not YAW_OFFSET_LEARNER or units_per_metre <= 0.0:
        return
    if yaw_game_deg is None or imu_epoch is None:
        # A sample without a yaw or an epoch teaches nothing — and must not
        # be allowed to reset a commissioned learner either.
        return
    learner = _learner(worker_id)
    if imu_epoch != learner.epoch:
        # New epoch = new arbitrary Game RV reference: forget everything.
        learner.reset_learning()
        learner.epoch = imu_epoch
    if yaw_game_age_ms is None or yaw_game_age_ms < 0 or yaw_game_age_ms > MAX_YAW_AGE_MS:
        return
    if not (math.isfinite(t_s) and math.isfinite(x_units) and math.isfinite(y_units) and math.isfinite(yaw_game_deg)):
        return

    points = learner.points
    points.append((float(t_s), float(x_units), float(y_units), float(yaw_game_deg)))
    while points and (points[-1][0] - points[0][0]) > SEGMENT_WINDOW_S:
        points.popleft()
    if len(points) < 3:
        return

    x0, y0 = points[0][1], points[0][2]
    xn, yn = points[-1][1], points[-1][2]
    net_units = math.hypot(xn - x0, yn - y0)
    net_m = net_units / units_per_metre
    if net_m < MIN_SEGMENT_M:
        return

    path_units = 0.0
    for index in range(1, len(points)):
        path_units += math.hypot(
            points[index][1] - points[index - 1][1],
            points[index][2] - points[index - 1][2],
        )
    if path_units <= 1e-9 or (net_units / path_units) < MIN_STRAIGHTNESS:
        # Curved or jittery window: drop the oldest half and keep watching.
        for _ in range(len(points) // 2):
            points.popleft()
        return

    yaws = [p[3] for p in points]
    yaw_mean = _circular_mean_deg(yaws)
    if yaw_mean is None:
        points.clear()
        return
    if max(abs(_wrap_deg(y - yaw_mean)) for y in yaws) > MAX_YAW_SPREAD_DEG:
        points.clear()
        return

    track_heading = math.degrees(math.atan2(yn - y0, xn - x0))
    points.clear()

    if learner.commissioned:
        # Judge the segment against the PRE-update mapping.  Adding it to the
        # EMA first would pull the offset toward the outlier and soften the
        # decommission threshold from DECOMMISSION_RESIDUAL_DEG to roughly
        # (1-alpha)^-1 times that — a broken mapping could survive forever.
        winner = learner.plus if learner.sign > 0 else learner.minus
        offset = winner.offset_deg()
        if offset is None:
            learner.reset_learning()
            return
        predicted = _wrap_deg(learner.sign * yaw_mean + offset)
        residual = abs(_wrap_deg(track_heading - predicted))
        if residual > DECOMMISSION_RESIDUAL_DEG:
            # A strike segment must not teach either hypothesis.
            learner.strikes += 1
            if learner.strikes >= DECOMMISSION_STRIKES:
                # The mapping no longer matches how the worker moves
                # (drift, remount).  Fall back to unlearned and rebuild.
                learner.reset_learning()
            return
        learner.strikes = 0
        learner.track_headings.append(track_heading)
        learner.plus.add(_wrap_deg(track_heading - yaw_mean))
        learner.minus.add(_wrap_deg(track_heading + yaw_mean))
        return

    learner.track_headings.append(track_heading)
    learner.plus.add(_wrap_deg(track_heading - yaw_mean))
    learner.minus.add(_wrap_deg(track_heading + yaw_mean))

    if learner.plus.samples < MIN_SEGMENTS:
        return
    if _heading_diversity_deg(learner.track_headings) < MIN_DIVERSITY_DEG:
        return
    winner, loser, sign = (
        (learner.plus, learner.minus, 1)
        if learner.plus.residual_ema_deg <= learner.minus.residual_ema_deg
        else (learner.minus, learner.plus, -1)
    )
    if winner.residual_ema_deg > MAX_RESIDUAL_DEG:
        return
    if (loser.residual_ema_deg - winner.residual_ema_deg) < MIN_MARGIN_DEG:
        return
    learner.commissioned = True
    learner.sign = sign
    learner.strikes = 0


def commissioned(worker_id: str) -> bool:
    learner = _learners.get(worker_id)
    return bool(learner and learner.commissioned)


def commissioned_workers() -> List[str]:
    """Workers whose online mapping is currently trusted (for diagnostics)."""
    return sorted(worker for worker, learner in _learners.items() if learner.commissioned)


def map_heading(worker_id: str, *, yaw_game_deg: Optional[float], imu_epoch: Optional[int]) -> Optional[float]:
    """Learned map heading for a live yaw sample, or None when not usable."""
    learner = _learners.get(worker_id)
    if (
        learner is None
        or not learner.commissioned
        or yaw_game_deg is None
        or not math.isfinite(yaw_game_deg)
        or imu_epoch != learner.epoch
    ):
        return None
    winner = learner.plus if learner.sign > 0 else learner.minus
    offset = winner.offset_deg()
    if offset is None:
        return None
    return _wrap_deg(learner.sign * yaw_game_deg + offset)


def diagnostics(worker_id: str) -> dict:
    learner = _learners.get(worker_id)
    if learner is None:
        return {"commissioned": False, "segments": 0}
    winner = learner.plus if learner.sign >= 0 else learner.minus
    return {
        "commissioned": learner.commissioned,
        "sign": learner.sign,
        "offset_deg": None if winner.offset_deg() is None else round(winner.offset_deg(), 1),
        "residual_deg": round(winner.residual_ema_deg, 1),
        "segments": learner.plus.samples,
        "epoch": learner.epoch,
    }
