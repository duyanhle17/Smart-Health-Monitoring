# from collections import deque
# import time
# import numpy as np
# from .fall_model import predict_fall

# BUFFER_SIZE = 400
# FALL_HOLD_DURATION = 30.0
# ACTIVITY_THRESHOLD = 0.15

# sensor_buffer = deque(maxlen=BUFFER_SIZE)
# last_fall_timestamp = 0

# def update_fall_state(sample):
#     global last_fall_timestamp

#     sensor_buffer.append(sample)

#     if len(sensor_buffer) < BUFFER_SIZE:
#         return {"status": "WAITING"}

#     window = np.array(sensor_buffer)
#     result = predict_fall(window)

#     now = time.time()

#     if result["is_fall"]:
#         last_fall_timestamp = now
#         return {"status": "FALL", "prob": result["probability"]}

#     if now - last_fall_timestamp < FALL_HOLD_DURATION:
#         activity = np.std(np.sqrt(np.sum(window[:, :3]**2, axis=1)))
#         if activity > ACTIVITY_THRESHOLD:
#             last_fall_timestamp = 0
#             return {"status": "RECOVERED"}
#         return {"status": "FALL"}

#     return {"status": "SAFE"}

# src/fall/fall_state.py
import numpy as np
import joblib
import time
from collections import deque
import os

from backend.core.fall.fall_features import extract_features

_root = os.path.dirname(os.path.abspath(__file__))
MODEL_PATH = os.path.join(_root, "models", "fall_model.pkl")

# Load model, handle missing model gracefully for tests
try:
    model = joblib.load(MODEL_PATH)
except Exception as e:
    print(f"[Warning] Could not load model at {MODEL_PATH}: {e}")
    model = None

# Hardware sends telemetry at ~10Hz, so 50 records = 5 seconds window
BUFFER_SIZE = 50 
FALL_HOLD_DURATION = 15.0 # Mức thời gian lưu giữ cờ FALL (15 giây)

buffers = {}
fall_states = {}

def get_worker_buffer(worker_id):
    if worker_id not in buffers:
         buffers[worker_id] = deque(maxlen=BUFFER_SIZE)
    return buffers[worker_id]

def get_worker_state(worker_id):
    if worker_id not in fall_states:
         fall_states[worker_id] = {
             "status": "WAITING",
             "prob": 0.0,
             "timestamp": 0,
             "last_fall_time": 0
         }
    return fall_states[worker_id]

def update_fall_state(worker_id, sample):
    """
    sample: [ax, ay, az, gx, gy, gz]
    """
    buffer = get_worker_buffer(worker_id)
    fall_state = get_worker_state(worker_id)
    buffer.append(sample)

    now = time.time()

    # Nếu chưa đủ buffer size, vẫn check xem trong diện đang hold FALL không
    if len(buffer) < BUFFER_SIZE:
        fall_state["timestamp"] = now
        if now - fall_state["last_fall_time"] < FALL_HOLD_DURATION and fall_state["last_fall_time"] > 0:
            fall_state["status"] = "FALL"
        return fall_state

    # Tiến hành Predict nếu có model
    if model is not None:
        window = np.array(buffer)
        feats = extract_features(window).reshape(1, -1)

        pred = model.predict(feats)[0]
        prob = model.predict_proba(feats)[0][1]

        if pred == 1 and prob > 0.7:
            fall_state["status"] = "FALL"
            fall_state["prob"] = float(prob)
            fall_state["last_fall_time"] = now
        else:
            # Nếu hết thời gian Hold thì mới trả về SAFE
            if now - fall_state["last_fall_time"] >= FALL_HOLD_DURATION:
                fall_state["status"] = "SAFE"
                fall_state["prob"] = float(prob)
            else:
                fall_state["status"] = "FALL" # Vẫn đang HOLD
    else:
        # Fallback if no model
        pass

    fall_state["timestamp"] = now
    return fall_state
