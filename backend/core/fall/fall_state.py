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

from backend.core.fall.fall_features import extract_features

import os; _root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))); MODEL_PATH = os.path.join(_root, "ai_training", "training_scripts", "fall_model.pkl")
model = joblib.load(MODEL_PATH)

BUFFER_SIZE = 400
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
             "timestamp": 0
         }
    return fall_states[worker_id]

def update_fall_state(worker_id, sample):
    """
    sample: [ax, ay, az, gx, gy, gz]
    """
    buffer = get_worker_buffer(worker_id)
    fall_state = get_worker_state(worker_id)
    buffer.append(sample)

    if len(buffer) < BUFFER_SIZE:
        fall_state["timestamp"] = time.time()
        return fall_state

    window = np.array(buffer)
    feats = extract_features(window).reshape(1, -1)

    pred = model.predict(feats)[0]
    prob = model.predict_proba(feats)[0][1]

    if pred == 1 and prob > 0.7:
        fall_state["status"] = "FALL"
        fall_state["prob"] = float(prob)
    else:
        fall_state["status"] = "SAFE"
        fall_state["prob"] = float(prob)

    fall_state["timestamp"] = time.time()
    return fall_state
