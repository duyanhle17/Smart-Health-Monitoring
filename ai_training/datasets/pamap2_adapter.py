"""
PAMAP2 -> schema SafeWork (hr, temp, activity, nhãn cường độ)  [dataset (b)]
===========================================================================
PAMAP2 (UCI #231) là dữ liệu THẬT: nhịp tim (bpm) + nhiệt độ IMU (°C) + gia tốc,
gắn nhãn theo 12 hoạt động (nằm/ngồi/đứng/đi/chạy/leo cầu thang/nhảy dây...).
Ta lấy **cường độ hoạt động (MET)** làm nhãn exertion — nhãn NÀY ĐỘC LẬP với
công thức PSI, nên phá được vòng tự-tham-chiếu.

Định dạng .dat: cách nhau bằng khoảng trắng, 54 cột:
  col 0 = timestamp(s), 1 = activityID, 2 = heart rate(bpm),
  3 = nhiệt độ IMU bàn tay(°C), 4-6 = gia tốc ±16g bàn tay, ...
'NaN' = thiếu (HR chỉ ~9Hz, IMU 100Hz).

Xuất: ai_training/data/pamap2_features.csv  (subject,t_sec,hr,temp,activity,label_score,activity_id,met)
"""

import os
import glob
import sys
import numpy as np
import pandas as pd

# activityID -> MET (compendium hoạt động thể chất)
ACTIVITY_MET = {
    1: 1.0, 2: 1.3, 3: 1.8, 4: 3.3, 5: 8.0, 6: 6.8, 7: 5.5,
    9: 1.0, 10: 1.3, 11: 2.0, 12: 6.0, 13: 4.0,
    16: 3.3, 17: 2.3, 18: 2.0, 19: 3.5, 20: 7.0, 24: 10.0,
}
MET_MIN, MET_MAX = 1.0, 10.0


def met_to_score(met):
    return float(np.clip((met - MET_MIN) / (MET_MAX - MET_MIN) * 10.0, 0.0, 10.0))


def load_dat(path, subject, target_hz=1.0):
    """Đọc 1 file .dat -> DataFrame đã downsample về ~target_hz."""
    arr = np.genfromtxt(path, dtype=float)          # 'NaN' -> np.nan
    if arr.ndim != 2 or arr.shape[1] < 7:
        return pd.DataFrame()
    ts = arr[:, 0]
    act = arr[:, 1]
    hr = arr[:, 2]
    temp = arr[:, 3]                                 # nhiệt IMU bàn tay
    acc = np.linalg.norm(arr[:, 4:7], axis=1)        # |acc| (g)

    df = pd.DataFrame({"t_sec": ts, "activity_id": act, "hr": hr,
                       "temp": temp, "acc": acc})
    df = df[df["activity_id"] != 0]                  # bỏ transient
    df = df[df["activity_id"].isin(ACTIVITY_MET)]
    if df.empty:
        return df
    df["hr"] = df["hr"].ffill().bfill()             # HR thưa -> điền
    # downsample: PAMAP2 ~100Hz -> lấy mỗi (100/target_hz) dòng
    step = max(1, int(round(100.0 / target_hz)))
    df = df.iloc[::step].reset_index(drop=True)
    # activity 0-1 chuẩn hoá thô từ độ lệch |acc| quanh 1g
    df["activity"] = np.clip(np.abs(df["acc"] - 1.0) / 2.0, 0.0, 1.0)
    df["met"] = df["activity_id"].map(ACTIVITY_MET)
    df["label_score"] = df["met"].map(met_to_score)
    df["subject"] = subject
    return df[["subject", "t_sec", "hr", "temp", "activity",
               "label_score", "activity_id", "met"]]


def load_pamap2(root_dir, target_hz=1.0):
    """Gộp mọi Protocol/*.dat dưới root_dir."""
    paths = sorted(glob.glob(os.path.join(root_dir, "**", "Protocol", "*.dat"),
                             recursive=True))
    if not paths:
        paths = sorted(glob.glob(os.path.join(root_dir, "**", "*.dat"), recursive=True))
    frames = []
    for p in paths:
        subj = os.path.splitext(os.path.basename(p))[0]   # subject10x
        d = load_dat(p, subj, target_hz)
        if not d.empty:
            frames.append(d)
            print(f"  {subj}: {len(d)} mẫu @ {target_hz}Hz")
    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, ignore_index=True)


def main():
    root = sys.argv[1] if len(sys.argv) > 1 else \
        os.path.join("ai_training", "data", "pamap2_raw")
    out = os.path.join("ai_training", "data", "pamap2_features.csv")
    print(f"Đọc PAMAP2 từ {root} ...")
    df = load_pamap2(root)
    if df.empty:
        print("❌ Không thấy .dat nào. Kiểm tra đường dẫn / giải nén.")
        sys.exit(1)
    os.makedirs(os.path.dirname(out), exist_ok=True)
    df.to_csv(out, index=False)
    print(f"✅ {len(df)} mẫu, {df['subject'].nunique()} subject -> {out}")


if __name__ == "__main__":
    main()
