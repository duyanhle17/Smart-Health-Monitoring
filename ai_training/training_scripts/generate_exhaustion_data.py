"""
Sinh dữ liệu huấn luyện EXHAUSTION theo sinh lý  (SafeWork)
==========================================================
Không có dữ liệu kiệt sức gắn nhãn thật, nên ta mô phỏng nhiều ca làm việc:
mỗi ca gồm các pha nghỉ / đi lại / làm vừa / làm nặng / phơi nhiệt, sinh ra
nhịp tim + thân nhiệt (+ huyết áp tuỳ chọn) theo mô hình động học bậc nhất
có trôi tim (cardiac drift) khi mệt. NHÃN (true_score/true_level) tính bằng
lõi sinh lý trong exhaustion_labels trên tín hiệu SẠCH; còn cột quan sát
(hr/temp/bp) là tín hiệu CÓ nhiễu + rớt mẫu + outlier để model học chịu nhiễu.

Phản ánh phần cứng hiện tại:
  * mọi ca đều có HR (MAX30102);
  * ~80% ca có thân nhiệt (MAX30205);
  * chỉ ~15% ca có huyết áp (giả lập trường hợp lắp thêm cảm biến BP).

Chạy:
    python ai_training/training_scripts/generate_exhaustion_data.py [n_shifts]
Xuất: ai_training/data/exhaustion_raw.csv
"""

import os
import sys
import csv
import math
import numpy as np

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
from backend.core.exhaustion.exhaustion_labels import (  # noqa: E402
    PhysiologyConfig, exhaustion_score, score_to_level, update_fatigue_load,
)

OUT_CSV = os.path.join("ai_training", "data", "exhaustion_raw.csv")
SAMPLE_DT_MIN = 0.1            # 6 giây / mẫu
CFG = PhysiologyConfig()

# Thư viện pha: (tên, cường độ vận động 0-1, nhiệt môi trường 0-1, phút_min, phút_max)
PHASES = [
    ("rest",       0.05, 0.1, 3, 10),
    ("walk",       0.35, 0.2, 4, 12),
    ("moderate",   0.55, 0.35, 5, 15),
    ("heavy",      0.80, 0.45, 5, 18),
    ("heavy_hot",  0.85, 0.85, 6, 20),
    ("recover",    0.15, 0.25, 3, 10),
]


def _lag(prev, target, dt_min, tau_min):
    """Động học bậc nhất: prev tiến về target với hằng số thời gian tau_min."""
    alpha = 1.0 - math.exp(-dt_min / tau_min)
    return prev + alpha * (target - prev)


def simulate_shift(rng, shift_id, has_temp, has_bp):
    # cá nhân hoá baseline theo từng worker
    hr_rest = rng.uniform(58, 74)
    hr_max = rng.uniform(180, 198)
    temp_rest = rng.uniform(33.8, 35.2)
    map_rest = rng.uniform(82, 96)

    # dựng chuỗi pha ngẫu nhiên cho ca (6-12 pha)
    n_phases = rng.integers(6, 13)
    plan = []
    for _ in range(n_phases):
        name, a, h, pmin, pmax = PHASES[rng.integers(0, len(PHASES))]
        dur = rng.uniform(pmin, pmax)
        plan.append((a, h, dur))

    rows = []
    hr = hr_rest
    temp = temp_rest
    bpm = map_rest
    load = 0.0
    t_min = 0.0
    # xác suất rớt mẫu theo từng đoạn (mô phỏng chập chờn I2C)
    dropout_temp = rng.uniform(0.0, 0.06)
    dropout_bp = rng.uniform(0.0, 0.10)

    for (a, h, dur) in plan:
        n = int(dur / SAMPLE_DT_MIN)
        for _ in range(n):
            # --- tín hiệu SẠCH (ground truth) ---
            # trôi tim: khi load cao, cùng cường độ nhưng HR nền cao hơn
            drift = 0.12 * load
            hr_target = hr_rest + (hr_max - hr_rest) * (0.15 + 0.70 * a + 0.10 * h + drift)
            hr = _lag(hr, hr_target, SAMPLE_DT_MIN, tau_min=0.5)   # tim đáp nhanh (~30s)

            temp_target = temp_rest + (CFG.temp_max - temp_rest) * (0.08 + 0.55 * a + 0.55 * h)
            temp = _lag(temp, temp_target, SAMPLE_DT_MIN, tau_min=8.0)  # nhiệt chậm

            # huyết áp: tăng theo gắng sức, nhưng TỤT khi nhiệt cao + mệt nặng
            map_target = map_rest + (CFG.map_max - map_rest) * (0.10 + 0.45 * a)
            if h > 0.6 and load > 0.6:
                map_target -= 22.0 * (load - 0.6)   # hạ huyết áp do kiệt sức nhiệt
            bpm = _lag(bpm, map_target, SAMPLE_DT_MIN, tau_min=2.0)

            load = update_fatigue_load(load, hr, SAMPLE_DT_MIN, CFG)

            score = exhaustion_score(hr=hr, temp=temp,
                                     bp_map=(bpm if has_bp else None),
                                     fatigue_load=load, cfg=CFG)
            level = score_to_level(score)

            # --- tín hiệu QUAN SÁT (nhiễu + rớt mẫu + outlier) ---
            hr_obs = hr + rng.normal(0, 2.5)
            if rng.random() < 0.003:                      # outlier hiếm (kiểu HR=2000)
                hr_obs = rng.choice([rng.uniform(5, 25), rng.uniform(240, 2000)])
            temp_obs = ""
            if has_temp and rng.random() > dropout_temp:
                temp_obs = round(temp + rng.normal(0, 0.12), 3)
            bp_obs = ""
            if has_bp and rng.random() > dropout_bp:
                bp_obs = round(bpm + rng.normal(0, 3.5), 2)
            activity_obs = round(max(0.0, a + rng.normal(0, 0.05)), 3)  # từ IMU/UWB speed

            rows.append([
                shift_id, round(t_min, 3),
                round(hr_obs, 2), temp_obs, bp_obs, activity_obs,
                round(score, 4), level,
            ])
            t_min += SAMPLE_DT_MIN
    return rows


def main():
    n_shifts = int(sys.argv[1]) if len(sys.argv) > 1 else 60
    rng = np.random.default_rng(42)
    os.makedirs(os.path.dirname(OUT_CSV), exist_ok=True)

    total = 0
    with open(OUT_CSV, "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["shift_id", "t_min", "hr", "temp", "bp_map",
                    "activity", "true_score", "true_level"])
        for sid in range(n_shifts):
            has_temp = rng.random() < 0.80
            has_bp = rng.random() < 0.15
            rows = simulate_shift(rng, sid, has_temp, has_bp)
            w.writerows(rows)
            total += len(rows)

    print(f"✅ Sinh {n_shifts} ca, {total} mẫu -> {OUT_CSV}")


if __name__ == "__main__":
    main()
