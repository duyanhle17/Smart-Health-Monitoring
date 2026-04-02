import numpy as np

def load_txt_file(path):
    """
    Load fall detection txt file (CSV format)
    Columns:
    ax, ay, az, gx, gy, gz
    OR
    timestamp, ax, ay, az, gx, gy, gz
    """
    # đọc bằng delimiter = ','
    data = np.loadtxt(path, delimiter=",")

    # nếu có timestamp → bỏ cột đầu
    if data.shape[1] == 7:
        data = data[:, 1:]

    if data.shape[1] != 6:
        raise ValueError(f"Invalid shape {data.shape} in {path}")

    return data


# =========================
# SLIDING WINDOW
# =========================
def sliding_window(data, window_size=400, step=200):
    windows = []
    for i in range(0, len(data) - window_size + 1, step):
        windows.append(data[i:i + window_size])
    return windows


# =========================
# FEATURE EXTRACTION
# =========================
def extract_features(window):
    acc = window[:, :3]
    gyro = window[:, 3:]

    svm_acc = np.linalg.norm(acc, axis=1)
    svm_gyro = np.linalg.norm(gyro, axis=1)

    features = []

    # Acc SVM
    features.extend([
        np.mean(svm_acc),
        np.std(svm_acc),
        np.max(svm_acc),
        np.min(svm_acc),
        np.sqrt(np.mean(svm_acc ** 2)),
    ])

    # Gyro SVM
    features.extend([
        np.mean(svm_gyro),
        np.std(svm_gyro),
        np.max(svm_gyro),
        np.min(svm_gyro),
        np.sqrt(np.mean(svm_gyro ** 2)),
    ])

    # Mean 6 trục
    for i in range(6):
        features.append(np.mean(window[:, i]))

    # RMS 6 trục
    for i in range(6):
        features.append(np.sqrt(np.mean(window[:, i] ** 2)))

    return np.array(features)
