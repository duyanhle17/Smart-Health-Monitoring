"""
Train Gas Forecasting + Smart Routing Baseline
=============================================

Output artifact:
  - model/gas_forecast_bundle.pkl
  - model/gas_training_report.json

Usage:
  python model/gas_train.py \
      --gas-csv data/gas_training_sample.csv \
      --topology data/mine_topology_sample.json
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from typing import List

import joblib
import numpy as np
from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import mean_absolute_error, r2_score
from sklearn.model_selection import train_test_split
from sklearn.multioutput import MultiOutputRegressor

# Add project root for src imports.
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from src.gas.features import build_training_matrix, load_gas_csv
from src.gas.topology import MineTopology

DEFAULT_GAS_CSV = os.path.join("data", "gas_training_sample.csv")
DEFAULT_TOPOLOGY = os.path.join("data", "mine_topology_sample.json")
DEFAULT_BUNDLE = os.path.join("model", "gas_forecast_bundle.pkl")
DEFAULT_REPORT = os.path.join("model", "gas_training_report.json")


def _parse_horizons(raw: str) -> List[int]:
    items = [x.strip() for x in raw.split(",") if x.strip()]
    values = sorted({int(v) for v in items})
    if not values or any(v <= 0 for v in values):
        raise ValueError("horizons must be positive integers, e.g. 20,60")
    return values


def main() -> None:
    parser = argparse.ArgumentParser(description="Train gas forecasting baseline model")
    parser.add_argument("--gas-csv", default=DEFAULT_GAS_CSV, help="Input gas history CSV")
    parser.add_argument("--topology", default=DEFAULT_TOPOLOGY, help="Mine topology JSON")
    parser.add_argument("--history-steps", type=int, default=6, help="Lag steps used as features")
    parser.add_argument(
        "--horizons",
        default="20,60",
        help="Forecast horizons in time-steps (20~10m, 60~30m if sampling=30s)",
    )
    parser.add_argument("--output-bundle", default=DEFAULT_BUNDLE, help="Model bundle output path")
    parser.add_argument("--output-report", default=DEFAULT_REPORT, help="Training report output path")
    parser.add_argument("--test-size", type=float, default=0.2, help="Test split ratio")
    args = parser.parse_args()

    if not os.path.isfile(args.gas_csv):
        raise FileNotFoundError(
            f"Gas CSV not found: {args.gas_csv}. Create one or run tools/generate_gas_data.py first."
        )
    if not os.path.isfile(args.topology):
        raise FileNotFoundError(f"Topology JSON not found: {args.topology}")

    horizons = _parse_horizons(args.horizons)

    print("=" * 70)
    print("TRAIN GAS FORECASTING BASELINE")
    print("=" * 70)
    print(f"Gas CSV:       {args.gas_csv}")
    print(f"Topology:      {args.topology}")
    print(f"History steps: {args.history_steps}")
    print(f"Horizons:      {horizons}")

    topology = MineTopology.from_json(args.topology)
    records = load_gas_csv(args.gas_csv)

    X, y, feature_names, target_names, sample_keys = build_training_matrix(
        records=records,
        topology=topology,
        history_steps=args.history_steps,
        horizons=horizons,
    )

    X_train, X_test, y_train, y_test = train_test_split(
        X,
        y,
        test_size=args.test_size,
        random_state=42,
    )

    estimator = RandomForestRegressor(
        n_estimators=300,
        max_depth=18,
        min_samples_leaf=2,
        random_state=42,
        n_jobs=-1,
    )
    model = MultiOutputRegressor(estimator)
    model.fit(X_train, y_train)

    y_pred = model.predict(X_test)

    mae_per_target = {}
    r2_per_target = {}
    for i, name in enumerate(target_names):
        mae_per_target[name] = float(mean_absolute_error(y_test[:, i], y_pred[:, i]))
        r2_per_target[name] = float(r2_score(y_test[:, i], y_pred[:, i]))

    global_mae = float(mean_absolute_error(y_test, y_pred))

    print(f"Rows: train={len(X_train)}, test={len(X_test)}, features={X.shape[1]}")
    print(f"Global MAE: {global_mae:.4f}")
    print("Target metrics:")
    for name in target_names:
        print(f"  - {name:<20} MAE={mae_per_target[name]:.4f} | R2={r2_per_target[name]:.4f}")

    bundle = {
        "model": model,
        "metadata": {
            "feature_names": feature_names,
            "target_names": target_names,
            "horizons": horizons,
            "history_steps": args.history_steps,
            "zones": topology.zones,
            "topology": topology.to_dict(),
            "train_rows": int(len(X_train)),
            "test_rows": int(len(X_test)),
        },
    }

    os.makedirs(os.path.dirname(args.output_bundle), exist_ok=True)
    joblib.dump(bundle, args.output_bundle)

    report = {
        "global_mae": global_mae,
        "mae_per_target": mae_per_target,
        "r2_per_target": r2_per_target,
        "feature_count": len(feature_names),
        "target_count": len(target_names),
        "total_samples": len(sample_keys),
        "bundle_path": args.output_bundle,
    }

    os.makedirs(os.path.dirname(args.output_report), exist_ok=True)
    with open(args.output_report, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)

    print(f"\nSaved model bundle: {args.output_bundle}")
    print(f"Saved report:       {args.output_report}")
    print("=" * 70)


if __name__ == "__main__":
    main()
