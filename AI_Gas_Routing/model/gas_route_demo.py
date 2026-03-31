"""Demo inference + smart routing using trained gas model bundle."""

from __future__ import annotations

import argparse
import csv
import os
import sys
from collections import defaultdict
from typing import Dict, List, Tuple

import joblib
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from src.gas.routing import compute_safest_path
from src.gas.topology import MineTopology


def _build_feature_for_zone(
    zone: str,
    history: Dict[str, List[Tuple[float, float, float]]],
    neighbors: List[str],
    degree: int,
    history_steps: int,
) -> np.ndarray:
    seq = history.get(zone, [])
    if len(seq) < history_steps:
        raise ValueError(f"Not enough history for zone {zone}")

    feats: List[float] = []
    recent = seq[-history_steps:]

    for methane, co, _vent in reversed(recent):
        feats.append(methane)
        feats.append(co)

    vent_now = recent[-1][2]

    n_methane = []
    n_co = []
    for n in neighbors:
        n_seq = history.get(n, [])
        if not n_seq:
            continue
        n_methane.append(n_seq[-1][0])
        n_co.append(n_seq[-1][1])

    feats.append(vent_now)
    feats.append(float(np.mean(n_methane)) if n_methane else 0.0)
    feats.append(float(np.mean(n_co)) if n_co else 0.0)
    feats.append(float(degree))

    return np.asarray(feats, dtype=np.float64)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run gas forecast + safest route demo")
    parser.add_argument("--bundle", default="model/gas_forecast_bundle.pkl")
    parser.add_argument("--gas-csv", default="data/gas_training_sample.csv")
    parser.add_argument("--start-zone", default="Z3")
    parser.add_argument("--exit-zones", default="Z1,Z6")
    parser.add_argument("--methane-alert", type=float, default=3.0)
    parser.add_argument("--co-alert", type=float, default=35.0)
    args = parser.parse_args()

    payload = joblib.load(args.bundle)
    model = payload["model"]
    metadata = payload["metadata"]

    history_steps = int(metadata["history_steps"])
    # Rebuild edge list from serialized topology.
    edge_rows = metadata["topology"]["edges"]
    from src.gas.topology import TunnelEdge  # local import to keep file focused

    topology = MineTopology(
        zones=metadata["topology"]["zones"],
        edges=[
            TunnelEdge(e["source"], e["target"], float(e.get("distance_m", 1.0)))
            for e in edge_rows
        ],
    )

    # Build short history per zone from CSV.
    zone_history: Dict[str, List[Tuple[float, float, float]]] = defaultdict(list)
    with open(args.gas_csv, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for r in reader:
            zone = r["zone_id"]
            zone_history[zone].append(
                (
                    float(r["methane_ppm"]),
                    float(r["co_ppm"]),
                    float(r["ventilation_level"]),
                )
            )

    zone_risk: Dict[str, float] = {}
    blocked = []

    for zone in topology.zones:
        feature = _build_feature_for_zone(
            zone=zone,
            history=zone_history,
            neighbors=[n for n, _ in topology.neighbors(zone)],
            degree=topology.degree(zone),
            history_steps=history_steps,
        )
        pred = model.predict(feature.reshape(1, -1))[0]

        horizons = metadata["horizons"]
        methane_pred = pred[: len(horizons)]
        co_pred = pred[len(horizons) :]

        methane_peak = float(np.max(methane_pred))
        co_peak = float(np.max(co_pred))

        risk = (methane_peak / max(args.methane_alert, 1e-6)) + (co_peak / max(args.co_alert, 1e-6))
        zone_risk[zone] = risk

        if methane_peak >= args.methane_alert * 1.5 or co_peak >= args.co_alert * 1.5:
            blocked.append(zone)

    exit_zones = [x.strip() for x in args.exit_zones.split(",") if x.strip()]
    path, cost = compute_safest_path(
        topology=topology,
        start_zone=args.start_zone,
        exit_zones=exit_zones,
        zone_risk=zone_risk,
        blocked_zones=blocked,
        distance_weight=1.0,
        risk_weight=12.0,
    )

    print("Forecasted zone risk:")
    for zone in sorted(zone_risk):
        marker = "BLOCKED" if zone in blocked else ""
        print(f"  - {zone}: risk={zone_risk[zone]:.3f} {marker}")

    print("\nSuggested evacuation route:")
    if not path:
        print("  No safe path found")
    else:
        print(f"  Path: {' -> '.join(path)}")
        print(f"  Cost: {cost:.3f}")


if __name__ == "__main__":
    main()
