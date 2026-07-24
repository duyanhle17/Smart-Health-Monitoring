"""
Position Engine — Two-Anchor Circle Intersection
================================================
Ước lượng vị trí (x, y) của Worker từ khoảng cách UWB tới 2 Anchor cố định.

Phần cứng hiện tại: 2 anchor + 1 worker (xem firmware/README.md).

Thuật toán:
  1. Nhận d1, d2 (MÉT) — khoảng cách thật từ worker tới anchor 1 và anchor 2.
  2. Đổi sang đơn vị logic của bản đồ (0-100) qua ANCHOR_BASELINE_M.
  3. Giao 2 đường tròn -> 2 nghiệm đối xứng qua đường nối 2 anchor.
  4. Chọn nghiệm nằm cùng phía với WORK_AREA_POINT (khu vực worker đi lại).
  5. Giới hạn bước nhảy + Exponential Smoothing để giảm nhiễu.

LƯU Ý HÌNH HỌC: đặt 2 anchor dọc theo MỘT cạnh biên của khu vực, khu vực đi
lại nằm hẳn về một phía — khi đó nghiệm gương rơi ra ngoài và bước 4 luôn đúng.
Tránh để worker đứng ngay trên đường thẳng nối 2 anchor: ở đó 2 nghiệm trùng
nhau và sai số theo phương vuông góc tăng vọt.
"""

import math
import random

# ──────────────────────────────────────────────────────────────
# ANCHOR CONFIGURATION
# Toạ độ trong không gian logic 0-100 của bản đồ frontend.
# PHẢI khớp với vị trí đặt thật ngoài hiện trường.
ANCHORS = [
    {"id": "ANC_LEFT",  "x": 10.0, "y": 15.0, "name": "Neo trái"},
    {"id": "ANC_RIGHT", "x": 90.0, "y": 15.0, "name": "Neo phải"},
]

# Khoảng cách THẬT giữa 2 anchor, tính bằng MÉT. Đo bằng thước một lần.
# Đây là thứ duy nhất quy đổi mét (từ UWB) sang đơn vị logic của bản đồ.
ANCHOR_BASELINE_M = 6.0

# Một điểm bất kỳ NẰM CHẮC CHẮN trong khu vực worker đi lại. Dùng để chọn
# nghiệm đúng trong 2 nghiệm đối xứng — không cần biết "trái/phải", chỉ cần
# một điểm mẫu. Đổi vị trí anchor thì đổi luôn điểm này cho khớp.
WORK_AREA_POINT = (50.0, 70.0)

# Smoothing state per worker
_smooth_state = {}
ALPHA = 0.35           # 0 = mượt tối đa (trễ), 1 = không lọc
MAX_STEP_UNITS = 25.0  # chặn nhảy cóc do nhiễu NLOS giữa 2 lần cập nhật


def reset_smooth_state(worker_id):
    if worker_id in _smooth_state:
        del _smooth_state[worker_id]


def _side(px, py, ax, ay, bx, by):
    """Dấu của tích có hướng: điểm P nằm phía nào của đường thẳng AB."""
    return (bx - ax) * (py - ay) - (by - ay) * (px - ax)


def units_per_metre():
    """Hệ số quy đổi mét -> đơn vị logic, suy ra từ baseline đo được."""
    a, b = ANCHORS[0], ANCHORS[1]
    baseline_units = math.hypot(b["x"] - a["x"], b["y"] - a["y"])
    if ANCHOR_BASELINE_M <= 0:
        return 1.0
    return baseline_units / ANCHOR_BASELINE_M


def dual_anchor_tracking(d1_m, d2_m):
    """
    Giao 2 đường tròn. d1_m, d2_m tính bằng MÉT (số UWB gửi lên).
    Trả về (x, y) trong không gian logic, hoặc None nếu không giải được.
    """
    a, b = ANCHORS[0], ANCHORS[1]
    ax, ay, bx, by = a["x"], a["y"], b["x"], b["y"]
    dx, dy = bx - ax, by - ay
    L = math.hypot(dx, dy)                      # baseline, đơn vị logic
    if L <= 0:
        return None

    upm = units_per_metre()
    d1, d2 = d1_m * upm, d2_m * upm             # đổi sang đơn vị logic
    if d1 <= 0 or d2 <= 0:
        return None

    # Nhiễu/NLOS có thể làm 2 đường tròn không cắt nhau. Nới nhẹ cho chúng
    # chạm nhau thay vì bỏ cả phép đo (giữ nguyên tỉ lệ d1:d2).
    if d1 + d2 < L:
        s = L / (d1 + d2)
        d1, d2 = d1 * s, d2 * s
    if abs(d1 - d2) > L:                        # đường tròn này nằm gọn trong kia
        if d1 > d2:
            d1 = d2 + L * 0.999
        else:
            d2 = d1 + L * 0.999

    # Toạ độ dọc baseline, tính từ anchor 1
    x_rel = (d1 * d1 - d2 * d2 + L * L) / (2.0 * L)
    h_sq = d1 * d1 - x_rel * x_rel
    h = math.sqrt(h_sq) if h_sq > 0 else 0.0    # h=0 -> 2 nghiệm trùng nhau

    ux, uy = dx / L, dy / L                     # vector đơn vị dọc baseline
    nx, ny = -uy, ux                            # pháp tuyến
    fx, fy = ax + ux * x_rel, ay + uy * x_rel   # chân đường vuông góc

    cand_plus = (fx + nx * h, fy + ny * h)
    cand_minus = (fx - nx * h, fy - ny * h)

    # Chọn nghiệm cùng phía với khu vực làm việc (khử nghiệm gương)
    want = _side(WORK_AREA_POINT[0], WORK_AREA_POINT[1], ax, ay, bx, by)
    got = _side(cand_plus[0], cand_plus[1], ax, ay, bx, by)
    x_est, y_est = cand_plus if (want >= 0) == (got >= 0) else cand_minus

    return max(0.0, min(100.0, x_est)), max(0.0, min(100.0, y_est))


def distances_from_position(x, y, noise_std=0.15):
    """
    Khoảng cách (MÉT) từ vị trí logic (x, y) tới từng anchor, kèm nhiễu Gauss.
    Dùng cho Demo Simulator — cùng đơn vị với số UWB thật gửi lên.
    """
    upm = units_per_metre()
    out = []
    for a in ANCHORS:
        d_units = math.hypot(x - a["x"], y - a["y"])
        d_m = d_units / upm + random.gauss(0.0, noise_std)
        out.append(round(max(0.05, d_m), 2))
    return out


def estimate_position(worker_id, d1, d2, yaw=0.0):
    """
    Pipeline đầy đủ: giao 2 đường tròn -> chặn bước nhảy -> smooth.
    d1, d2 tính bằng MÉT. yaw hiện chưa dùng (giữ chỗ cho PDR sau này).
    Trả về (x, y) đã làm mượt, hoặc None nếu lần này không giải được —
    caller phải giữ nguyên vị trí cũ khi nhận None.
    """
    fix = dual_anchor_tracking(d1, d2)
    if fix is None:
        return None
    x_raw, y_raw = fix

    prev = _smooth_state.get(worker_id)
    if prev is None:
        x_smooth, y_smooth = x_raw, y_raw       # lần đầu: bám thẳng
    else:
        prev_x, prev_y = prev
        # chặn nhảy cóc: cắt bớt bước nhảy quá lớn thay vì bỏ hẳn phép đo
        step = math.hypot(x_raw - prev_x, y_raw - prev_y)
        if step > MAX_STEP_UNITS:
            k = MAX_STEP_UNITS / step
            x_raw = prev_x + (x_raw - prev_x) * k
            y_raw = prev_y + (y_raw - prev_y) * k
        x_smooth = ALPHA * x_raw + (1 - ALPHA) * prev_x
        y_smooth = ALPHA * y_raw + (1 - ALPHA) * prev_y

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
