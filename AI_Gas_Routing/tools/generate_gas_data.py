"""Generate synthetic gas time-series data for training baseline models."""

from __future__ import annotations

import argparse
import csv
import os
import random
from typing import Dict, List


def _default_zones() -> List[str]:
    return ["Z1", "Z2", "Z3", "Z4", "Z5", "Z6"]


def _adjacency() -> Dict[str, List[str]]:
    return {
        "Z1": ["Z2"],
        "Z2": ["Z1", "Z3", "Z5"],
        "Z3": ["Z2", "Z4"],
        "Z4": ["Z3", "Z6"],
        "Z5": ["Z2", "Z6"],
        "Z6": ["Z4", "Z5"],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate synthetic gas telemetry CSV")
    parser.add_argument("--output", default="data/gas_training_sample.csv")
    parser.add_argument("--steps", type=int, default=720, help="Number of time steps")
    parser.add_argument("--sample-seconds", type=int, default=30)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    random.seed(args.seed)
    zones = _default_zones()
    graph = _adjacency()

    methane = {z: 0.5 + random.random() * 0.5 for z in zones}
    co = {z: 2.0 + random.random() * 1.0 for z in zones}
    vent = {z: 0.55 + random.random() * 0.25 for z in zones}

    os.makedirs(os.path.dirname(args.output), exist_ok=True)

    with open(args.output, "w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["timestamp", "zone_id", "methane_ppm", "co_ppm", "ventilation_level"])

        ts = 0
        for step in range(args.steps):
            leak_zone = "Z3" if 220 <= step <= 320 else ("Z5" if 500 <= step <= 580 else None)

            new_methane = {}
            new_co = {}

            for z in zones:
                neighbors = graph[z]
                m_neighbors = sum(methane[n] for n in neighbors) / len(neighbors)
                co_neighbors = sum(co[n] for n in neighbors) / len(neighbors)

                local_shock = 0.0
                if leak_zone == z:
                    local_shock = random.uniform(0.8, 1.8)
                elif leak_zone in neighbors:
                    local_shock = random.uniform(0.2, 0.6)

                vent[z] = max(0.2, min(1.0, vent[z] + random.uniform(-0.03, 0.03)))

                new_methane[z] = (
                    0.65 * methane[z]
                    + 0.20 * m_neighbors
                    + 0.30 * local_shock
                    - 0.15 * vent[z]
                    + random.uniform(-0.03, 0.03)
                )
                new_co[z] = (
                    0.70 * co[z]
                    + 0.15 * co_neighbors
                    + 1.40 * local_shock
                    - 0.30 * vent[z]
                    + random.uniform(-0.08, 0.08)
                )

                new_methane[z] = max(0.0, min(8.0, new_methane[z]))
                new_co[z] = max(0.0, min(120.0, new_co[z]))

            methane = new_methane
            co = new_co

            for z in zones:
                writer.writerow([ts, z, round(methane[z], 4), round(co[z], 4), round(vent[z], 4)])

            ts += args.sample_seconds

    print(f"Synthetic gas dataset generated: {args.output}")


if __name__ == "__main__":
    main()
