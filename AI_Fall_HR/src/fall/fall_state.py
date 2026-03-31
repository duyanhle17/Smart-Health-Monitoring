"""
Fall State Manager - Mining Safety
===================================
Quản lý trạng thái phát hiện ngã theo thời gian thực.
Nhận dữ liệu IMU từ ESP32, tích lũy vào buffer,
và gọi model predict khi đủ dữ liệu.
"""

import numpy as np
import joblib
import time
from collections import deque

from src.fall.fall_features import extract_features

MODEL_PATH = "model/fall_model.pkl"

# Load model lúc khởi động
try:
    model = joblib.load(MODEL_PATH)
    print(f"✅ Fall detection model loaded: {MODEL_PATH}")
except FileNotFoundError:
    model = None
    print(f"⚠️  Fall model not found at {MODEL_PATH}. Please train first.")

BUFFER_SIZE = 400
FALL_HOLD_DURATION = 30.0   # Giữ trạng thái FALL trong 30s
ACTIVITY_THRESHOLD = 0.15   # Ngưỡng hoạt động để xác nhận RECOVERED

buffer = deque(maxlen=BUFFER_SIZE)

fall_state = {
    "status": "WAITING",   # WAITING | SAFE | FALL | RECOVERED
    "prob": 0.0,
    "timestamp": 0,
}

_last_fall_timestamp = 0


def update_fall_state(sample):
    """
    Nhận 1 sample [ax, ay, az, gx, gy, gz] từ ESP32.
    Trả về trạng thái hiện tại.
    """
    global _last_fall_timestamp

    buffer.append(sample)
    fall_state["timestamp"] = time.time()

    if model is None:
        fall_state["status"] = "WAITING"
        return fall_state

    if len(buffer) < BUFFER_SIZE:
        return fall_state

    # Extract features từ buffer
    window = np.array(buffer)
    feats = extract_features(window).reshape(1, -1)

    pred = model.predict(feats)[0]
    prob = float(model.predict_proba(feats)[0][1])
    now = time.time()

    if pred == 1 and prob > 0.6:
        # Phát hiện NGÃ
        _last_fall_timestamp = now
        fall_state["status"] = "FALL"
        fall_state["prob"] = prob
    elif now - _last_fall_timestamp < FALL_HOLD_DURATION and _last_fall_timestamp > 0:
        # Vẫn trong giai đoạn FALL_HOLD → kiểm tra recovery
        activity = np.std(np.sqrt(np.sum(window[:, :3] ** 2, axis=1)))
        if activity > ACTIVITY_THRESHOLD:
            _last_fall_timestamp = 0
            fall_state["status"] = "RECOVERED"
            fall_state["prob"] = prob
        else:
            fall_state["status"] = "FALL"
            fall_state["prob"] = prob
    else:
        fall_state["status"] = "SAFE"
        fall_state["prob"] = prob

    return fall_state
