"""
WESAD -> schema SafeWork (hr, temp, activity, nhãn)  [dataset (b)]
=================================================================
WESAD (UCI #465) khớp NHẤT với phần cứng worker: cổ tay Empatica E4 có PPG (BVP,
64Hz) ~ MAX30102, và NHIỆT ĐỘ DA thật (TEMP, 4Hz) ~ MAX30205. Nhãn trạng thái
(baseline/stress/amusement/meditation) ĐỘC LẬP với công thức PSI.

Mỗi subject là SX.pkl (pickle Python2 -> đọc encoding='latin1'):
  dict{ 'label'@700Hz, 'signal': {'wrist': {'BVP'@64, 'TEMP'@4, 'ACC'@32}, 'chest': {...}} }
  label: 1=baseline, 2=stress, 3=amusement, 4=meditation (0/5/6/7 = bỏ).

HR lấy từ BVP bằng peak-detection đơn giản (numpy, không cần scipy).
Xuất: ai_training/data/wesad_features.csv
"""

import os
import sys
import glob
import pickle
import numpy as np
import pandas as pd

LABEL_SCORE = {1: 1.0, 2: 7.0, 3: 2.5, 4: 0.5}   # strain proxy 0-10, độc lập PSI
BVP_HZ, TEMP_HZ, ACC_HZ, LABEL_HZ = 64, 4, 32, 700


def _bvp_hr(bvp, fs=BVP_HZ):
    """HR (bpm) từ một cửa sổ BVP: bandpass thô + đếm đỉnh, cách nhau >= 0.4s."""
    x = np.asarray(bvp, dtype=float).ravel()
    if x.size < fs * 3:
        return np.nan
    x = x - np.mean(x)
    # moving-average bandpass thô: (MA ngắn) - (MA dài)
    def ma(sig, n):
        n = max(1, int(n))
        k = np.ones(n) / n
        return np.convolve(sig, k, mode="same")
    band = ma(x, fs * 0.1) - ma(x, fs * 0.75)      # ~1.3-10 Hz đi qua
    thr = 0.5 * np.std(band)
    min_dist = int(0.4 * fs)                        # <=150 bpm
    peaks = []
    last = -min_dist
    for i in range(1, len(band) - 1):
        if band[i] > thr and band[i] >= band[i-1] and band[i] > band[i+1] and (i - last) >= min_dist:
            peaks.append(i); last = i
    if len(peaks) < 2:
        return np.nan
    ibi = np.diff(peaks) / fs                        # inter-beat interval (s)
    ibi = ibi[(ibi > 0.33) & (ibi < 1.5)]           # 40-180 bpm hợp lệ
    if ibi.size == 0:
        return np.nan
    return float(60.0 / np.median(ibi))


def load_subject(pkl_path, subject, win_s=8):
    with open(pkl_path, "rb") as f:
        d = pickle.load(f, encoding="latin1")
    wrist = d["signal"]["wrist"]
    bvp = np.asarray(wrist["BVP"], dtype=float).ravel()
    temp = np.asarray(wrist["TEMP"], dtype=float).ravel()
    acc = np.asarray(wrist["ACC"], dtype=float)
    label = np.asarray(d["label"]).ravel()

    dur_s = int(len(bvp) / BVP_HZ)
    rows = []
    for t in range(win_s, dur_s):                   # mỗi giây, cửa sổ win_s giây
        b = bvp[(t - win_s) * BVP_HZ: t * BVP_HZ]
        hr = _bvp_hr(b)
        tp = np.mean(temp[max(0, (t-1) * TEMP_HZ): t * TEMP_HZ]) if temp.size else np.nan
        aw = acc[max(0, (t-1) * ACC_HZ): t * ACC_HZ]
        act = float(np.clip(np.std(np.linalg.norm(aw, axis=1)) / 64.0, 0, 1)) if aw.size else 0.0
        lseg = label[max(0, (t-1) * LABEL_HZ): t * LABEL_HZ]
        if lseg.size == 0:
            continue
        lab = int(np.bincount(lseg.astype(int)).argmax())
        if lab not in LABEL_SCORE or not np.isfinite(hr):
            continue
        rows.append({"subject": subject, "t_sec": float(t), "hr": round(hr, 1),
                     "temp": round(float(tp), 3), "activity": round(act, 3),
                     "label_score": LABEL_SCORE[lab], "activity_id": lab, "met": np.nan})
    return pd.DataFrame(rows)


def load_wesad(root_dir):
    paths = sorted(glob.glob(os.path.join(root_dir, "**", "S*.pkl"), recursive=True))
    frames = []
    for p in paths:
        subj = os.path.splitext(os.path.basename(p))[0]
        try:
            d = load_subject(p, subj)
        except Exception as exc:
            print(f"  {subj}: lỗi {exc}"); continue
        if not d.empty:
            frames.append(d); print(f"  {subj}: {len(d)} mẫu 1Hz")
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def main():
    root = sys.argv[1] if len(sys.argv) > 1 else os.path.join("ai_training", "data", "wesad_raw")
    out = os.path.join("ai_training", "data", "wesad_features.csv")
    print(f"Đọc WESAD từ {root} ...")
    df = load_wesad(root)
    if df.empty:
        print("❌ Không thấy S*.pkl. Tải WESAD (UCI #465) rồi trỏ đường dẫn vào.")
        sys.exit(1)
    os.makedirs(os.path.dirname(out), exist_ok=True)
    df.to_csv(out, index=False)
    print(f"✅ {len(df)} mẫu, {df['subject'].nunique()} subject -> {out}")


if __name__ == "__main__":
    main()
