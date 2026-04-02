import sys
import numpy as np
import joblib

from backend.core.fall.fall_features import load_txt_file, sliding_window, extract_features

MODEL_PATH = "ai_training/training_scripts/fall_model.pkl"

def main(txt_path):
    print(f"📂 Testing file: {txt_path}")

    model = joblib.load(MODEL_PATH)
    data = load_txt_file(txt_path)

    windows = sliding_window(data, window_size=400, step=200)

    print(f"🔍 Total windows: {len(windows)}\n")

    fall_count = 0

    for i, w in enumerate(windows):
        feats = extract_features(w).reshape(1, -1)
        pred = model.predict(feats)[0]
        prob = model.predict_proba(feats)[0][1]

        label = "FALL" if pred == 1 else "SAFE"

        if pred == 1:
            fall_count += 1

        print(f"Window {i+1:02d}: {label} (prob={prob:.2f})")

    print("\n====================")
    print(f"Total FALL windows: {fall_count}/{len(windows)}")

    if fall_count >= 2:
        print("⚠️ FINAL DECISION: FALL DETECTED")
    else:
        print("✅ FINAL DECISION: SAFE")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python test_fall_on_file.py path/to/file.txt")
        sys.exit(1)

    main(sys.argv[1])
