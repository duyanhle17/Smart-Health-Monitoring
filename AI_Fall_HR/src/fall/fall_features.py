"""
Feature Extraction for Mining Safety Fall Detection
====================================================
Trích xuất đặc trưng từ dữ liệu cảm biến IMU (ax, ay, az, gx, gy, gz).
Hỗ trợ cả bài toán nhị phân (FALL vs NON-FALL) và phân loại đa lớp.
"""

import numpy as np


# ==============================================================
# LABEL MAPPING - Phân loại 10 tình huống trong mỏ
# ==============================================================
# FALL classes  (label = 1 trong binary)
FALL_TYPES = {"ladder_fall", "slip_fall", "fainting", "cart_hit"}

# NON-FALL classes (label = 0 trong binary)
NON_FALL_TYPES = {"machinery", "rock_hit", "jump_truck", "drill_kickback", "crawling", "running"}

# Multi-class mapping
CLASS_MAP = {
    "machinery": 0,
    "ladder_fall": 1,
    "slip_fall": 2,
    "rock_hit": 3,
    "jump_truck": 4,
    "drill_kickback": 5,
    "fainting": 6,
    "crawling": 7,
    "running": 8,
    "cart_hit": 9,
}


def get_case_type(filename: str) -> str:
    """Trích xuất loại tình huống từ tên file.
    VD: 'case_011_ladder_fall.txt' → 'ladder_fall'
    """
    # Bỏ 'case_XXX_' prefix và '.txt' suffix
    name = filename.replace(".txt", "")
    parts = name.split("_", 2)  # ['case', '011', 'ladder_fall']
    if len(parts) >= 3:
        return parts[2]
    return "unknown"


# ==============================================================
# LOAD DATA
# ==============================================================
def load_txt_file(path):
    """
    Load fall detection txt file (CSV format)
    Columns: ax, ay, az, gx, gy, gz
    OR: timestamp, ax, ay, az, gx, gy, gz
    """
    data = np.loadtxt(path, delimiter=",")

    # nếu có timestamp → bỏ cột đầu
    if data.shape[1] == 7:
        data = data[:, 1:]

    if data.shape[1] != 6:
        raise ValueError(f"Invalid shape {data.shape} in {path}")

    return data


# ==============================================================
# SLIDING WINDOW
# ==============================================================
def sliding_window(data, window_size=40, step=20):
    """Chia dữ liệu thành các cửa sổ trượt."""
    windows = []
    for i in range(0, len(data) - window_size + 1, step):
        windows.append(data[i:i + window_size])
    return windows


# ==============================================================
# FEATURE EXTRACTION - Nâng cấp với nhiều đặc trưng hơn
# ==============================================================
def extract_features(window):
    """
    Trích xuất 52 đặc trưng từ một cửa sổ dữ liệu IMU (40 sample × 6 trục).

    Đặc trưng bao gồm:
    - SVM (Signal Vector Magnitude) stats cho acc & gyro
    - Statistical features per-axis (mean, std, max, min, RMS)
    - Tỉ lệ năng lượng (energy ratio)
    - Peak count (số đỉnh vượt ngưỡng)
    - Zero-crossing rate cho gyro
    """
    acc = window[:, :3]   # ax, ay, az
    gyro = window[:, 3:]  # gx, gy, gz

    svm_acc = np.linalg.norm(acc, axis=1)
    svm_gyro = np.linalg.norm(gyro, axis=1)

    features = []

    # ── SVM Acc (5 features) ──
    features.extend([
        np.mean(svm_acc),
        np.std(svm_acc),
        np.max(svm_acc),
        np.min(svm_acc),
        np.sqrt(np.mean(svm_acc ** 2)),  # RMS
    ])

    # ── SVM Gyro (5 features) ──
    features.extend([
        np.mean(svm_gyro),
        np.std(svm_gyro),
        np.max(svm_gyro),
        np.min(svm_gyro),
        np.sqrt(np.mean(svm_gyro ** 2)),
    ])

    # ── Per-axis mean (6 features) ──
    for i in range(6):
        features.append(np.mean(window[:, i]))

    # ── Per-axis RMS (6 features) ──
    for i in range(6):
        features.append(np.sqrt(np.mean(window[:, i] ** 2)))

    # ── Per-axis std (6 features) ──
    for i in range(6):
        features.append(np.std(window[:, i]))

    # ── Per-axis max (6 features) ──
    for i in range(6):
        features.append(np.max(window[:, i]))

    # ── Per-axis min (6 features) ──
    for i in range(6):
        features.append(np.min(window[:, i]))

    # ── Delta features: max - min per axis (6 features) ──
    for i in range(6):
        features.append(np.max(window[:, i]) - np.min(window[:, i]))

    # ── Peak count cho SVM acc (1 feature) ──
    threshold = np.mean(svm_acc) + 2 * np.std(svm_acc)
    features.append(np.sum(svm_acc > threshold))

    # ── Energy ratio: high-freq energy (1 feature) ──
    diff_svm = np.diff(svm_acc)
    energy_high = np.sum(diff_svm ** 2)
    energy_total = np.sum(svm_acc ** 2) + 1e-8
    features.append(energy_high / energy_total)

    # ── SVM Acc skewness & kurtosis (2 features) ──
    mean_svm = np.mean(svm_acc)
    std_svm = np.std(svm_acc) + 1e-8
    features.append(np.mean(((svm_acc - mean_svm) / std_svm) ** 3))  # skewness
    features.append(np.mean(((svm_acc - mean_svm) / std_svm) ** 4))  # kurtosis

    # ── SVM Gyro skewness & kurtosis (2 features) ──
    mean_gyro = np.mean(svm_gyro)
    std_gyro = np.std(svm_gyro) + 1e-8
    features.append(np.mean(((svm_gyro - mean_gyro) / std_gyro) ** 3))
    features.append(np.mean(((svm_gyro - mean_gyro) / std_gyro) ** 4))

    return np.array(features)
