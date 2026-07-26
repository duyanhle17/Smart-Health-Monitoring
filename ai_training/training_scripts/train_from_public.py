"""
Train/validate exhaustion features trên DATASET SINH LÝ CÔNG KHAI  [dataset (b)]
==============================================================================
Nhận CSV do adapter xuất (pamap2_features.csv / wesad_features.csv) với cột:
    subject, t_sec, hr, temp, activity, label_score
Trượt cửa sổ theo subject -> trích ĐÚNG bộ đặc trưng exhaustion_features (khớp
production) -> nhãn = label_score (ĐỘC LẬP với PSI). Đánh giá bằng GroupKFold
THEO SUBJECT (train người này, test người khác) = kiểm tra tổng quát hoá thật.
So với BASELINE = công thức PSI để biết ML có thêm giá trị hay không.

Chạy:
  python ai_training/datasets/pamap2_adapter.py <pamap2_raw>
  python ai_training/training_scripts/train_from_public.py ai_training/data/pamap2_features.csv
"""

import os
import sys
import numpy as np
import pandas as pd
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

WINDOW_S = 60.0
STEP_S = 15.0
MIN_SAMPLES = 6
CFG = PhysiologyConfig()


def _num(v):
    try:
        v = float(v)
        return v if np.isfinite(v) else None
    except (TypeError, ValueError):
        return None


def build(df):
    X, y, groups, base = [], [], [], []
    for subj, g in df.groupby("subject"):
        g = g.sort_values("t_sec").reset_index(drop=True)
        ts = g["t_sec"].values.astype(float)
        loads = np.empty(len(g)); load = 0.0; last_hr = CFG.hr_rest
        prev = ts[0]
        for i in range(len(g)):
            dt = max(0.0, (ts[i] - prev) / 60.0); prev = ts[i]
            hv = _num(g["hr"].iloc[i]); last_hr = hv if hv is not None else last_hr
            load = update_fatigue_load(load, last_hr, dt, CFG); loads[i] = load
        recs = g.to_dict("records"); t0 = ts[0]
        t_end = ts[0] + WINDOW_S
        while t_end <= ts[-1] + 1e-6:
            idx = np.where((ts > t_end - WINDOW_S) & (ts <= t_end + 1e-6))[0]
            if idx.size >= MIN_SAMPLES:
                e = idx[-1]
                win = [{"t_min": (ts[j]-t0)/60.0, "hr": _num(recs[j]["hr"]),
                        "temp": _num(recs[j].get("temp")), "bp_map": None,
                        "activity": _num(recs[j].get("activity"))} for j in idx]
                vec, feat = extract_window_features(win, fatigue_load=float(loads[e]),
                                                    shift_duration_min=(ts[e]-t0)/60.0, cfg=CFG)
                X.append(vec)
                y.append(float(np.mean([_num(recs[j]["label_score"]) or 0.0 for j in idx])))
                groups.append(str(subj))
                base.append(exhaustion_score(
                    hr=feat["hr_mean"], temp=(feat["temp_mean"] if feat["temp_present"] else None),
                    fatigue_load=float(loads[e]), cfg=CFG))
            t_end += STEP_S
    return np.array(X), np.array(y), np.array(groups), np.array(base)


def main():
    if len(sys.argv) < 2:
        print("Dùng: train_from_public.py <features.csv>"); sys.exit(1)
    csv_path = sys.argv[1]
    df = pd.read_csv(csv_path)
    print(f"📂 {csv_path}: {len(df)} mẫu, {df['subject'].nunique()} subject")
    X, y, groups, base = build(df)
    print(f"🪟 {len(X)} cửa sổ ({WINDOW_S}s/{STEP_S}s), {X.shape[1] if len(X) else 0} đặc trưng")
    if len(X) < 20:
        print("⚠️  Quá ít cửa sổ để đánh giá."); return

    base_mae = mean_absolute_error(y, np.clip(base, 0, 10))
    # tương quan: label_score có gắn với công thức PSI không?
    print(f"\n📐 BASELINE (PSI) vs nhãn: MAE={base_mae:.3f}")

    uniq = np.unique(groups)
    n_splits = min(5, len(uniq)) if len(uniq) >= 2 else 2
    if len(uniq) < 2:
        print("Chỉ 1 subject -> không kiểm tra tổng quát hoá cross-subject được."); return
    gkf = GroupKFold(n_splits=n_splits)
    preds = np.zeros(len(X))
    for tr, te in gkf.split(X, y, groups):
        m = GradientBoostingRegressor(n_estimators=300, max_depth=3,
                                      learning_rate=0.05, subsample=0.8, random_state=42)
        m.fit(X[tr], y[tr]); preds[te] = np.clip(m.predict(X[te]), 0, 10)
    print(f"🤖 MODEL (GBR, {n_splits}-fold THEO SUBJECT) vs nhãn: "
          f"MAE={mean_absolute_error(y, preds):.3f}  R²={r2_score(y, preds):.3f}")

    full = GradientBoostingRegressor(n_estimators=300, max_depth=3,
                                     learning_rate=0.05, subsample=0.8, random_state=42).fit(X, y)
    imp = np.argsort(full.feature_importances_)[::-1]
    print("🔎 Top đặc trưng:", ", ".join(
        f"{FEATURE_NAMES[i]}={full.feature_importances_[i]:.2f}" for i in imp[:6]))


if __name__ == "__main__":
    main()
