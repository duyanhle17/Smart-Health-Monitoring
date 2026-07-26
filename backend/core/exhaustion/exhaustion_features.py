"""
Exhaustion feature extraction  (SafeWork)
=========================================
Biến một CỬA SỔ mẫu sinh hiệu (vitals) thành vector đặc trưng cố định để
đưa vào model. Dùng CHUNG ở lúc train và lúc suy luận thời gian thực nên
train/serve luôn khớp nhau.

Mỗi mẫu (sample) là dict: {"t_min": float, "hr": ?, "temp": ?, "bp_map": ?,
"activity": ?}. Các kênh temp/bp/activity có thể thiếu (None/NaN) -> được
impute + cờ *_present để model biết kênh nào thực sự có.

fatigue_load (0-1) và shift_duration_min là TRẠNG THÁI cả ca, do bên gọi
duy trì (xem exhaustion_labels.update_fatigue_load) và truyền vào đây.
"""

import numpy as np
from backend.core.exhaustion.exhaustion_labels import (
    PhysiologyConfig, instantaneous_strain, hr_reserve_fraction,
)

FEATURE_NAMES = [
    "hr_mean", "hr_std", "hr_min", "hr_max", "hr_slope", "hr_last", "hr_reserve_mean",
    "temp_mean", "temp_max", "temp_slope", "temp_last", "temp_reserve_mean", "temp_present",
    "bp_map_mean", "bp_pp_mean", "bp_present",
    "activity_mean", "activity_present",
    "inst_strain", "fatigue_load", "shift_duration_min",
]
N_FEATURES = len(FEATURE_NAMES)


def _clean(values, times, valid):
    """Trả (arr_giá_trị_hợp_lệ, arr_thời_gian_tương_ứng) sau khi loại NaN/outlier."""
    v = np.asarray(values, dtype=float)
    t = np.asarray(times, dtype=float)
    lo, hi = valid
    m = np.isfinite(v) & (v >= lo) & (v <= hi)
    return v[m], t[m]


def _slope_per_min(v, t):
    """Độ dốc tuyến tính (đơn vị/phút). 0 nếu <2 điểm hoặc thời gian không đổi."""
    if v.size < 2 or (t.max() - t.min()) < 1e-6:
        return 0.0
    # least squares slope
    return float(np.polyfit(t, v, 1)[0])


def extract_window_features(window, fatigue_load=0.0, shift_duration_min=0.0,
                            cfg=PhysiologyConfig()):
    """
    window: list các sample dict theo thứ tự thời gian tăng dần.
    Trả về (np.ndarray shape (N_FEATURES,), dict tên->giá trị).
    """
    times = [s.get("t_min", i) for i, s in enumerate(window)]
    hr_raw   = [s.get("hr")       for s in window]
    tp_raw   = [s.get("temp")     for s in window]
    bp_raw   = [s.get("bp_map")   for s in window]
    act_raw  = [s.get("activity") for s in window]

    hr, hr_t = _clean(hr_raw, times, cfg.hr_valid)
    tp, tp_t = _clean(tp_raw, times, cfg.temp_valid)
    bp, bp_t = _clean(bp_raw, times, cfg.map_valid)
    act = np.asarray([a for a in act_raw if a is not None and np.isfinite(a)], dtype=float)

    f = {n: 0.0 for n in FEATURE_NAMES}

    # ---- Nhịp tim (bắt buộc phải có ít nhất vài mẫu) ----
    if hr.size:
        f["hr_mean"] = float(np.mean(hr))
        f["hr_std"]  = float(np.std(hr))
        f["hr_min"]  = float(np.min(hr))
        f["hr_max"]  = float(np.max(hr))
        f["hr_slope"] = _slope_per_min(hr, hr_t)
        f["hr_last"] = float(hr[-1])
        f["hr_reserve_mean"] = hr_reserve_fraction(float(np.mean(hr)), cfg)
    else:
        f["hr_mean"] = cfg.hr_rest
        f["hr_last"] = cfg.hr_rest

    # ---- Thân nhiệt bề mặt (MAX30205) ----
    if tp.size:
        f["temp_mean"] = float(np.mean(tp))
        f["temp_max"]  = float(np.max(tp))
        f["temp_slope"] = _slope_per_min(tp, tp_t)
        f["temp_last"] = float(tp[-1])
        f["temp_reserve_mean"] = min(1.0, max(0.0,
            (float(np.mean(tp)) - cfg.temp_rest) / (cfg.temp_max - cfg.temp_rest)))
        f["temp_present"] = 1.0
    else:
        f["temp_mean"] = cfg.temp_rest
        f["temp_max"]  = cfg.temp_rest
        f["temp_last"] = cfg.temp_rest

    # ---- Huyết áp (tuỳ chọn) ----
    if bp.size:
        f["bp_map_mean"] = float(np.mean(bp))
        # pulse pressure nếu có systolic/diastolic riêng; ở đây chỉ có MAP -> 0
        pp = [s.get("bp_pp") for s in window if s.get("bp_pp") is not None]
        f["bp_pp_mean"] = float(np.mean(pp)) if pp else 0.0
        f["bp_present"] = 1.0
    else:
        f["bp_map_mean"] = cfg.map_rest

    # ---- Mức vận động (tuỳ chọn: từ IMU/UWB speed) ----
    if act.size:
        f["activity_mean"] = float(np.mean(act))
        f["activity_present"] = 1.0

    # ---- Đặc trưng sinh lý tổng hợp ----
    strain = instantaneous_strain(
        hr=f["hr_mean"] if hr.size else None,
        temp=f["temp_mean"] if tp.size else None,
        bp_map=f["bp_map_mean"] if bp.size else None,
        cfg=cfg,
    )
    f["inst_strain"] = 0.0 if not np.isfinite(strain) else float(strain)
    f["fatigue_load"] = float(fatigue_load)
    f["shift_duration_min"] = float(shift_duration_min)

    vec = np.array([f[n] for n in FEATURE_NAMES], dtype=float)
    return vec, f
