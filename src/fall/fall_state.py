from collections import deque
import time
import numpy as np
from .fall_model import predict_fall

BUFFER_SIZE = 400
FALL_HOLD_DURATION = 30.0
ACTIVITY_THRESHOLD = 0.15

sensor_buffer = deque(maxlen=BUFFER_SIZE)
last_fall_timestamp = 0

def update_fall_state(sample):
    global last_fall_timestamp

    sensor_buffer.append(sample)

    if len(sensor_buffer) < BUFFER_SIZE:
        return {"status": "WAITING"}

    window = np.array(sensor_buffer)
    result = predict_fall(window)

    now = time.time()

    if result["is_fall"]:
        last_fall_timestamp = now
        return {"status": "FALL", "prob": result["probability"]}

    if now - last_fall_timestamp < FALL_HOLD_DURATION:
        activity = np.std(np.sqrt(np.sum(window[:, :3]**2, axis=1)))
        if activity > ACTIVITY_THRESHOLD:
            last_fall_timestamp = 0
            return {"status": "RECOVERED"}
        return {"status": "FALL"}

    return {"status": "SAFE"}
