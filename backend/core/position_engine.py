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
# ──────────────────────────────────────────────────────────────
ANCHORS = [
    {"id": "ANC_STAGE", "x": 50.0, "y": 20.0, "name": "Khán đài giữa"},
    {"id": "ANC_LEFT",  "x": 15.0, "y": 60.0, "name": "Khu vực trái"},
    {"id": "ANC_RIGHT", "x": 85.0, "y": 60.0, "name": "Khu vực phải"},
]

# Smoothing state per worker
_smooth_state = {}
ALPHA = 0.15  # Exponential smoothing factor (0=max smooth, 1=no smooth)


def trilaterate(d1, d2, d3):
    """
    Trilateration Least-Squares từ 3 khoảng cách tới 3 Anchor cố định.

    Hệ phương trình gốc:
        (x - x1)² + (y - y1)² = d1²
        (x - x2)² + (y - y2)² = d2²
        (x - x3)² + (y - y3)² = d3²

    Trừ PT1 cho PT2 và PT3 → hệ tuyến tính 2x2:
        A @ [x, y]^T = b
    """
    x1, y1 = ANCHORS[0]["x"], ANCHORS[0]["y"]
    x2, y2 = ANCHORS[1]["x"], ANCHORS[1]["y"]
    x3, y3 = ANCHORS[2]["x"], ANCHORS[2]["y"]

    A = np.array([
        [2 * (x2 - x1), 2 * (y2 - y1)],
        [2 * (x3 - x1), 2 * (y3 - y1)],
    ])

    b = np.array([
        d1**2 - d2**2 - x1**2 + x2**2 - y1**2 + y2**2,
        d1**2 - d3**2 - x1**2 + x3**2 - y1**2 + y3**2,
    ])

    try:
        result = np.linalg.lstsq(A, b, rcond=None)[0]
        x_est, y_est = float(result[0]), float(result[1])
        # Clamp to logical space
        x_est = max(0.0, min(100.0, x_est))
        y_est = max(0.0, min(100.0, y_est))
        return x_est, y_est
    except np.linalg.LinAlgError:
        return 50.0, 50.0  # fallback center


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


def estimate_position(worker_id, d1, d2, d3):
    """
    Pipeline đầy đủ: Trilaterate → Smooth → Return.
    Đây là hàm chính được gọi từ endpoint.
    """
    x_raw, y_raw = trilaterate(d1, d2, d3)

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
    else:
        return "CENTER_PATH"


def get_anchor_config():
    """Trả về anchor config cho frontend."""
    return [dict(a) for a in ANCHORS]
