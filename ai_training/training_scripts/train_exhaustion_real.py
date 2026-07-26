"""
Train EXHAUSTION model trên NHÃN THẬT (Borg RPE)  -  SafeWork
============================================================
Khác hẳn train_exhaustion.py (nhãn = công thức PSI, tự tham chiếu): script này
dùng nhãn Borg RPE do người vận hành nhập qua dashboard (POST /api/exhaustion/
label -> exhaustion_rpe_labels.csv) làm GROUND TRUTH ĐỘC LẬP, ghép với luồng
vitals thật (vitals_history.csv).

  target = (RPE - 6) / 14 * 10        # RPE 6..20  ->  điểm kiệt sức 0..10

Đánh giá TRUNG THỰC:
  * chia theo NHÓM (worker; nếu chỉ 1 worker thì theo NGÀY) -> không rò rỉ.
  * so với BASELINE = công thức PSI. Chỉ lưu model nếu ML thắng baseline; nếu
    không, khuyến nghị dùng thẳng công thức (exhaustion_state fallback).

Chạy:
  SAFEWORK_DATA_DIR=backend/data python ai_training/training_scripts/train_exhaustion_real.py
Xuất (nếu đủ dữ liệu & thắng baseline):
  backend/core/exhaustion/models/exhaustion_model_real.pkl
"""

import os
import sys
import numpy as np
import pandas as pd
import joblib
from sklearn.ensemble import GradientBoostingRegressor
from sklearn.model_selection import GroupKFold
from sklearn.metrics import mean_absolute_error, r2_score

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
from backend.core.exhaustion.exhaustion_labels import (  # noqa: E402
    PhysiologyConfig, update_fatigue_load, exhaustion_score,
)
from backend.core.exhaustion.exhaustion_features import (  # noqa: E402
    extract_window_features, FEATURE_NAMES,
)

DATA_DIR = os.environ.get("SAFEWORK_DATA_DIR", os.path.join("backend", "data"))
VITALS_CSV = os.path.join(DATA_DIR, "vitals_history.csv")
LABELS_CSV = os.path.join(DATA_DIR, "exhaustion_rpe_labels.csv")
MODEL_OUT = os.path.join("backend", "core", "exhaustion", "models", "exhaustion_model_real.pkl")
WINDOW_MIN = 5.0
MIN_SAMPLES = 6
MIN_LABELS = 20
CFG = PhysiologyConfig()


def rpe_to_score(rpe):
    return float(np.clip((rpe - 6.0) / 14.0 * 10.0, 0.0, 10.0))


def _clean_hr(v, last):
    lo, hi = CFG.hr_valid
    try:
        v = float(v)
    except (TypeError, ValueError):
        return last
    return v if (np.isfinite(v) and lo <= v <= hi) else last


def _num(v):
    try:
        v = float(v)
        return v if np.isfinite(v) else None
    except (TypeError, ValueError):
        return None


def build_dataset(vitals, labels):
    """Trả X, y, groups, baseline_pred cho mỗi nhãn ghép được với cửa sổ vitals."""
    X, y, groups, baseline = [], [], [], []
    for wid, wl in labels.groupby("worker_id"):
        v = vitals[vitals["worker_id"] == wid].sort_values("timestamp").reset_index(drop=True)
        if v.empty:
            continue
        ts_arr = v["timestamp"].values.astype(float)
        # replay fatigue_load theo toàn bộ vitals của worker
        loads = np.empty(len(v)); load = 0.0; last_hr = CFG.hr_rest
        prev_t = ts_arr[0]
        for i in range(len(v)):
            dt = max(0.0, (ts_arr[i] - prev_t) / 60.0); prev_t = ts_arr[i]
            last_hr = _clean_hr(v["hr"].iloc[i], last_hr)
            load = update_fatigue_load(load, last_hr, dt, CFG)
            loads[i] = load
        recs = v.to_dict("records")
        first_ts = ts_arr[0]

        for _, lab in wl.iterrows():
            t = float(lab["timestamp"])
            idx = np.where((ts_arr > t - WINDOW_MIN * 60.0) & (ts_arr <= t + 1e-6))[0]
            if idx.size < MIN_SAMPLES:
                continue
            end_i = idx[-1]
            window = [{"t_min": (ts_arr[j] - first_ts) / 60.0,
                       "hr": _num(recs[j]["hr"]),
                       "temp": _num(recs[j].get("temp")),
                       "bp_map": _num(recs[j].get("bp_map")),
                       "activity": _num(recs[j].get("activity"))} for j in idx]
            vec, feat = extract_window_features(
                window, fatigue_load=float(loads[end_i]),
                shift_duration_min=(ts_arr[end_i] - first_ts) / 60.0, cfg=CFG)
            X.append(vec)
            y.append(rpe_to_score(float(lab["rpe"])))
            groups.append(str(wid))
            # baseline = công thức PSI trên trung bình cửa sổ + load quan sát
            baseline.append(exhaustion_score(
                hr=feat["hr_mean"], temp=(feat["temp_mean"] if feat["temp_present"] else None),
                bp_map=(feat["bp_map_mean"] if feat["bp_present"] else None),
                fatigue_load=float(loads[end_i]), cfg=CFG))
    return np.array(X), np.array(y), np.array(groups), np.array(baseline)


def main():
    if not (os.path.exists(VITALS_CSV) and os.path.exists(LABELS_CSV)):
        print(f"❌ Chưa có dữ liệu.\n   vitals: {VITALS_CSV}\n   labels: {LABELS_CSV}")
        print("   -> Chạy hệ thống live, bấm 'RPE' trên dashboard để tích nhãn trước.")
        sys.exit(1)

    vitals = pd.read_csv(VITALS_CSV)
    labels = pd.read_csv(LABELS_CSV)
    print(f"📂 {len(vitals)} dòng vitals | {len(labels)} nhãn RPE | "
          f"{labels['worker_id'].nunique()} worker")

    X, y, groups, baseline = build_dataset(vitals, labels)
    print(f"🔗 Ghép được {len(X)} nhãn với cửa sổ vitals (>= {MIN_SAMPLES} mẫu)")
    if len(X) < MIN_LABELS:
        print(f"⚠️  Cần >= {MIN_LABELS} nhãn ghép được để train đáng tin (đang có {len(X)}).")
        print("   Vẫn tính baseline để tham khảo, nhưng chưa lưu model.")

    base_mae = mean_absolute_error(y, np.clip(baseline, 0, 10)) if len(X) else float("nan")
    print(f"\n📐 BASELINE (công thức PSI) vs RPE: MAE={base_mae:.3f}")

    if len(X) < 8:
        print("Không đủ dữ liệu để cross-validate model. Dừng ở baseline.")
        return

    # nhóm theo worker; nếu chỉ 1 nhóm -> theo NGÀY
    uniq = np.unique(groups)
    if len(uniq) < 2:
        # gán nhóm theo ngày từ timestamp của nhãn (đã ghép cùng thứ tự với X)
        day = (labels.sort_values(["worker_id", "timestamp"])
               ["timestamp"].values // 86400).astype(int)
        # an toàn độ dài
        groups = day[:len(X)] if len(day) >= len(X) else np.arange(len(X)) % 3
        uniq = np.unique(groups)
    n_splits = min(5, max(2, len(uniq)))
    gkf = GroupKFold(n_splits=n_splits)

    preds = np.zeros(len(X))
    for tr, te in gkf.split(X, y, groups):
        m = GradientBoostingRegressor(n_estimators=250, max_depth=3,
                                      learning_rate=0.05, subsample=0.8, random_state=42)
        m.fit(X[tr], y[tr])
        preds[te] = np.clip(m.predict(X[te]), 0, 10)

    model_mae = mean_absolute_error(y, preds)
    model_r2 = r2_score(y, preds)
    print(f"🤖 MODEL (GBR, {n_splits}-fold theo nhóm) vs RPE: "
          f"MAE={model_mae:.3f}  R²={model_r2:.3f}")

    if model_mae < base_mae - 0.05 and len(X) >= MIN_LABELS:
        final = GradientBoostingRegressor(n_estimators=250, max_depth=3,
                                          learning_rate=0.05, subsample=0.8, random_state=42)
        final.fit(X, y)
        os.makedirs(os.path.dirname(MODEL_OUT), exist_ok=True)
        joblib.dump({"model": final, "feature_names": FEATURE_NAMES, "cfg": CFG,
                     "window_min": WINDOW_MIN, "trained_on": "real_rpe",
                     "n_labels": int(len(X)),
                     "cv_mae": model_mae, "baseline_mae": base_mae}, MODEL_OUT)
        print(f"\n✅ Model THẮNG baseline -> lưu {MODEL_OUT}")
        print("   (Đổi tên thành exhaustion_model.pkl để đưa vào production.)")
    else:
        print("\n➖ Model CHƯA thắng baseline rõ rệt -> nên dùng thẳng công thức PSI")
        print("   (exhaustion_state.py đã tự fallback công thức khi không có model).")


if __name__ == "__main__":
    main()
