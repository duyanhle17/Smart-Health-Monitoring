import joblib
import numpy as np
import os

# load pipeline model (scaler + classifier bên trong)
BASE_DIR = os.path.dirname(os.path.dirname(__file__))
MODEL_PATH = os.path.join(BASE_DIR, "model", "hr_model.pkl")

model = joblib.load(MODEL_PATH)

def ml_check_hr(hr_window):
    """
    hr_window: list 5 giá trị HR gần nhất
    return: NORMAL | ABNORMAL
    """

    if len(hr_window) < 5:
        return "WAITING"

    window = np.array(hr_window)

    features = np.array([[
        np.mean(window),
        np.std(window),
        np.max(window),
        np.min(window),
        window[-1] - window[0]
    ]])

    pred = model.predict(features)[0]
    return "ABNORMAL" if pred == 1 else "NORMAL"
