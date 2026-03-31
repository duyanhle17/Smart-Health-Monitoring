from __future__ import annotations

import csv
from collections import defaultdict
from dataclasses import dataclass
from typing import Dict, List, Sequence, Tuple

import numpy as np

from .topology import MineTopology


@dataclass
class GasRecord:
    timestamp: int
    zone_id: str
    methane_ppm: float
    co_ppm: float
    ventilation_level: float


def load_gas_csv(path: str) -> List[GasRecord]:
    """
    Load gas history from CSV.

    Required headers:
      timestamp,zone_id,methane_ppm,co_ppm,ventilation_level
    """
    rows: List[GasRecord] = []
    with open(path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        required = {"timestamp", "zone_id", "methane_ppm", "co_ppm", "ventilation_level"}
        if not required.issubset(set(reader.fieldnames or [])):
            missing = sorted(required - set(reader.fieldnames or []))
            raise ValueError(f"Missing required CSV columns: {missing}")

        for raw in reader:
            rows.append(
                GasRecord(
                    timestamp=int(raw["timestamp"]),
                    zone_id=str(raw["zone_id"]),
                    methane_ppm=float(raw["methane_ppm"]),
                    co_ppm=float(raw["co_ppm"]),
                    ventilation_level=float(raw["ventilation_level"]),
                )
            )

    rows.sort(key=lambda r: (r.timestamp, r.zone_id))
    return rows


def _build_zone_series(records: Sequence[GasRecord]) -> Dict[str, Dict[int, GasRecord]]:
    zone_ts: Dict[str, Dict[int, GasRecord]] = defaultdict(dict)
    for rec in records:
        zone_ts[rec.zone_id][rec.timestamp] = rec
    return zone_ts


def _neighbor_snapshot(
    topology: MineTopology,
    zone: str,
    timestamp: int,
    zone_ts: Dict[str, Dict[int, GasRecord]],
) -> Tuple[float, float]:
    methane_values: List[float] = []
    co_values: List[float] = []

    for neighbor, _distance in topology.neighbors(zone):
        n_rec = zone_ts.get(neighbor, {}).get(timestamp)
        if n_rec is None:
            continue
        methane_values.append(n_rec.methane_ppm)
        co_values.append(n_rec.co_ppm)

    if not methane_values:
        return 0.0, 0.0

    return float(np.mean(methane_values)), float(np.mean(co_values))


def build_training_matrix(
    records: Sequence[GasRecord],
    topology: MineTopology,
    history_steps: int,
    horizons: Sequence[int],
):
    """
    Build supervised learning matrix for zone-level forecasting.

    Feature layout per row:
      - Own gas history (methane + co) for `history_steps`
      - Current ventilation level
      - Neighbor mean methane/co at current timestamp
      - Zone graph degree

    Targets per row:
      - methane at each horizon
      - co at each horizon
    """
    if history_steps < 2:
        raise ValueError("history_steps must be >= 2")
    if not horizons:
        raise ValueError("horizons must not be empty")

    zone_ts = _build_zone_series(records)
    zones = sorted(zone_ts.keys())
    all_timestamps = sorted({r.timestamp for r in records})
    max_horizon = max(horizons)

    X_rows: List[List[float]] = []
    y_rows: List[List[float]] = []
    sample_keys: List[Tuple[str, int]] = []

    feature_names = []
    for lag in range(history_steps):
        feature_names.append(f"methane_lag_{lag}")
        feature_names.append(f"co_lag_{lag}")
    feature_names.extend(
        [
            "ventilation_now",
            "neighbor_methane_now",
            "neighbor_co_now",
            "zone_degree",
        ]
    )

    target_names = [f"methane_t_plus_{h}" for h in horizons] + [f"co_t_plus_{h}" for h in horizons]

    for zone in zones:
        zone_data = zone_ts[zone]

        # Index along global timeline so all zones align on the same cadence.
        for idx in range(history_steps - 1, len(all_timestamps) - max_horizon):
            current_ts = all_timestamps[idx]
            if current_ts not in zone_data:
                continue

            lag_slice = all_timestamps[idx - history_steps + 1 : idx + 1]
            if any(ts not in zone_data for ts in lag_slice):
                continue

            future_timestamps = [all_timestamps[idx + h] for h in horizons]
            if any(ts not in zone_data for ts in future_timestamps):
                continue

            feats: List[float] = []
            # Most recent first for easier online alignment later.
            for ts in reversed(lag_slice):
                rec = zone_data[ts]
                feats.append(rec.methane_ppm)
                feats.append(rec.co_ppm)

            now_rec = zone_data[current_ts]
            n_methane, n_co = _neighbor_snapshot(topology, zone, current_ts, zone_ts)
            feats.append(now_rec.ventilation_level)
            feats.append(n_methane)
            feats.append(n_co)
            feats.append(float(topology.degree(zone)))

            targets = [zone_data[ts].methane_ppm for ts in future_timestamps]
            targets.extend([zone_data[ts].co_ppm for ts in future_timestamps])

            X_rows.append(feats)
            y_rows.append(targets)
            sample_keys.append((zone, current_ts))

    if not X_rows:
        raise ValueError("No trainable rows produced. Check horizons/history and data coverage.")

    X = np.asarray(X_rows, dtype=np.float64)
    y = np.asarray(y_rows, dtype=np.float64)
    return X, y, feature_names, target_names, sample_keys
