"""
Exhaustion physiology core  (SafeWork - Smart Health Monitoring)
================================================================
Định nghĩa chỉ số kiệt sức (exhaustion) dựa trên SINH LÝ, dùng chung cho:
  - bộ sinh dữ liệu huấn luyện  (ai_training/.../generate_exhaustion_data.py)
  - bộ trích đặc trưng          (exhaustion_features.py)
  - suy luận thời gian thực     (exhaustion_state.py)

Nền tảng: Physiological Strain Index (PSI, Moran et al. 1998) mở rộng:
    PSI = 5·(HRt-HR0)/(HRmax-HR0) + 5·(Tc,t-Tc,0)/(Tc,max-Tc,0)   ∈ [0,10]
Ở đây tổng quát hoá thành tổ hợp có trọng số của các kênh SẴN CÓ
(nhịp tim + thân nhiệt + huyết áp tuỳ chọn), cộng thêm thành phần
"mệt mỏi tích luỹ" (accumulated load, kiểu TRIMP) để phản ánh việc kiệt
sức dồn lại theo ca làm, có hồi phục khi nghỉ.

LƯU Ý PHẦN CỨNG:
  * MAX30102 -> nhịp tim (bpm).            (có trên worker hiện tại)
  * MAX30205 -> thân nhiệt BỀ MẶT da (°C). (có trên worker hiện tại)
      Đây KHÔNG phải nhiệt độ lõi trực tràng; ngưỡng dưới đây đặt cho nhiệt
      độ bề mặt đo ở thái dương/trán dưới mũ. Hiệu chỉnh theo từng người khi
      commissioning.
  * Huyết áp (MAP) -> TUỲ CHỌN. Worker hiện chưa có cảm biến huyết áp, nên
      mặc định kênh này vắng mặt; model vẫn chạy tốt với temp + HR.
"""

from dataclasses import dataclass
import math

LEVELS = ["NORMAL", "MILD", "MODERATE", "SEVERE"]
# Điểm exhaustion (0-10) -> cấp độ. NORMAL<3, MILD<5, MODERATE<7, còn lại SEVERE.
LEVEL_THRESHOLDS = (3.0, 5.0, 7.0)


@dataclass
class PhysiologyConfig:
    # --- Nhịp tim (bpm) ---
    hr_rest: float = 65.0        # nhịp nghỉ baseline (có thể học riêng từng người)
    hr_max: float = 190.0        # nhịp tối đa (~220 - tuổi)
    # --- Thân nhiệt bề mặt (°C, MAX30205) ---
    temp_rest: float = 34.5
    temp_max: float = 38.5
    # --- Huyết áp trung bình MAP (mmHg), TUỲ CHỌN ---
    map_rest: float = 90.0
    map_max: float = 135.0
    # --- Trọng số tổ hợp PSI (tự chuẩn hoá theo các kênh có mặt) ---
    w_hr: float = 0.50
    w_temp: float = 0.40
    w_bp: float = 0.10
    # --- Thành phần mệt mỏi tích luỹ ---
    load_blend: float = 0.40     # tỉ trọng của tích luỹ trong điểm cuối (0..1)
    load_build_min: float = 90.0 # phút gắng sức tối đa để load tiến tới ~1
    load_recover_min: float = 45.0  # hằng số thời gian hồi phục khi nghỉ (phút)
    load_drive_floor: float = 0.30  # chỉ phần HR-reserve vượt mức này mới tích luỹ

    # Giới hạn làm sạch cảm biến (loại outlier như HR=2000 thấy trong log thật)
    hr_valid: tuple = (30.0, 220.0)
    temp_valid: tuple = (30.0, 43.0)
    map_valid: tuple = (40.0, 200.0)


def _frac(x, lo, hi):
    if x is None or (isinstance(x, float) and math.isnan(x)):
        return None
    return min(1.0, max(0.0, (x - lo) / (hi - lo)))


def instantaneous_strain(hr=None, temp=None, bp_map=None, cfg=PhysiologyConfig()):
    """PSI tức thời (0-10) từ các kênh SẴN CÓ. Trả về NaN nếu không có kênh nào."""
    terms, weights = [], []
    f = _frac(hr, cfg.hr_rest, cfg.hr_max)
    if f is not None:
        terms.append(f); weights.append(cfg.w_hr)
    f = _frac(temp, cfg.temp_rest, cfg.temp_max)
    if f is not None:
        terms.append(f); weights.append(cfg.w_temp)
    f = _frac(bp_map, cfg.map_rest, cfg.map_max)
    if f is not None:
        terms.append(f); weights.append(cfg.w_bp)
    wsum = sum(weights)
    if wsum <= 0:
        return float("nan")
    return 10.0 * sum(t * w for t, w in zip(terms, weights)) / wsum


def hr_reserve_fraction(hr, cfg=PhysiologyConfig()):
    """%HRR = (HR - HR_rest)/(HR_max - HR_rest), kẹp [0,1]."""
    f = _frac(hr, cfg.hr_rest, cfg.hr_max)
    return 0.0 if f is None else f


def update_fatigue_load(load, hr, dt_min, cfg=PhysiologyConfig()):
    """
    Cập nhật mệt mỏi tích luỹ (0-1) sau bước thời gian dt_min (phút):
      - Gắng sức (HR-reserve vượt load_drive_floor) làm load tăng.
      - Nghỉ làm load phân rã theo hằng số load_recover_min.
    Dùng GIỐNG NHAU ở lúc train và lúc suy luận -> feature nhất quán.
    """
    if dt_min <= 0:
        return load
    hrr = hr_reserve_fraction(hr, cfg)
    drive = max(0.0, hrr - cfg.load_drive_floor) / max(1e-6, 1.0 - cfg.load_drive_floor)
    # nạp tuyến tính theo thời gian gắng sức, phân rã mũ khi nghỉ
    load = load + drive * (dt_min / cfg.load_build_min)
    load = load * math.exp(-dt_min / cfg.load_recover_min) if drive == 0.0 else load
    return min(1.0, max(0.0, load))


def exhaustion_score(hr=None, temp=None, bp_map=None, fatigue_load=0.0,
                     cfg=PhysiologyConfig()):
    """
    Điểm kiệt sức 0-10 = tổ hợp lồi của PSI tức thời và mệt mỏi tích luỹ.
        score = (1-load_blend)·PSI + load_blend·(10·load)
    """
    inst = instantaneous_strain(hr, temp, bp_map, cfg)
    if math.isnan(inst):
        inst = 0.0
    score = (1.0 - cfg.load_blend) * inst + cfg.load_blend * (10.0 * fatigue_load)
    return min(10.0, max(0.0, score))


def score_to_level(score):
    """Điểm 0-10 -> chỉ số cấp độ 0..3 (NORMAL/MILD/MODERATE/SEVERE)."""
    t0, t1, t2 = LEVEL_THRESHOLDS
    if score < t0:
        return 0
    if score < t1:
        return 1
    if score < t2:
        return 2
    return 3


def score_to_label(score):
    return LEVELS[score_to_level(score)]
