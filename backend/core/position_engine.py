"""
Position Interpolation Engine — Trilateration Least-Squares
============================================================
Ước lượng vị trí (x, y) của Worker dựa trên khoảng cách tới 3 Anchor cố định.

Thuật toán:
  1. Nhận 3 khoảng cách d1, d2, d3 từ Worker tới 3 Anchor đã biết tọa độ.
  2. Giải hệ phương trình phi tuyến bằng Linearization (trừ PT đầu).
  3. Tìm nghiệm Least-Squares cho hệ tuyến tính kết quả.
  4. Áp dụng Simple Exponential Smoothing để giảm jitter.
"""

import numpy as np
import math

# ──────────────────────────────────────────────────────────────
# ANCHOR CONFIGURATION (logical space 0-100)
# Phải khớp với vị trí đặt trong thực tế / trên bản đồ frontend
ANCHORS = [
    {"id": "ANC_STAGE", "x": 50.0, "y": 17.0, "name": "Khán đài giữa"},
    {"id": "ANC_LEFT",  "x": 0.0, "y": 60.0, "name": "Khu vực trái"},
    {"id": "ANC_RIGHT", "x": 93.0, "y": 60.0, "name": "Khu vực phải"},
]

# Smoothing state per worker
_smooth_state = {}
ALPHA = 0.08  # Exponential smoothing factor (0=max smooth, 1=no smooth)


def single_anchor_tracking(d1, yaw_deg):
    """
    Tracking 1-Anchor:
    Sử dụng khoảng cách d1 từ ANC_STAGE và góc Yaw từ IMU.
    Anchor trung tâm (ANC_STAGE) tọa độ: (50, 20).
    Worker đi từ lối vào (y=80) tiến về sân khấu (y=20),
    nên ta cần áp dụng hệ trục tọa độ phù hợp.
    """
    x_anchor, y_anchor = ANCHORS[0]["x"], ANCHORS[0]["y"]
    
    # Chuyển đổi yaw (độ) sang radian
    # Giả định: Yaw=0 hướng thẳng lên sân khấu (trục dọc ngược chiều y)
    # y = y_anchor + d1 * cos(yaw)
    # x = x_anchor + d1 * sin(yaw)
    yaw_rad = math.radians(yaw_deg)
    
    x_est = x_anchor + d1 * math.sin(yaw_rad)
    y_est = y_anchor + d1 * math.cos(yaw_rad)

    # Khống chế giới hạn bản đồ (0-100)
    x_est = max(0.0, min(100.0, x_est))
    y_est = max(0.0, min(100.0, y_est))
    
    return float(x_est), float(y_est)


def distances_from_position(x, y, noise_std=0.5):
    """
    Tính khoảng cách từ vị trí (x, y) tới mỗi Anchor.
    Thêm Gaussian noise mô phỏng sai số đo lường của sensor.
    Dùng cho Demo Simulator.
    """
    distances = []
    for a in ANCHORS:
        d = math.sqrt((x - a["x"])**2 + (y - a["y"])**2)
        d += np.random.normal(0, noise_std)  # sensor noise
        d = max(0.1, d)  # distance can't be negative
        distances.append(round(d, 2))
    return distances


def estimate_position(worker_id, d1, d2, d3, yaw=0.0):
    """
    Pipeline đầy đủ: 1-Anchor Tracking → Smooth → Return.
    Đây là hàm chính được gọi từ endpoint.
    """
    x_raw, y_raw = single_anchor_tracking(d1, yaw)

    # Exponential Smoothing
    if worker_id in _smooth_state:
        prev_x, prev_y = _smooth_state[worker_id]
        x_smooth = ALPHA * x_raw + (1 - ALPHA) * prev_x
        y_smooth = ALPHA * y_raw + (1 - ALPHA) * prev_y
    else:
        x_smooth, y_smooth = x_raw, y_raw

    _smooth_state[worker_id] = (x_smooth, y_smooth)
    return round(x_smooth, 2), round(y_smooth, 2)


def classify_zone(x, y):
    """Phân loại Worker thuộc zone nào dựa trên vị trí logical."""
    if y < 35:
        return "GAMMA_STAGE"
    elif x < 35 and y >= 35:
        return "ALPHA_LEFT"
    elif x > 65 and y >= 35:
        return "BETA_RIGHT"
    elif 36 <= x <= 64 and 45 <= y <= 85:
        return "DELTA_CENTER"
    else:
        return "CENTER_PATH"


def get_anchor_config():
    """Trả về anchor config cho frontend."""
    return [dict(a) for a in ANCHORS]
