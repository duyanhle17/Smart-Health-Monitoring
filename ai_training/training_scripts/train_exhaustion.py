"""
Train EXHAUSTION model  (SafeWork - Smart Health Monitoring)
============================================================
Đọc dữ liệu sinh lý đã sinh (exhaustion_raw.csv), REPLAY từng ca để tính
fatigue_load từ HR QUAN SÁT (đúng như lúc suy luận), trượt cửa sổ -> trích
đặc trưng (exhaustion_features) -> nhãn = true_score cuối cửa sổ. Huấn luyện
GradientBoostingRegressor dự đoán điểm kiệt sức 0-10; đánh giá cả sai số hồi
quy (MAE/RMSE/R²) lẫn độ chính xác phân cấp (NORMAL/MILD/MODERATE/SEVERE).

Chia train/test THEO CA (shift) để tránh rò rỉ giữa các cửa sổ liền kề.

Chạy:
    python ai_training/training_scripts/generate_exhaustion_data.py 80
    python ai_training/training_scripts/train_exhaustion.py
Xuất: backend/core/exhaustion/models/exhaustion_model.pkl
"""

import os
import sys
import numpy as np
import pandas as pd
import joblib
from sklearn.ensemble import GradientBoostingRegressor
from sklearn.metrics import (
    mean_absolute_error, mean_squared_error, r2_score,
    classification_report, confusion_matrix,
)

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
from backend.core.exhaustion.exhaustion_labels import (  # noqa: E402
    PhysiologyConfig, update_fatigue_load, score_to_level, LEVELS, LEVEL_THRESHOLDS,
)
from backend.core.exhaustion.exhaustion_features import (  # noqa: E402
    extract_window_features, FEATURE_NAMES,
)

RAW_CSV = os.path.join("ai_training", "data", "exhaustion_raw.csv")
MODEL_OUT = os.path.join("backend", "core", "exhaustion", "models", "exhaustion_model.pkl")
WINDOW_MIN = 5.0
STEP_MIN = 1.0
CFG = PhysiologyConfig()


def _clean_hr(v, last_good):
    lo, hi = CFG.hr_valid
    if v is not None and np.isfinite(v) and lo <= v <= hi:
        return v
    return last_good


def build_windows(df):
    """Trả X, y_score, groups(shift_id) từ toàn bộ ca."""
    X, y, groups = [], [], []
    for sid, g in df.groupby("shift_id"):
        g = g.sort_values("t_min").reset_index(drop=True)
        # ---- replay để có fatigue_load QUAN SÁT theo thời gian ----
        load = 0.0
        last_hr = CFG.hr_rest
        loads = np.empty(len(g))
        prev_t = float(g["t_min"].iloc[0])
        for i in range(len(g)):
            t = float(g["t_min"].iloc[i])
            dt = max(0.0, t - prev_t); prev_t = t
            last_hr = _clean_hr(g["hr"].iloc[i], last_hr)
            load = update_fatigue_load(load, last_hr, dt, CFG)
            loads[i] = load

        samples = g.to_dict("records")
        t_arr = g["t_min"].values
        # ---- trượt cửa sổ ----
        t_end = WINDOW_MIN
        t_last = float(t_arr[-1])
        while t_end <= t_last + 1e-9:
            lo = t_end - WINDOW_MIN
            idx = np.where((t_arr > lo - 1e-9) & (t_arr <= t_end + 1e-9))[0]
            if idx.size >= 5:
                end_i = idx[-1]
                window = [{"t_min": float(samples[j]["t_min"]),
                           "hr": samples[j]["hr"],
                           "temp": samples[j]["temp"] if pd.notna(samples[j]["temp"]) else None,
                           "bp_map": samples[j]["bp_map"] if pd.notna(samples[j]["bp_map"]) else None,
                           "activity": samples[j]["activity"]} for j in idx]
                vec, _ = extract_window_features(
                    window, fatigue_load=float(loads[end_i]),
                    shift_duration_min=float(t_arr[end_i]), cfg=CFG)
                X.append(vec)
                y.append(float(g["true_score"].iloc[end_i]))
                groups.append(int(sid))
            t_end += STEP_MIN
    return np.array(X), np.array(y), np.array(groups)


def main():
    if not os.path.exists(RAW_CSV):
        print(f"❌ Chưa có {RAW_CSV}. Chạy generate_exhaustion_data.py trước.")
        sys.exit(1)

    print("=" * 60)
    print("💪 TRAIN EXHAUSTION MODEL - SafeWork")
    print("=" * 60)
    df = pd.read_csv(RAW_CSV)
    print(f"📂 {len(df)} mẫu thô, {df['shift_id'].nunique()} ca")

    X, y, groups = build_windows(df)
    print(f"🪟 {len(X)} cửa sổ | {X.shape[1]} đặc trưng "
          f"(WINDOW={WINDOW_MIN}min, STEP={STEP_MIN}min)")

    # ---- chia train/test THEO CA ----
    uniq = np.unique(groups)
    rng = np.random.default_rng(42)
    rng.shuffle(uniq)
    n_test = max(1, int(0.25 * len(uniq)))
    test_shifts = set(uniq[:n_test].tolist())
    te = np.array([g in test_shifts for g in groups])
    tr = ~te
    print(f"🔀 Train {tr.sum()} cửa sổ / {len(uniq)-n_test} ca | "
          f"Test {te.sum()} cửa sổ / {n_test} ca")

    model = GradientBoostingRegressor(
        n_estimators=300, max_depth=3, learning_rate=0.05,
        subsample=0.8, random_state=42,
    )
    model.fit(X[tr], y[tr])

    pred = np.clip(model.predict(X[te]), 0, 10)
    mae = mean_absolute_error(y[te], pred)
    rmse = math_sqrt(mean_squared_error(y[te], pred))
    r2 = r2_score(y[te], pred)
    print(f"\n📈 Hồi quy điểm 0-10:  MAE={mae:.3f}  RMSE={rmse:.3f}  R²={r2:.3f}")

    # ---- quy về cấp độ để báo cáo phân loại ----
    y_lvl = np.array([score_to_level(v) for v in y[te]])
    p_lvl = np.array([score_to_level(v) for v in pred])
    labs = sorted(set(y_lvl.tolist()) | set(p_lvl.tolist()))
    print("\n📋 Phân cấp (suy từ điểm dự đoán):")
    print(classification_report(y_lvl, p_lvl, labels=labs,
                                target_names=[LEVELS[i] for i in labs], digits=3,
                                zero_division=0))
    print("📉 Confusion matrix (hàng=thật, cột=dự đoán):", [LEVELS[i] for i in labs])
    print(confusion_matrix(y_lvl, p_lvl, labels=labs))

    # ---- feature importance ----
    imp = model.feature_importances_
    order = np.argsort(imp)[::-1]
    print("\n🔎 Top đặc trưng:")
    for i in order[:8]:
        print(f"   {FEATURE_NAMES[i]:<22} {imp[i]:.3f}")

    # ---- lưu bundle ----
    os.makedirs(os.path.dirname(MODEL_OUT), exist_ok=True)
    bundle = {
        "model": model,
        "feature_names": FEATURE_NAMES,
        "cfg": CFG,
        "window_min": WINDOW_MIN,
        "step_min": STEP_MIN,
        "level_thresholds": LEVEL_THRESHOLDS,
        "levels": LEVELS,
        "metrics": {"mae": mae, "rmse": rmse, "r2": r2},
    }
    joblib.dump(bundle, MODEL_OUT)
    print(f"\n✅ Đã lưu model -> {MODEL_OUT}")
    print("=" * 60)


def math_sqrt(x):
    return float(np.sqrt(x))


if __name__ == "__main__":
    main()
