"""
Test Fall Detection Model on a single file
===========================================
Sử dụng:
    python model/test_fall.py data/mining_cases/case_011_ladder_fall.txt
"""

import sys
import os
import numpy as np
import joblib

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from src.fall.fall_features import (
    load_txt_file, sliding_window, extract_features,
    get_case_type, FALL_TYPES,
)

MODEL_PATH = "model/fall_model.pkl"


def main(txt_path):
    case_type = get_case_type(os.path.basename(txt_path))
    expected = "FALL" if case_type in FALL_TYPES else "NON-FALL"

    print(f"📂 File: {txt_path}")
    print(f"📌 Case type: {case_type} (Expected: {expected})")
    print()

    model = joblib.load(MODEL_PATH)
    data = load_txt_file(txt_path)
    windows = sliding_window(data, window_size=40, step=20)

    print(f"🔍 Total windows: {len(windows)}\n")

    fall_count = 0
    for i, w in enumerate(windows):
        feats = extract_features(w).reshape(1, -1)
        pred = model.predict(feats)[0]
        prob = model.predict_proba(feats)[0][1]

        label = "🔴 FALL" if pred == 1 else "🟢 SAFE"
        if pred == 1:
            fall_count += 1

        print(f"  Window {i+1:02d}: {label}  (prob={prob:.3f})")

    print(f"\n{'=' * 40}")
    print(f"FALL windows: {fall_count}/{len(windows)}")

    if fall_count >= 2:
        decision = "⚠️  FALL DETECTED"
    else:
        decision = "✅ SAFE"

    print(f"DECISION: {decision}")
    print(f"EXPECTED: {expected}")

    match = (fall_count >= 2 and expected == "FALL") or \
            (fall_count < 2 and expected == "NON-FALL")
    print(f"RESULT: {'✅ CORRECT' if match else '❌ WRONG'}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python model/test_fall.py <path_to_txt_file>")
        sys.exit(1)
    main(sys.argv[1])
