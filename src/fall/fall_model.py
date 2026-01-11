import joblib
import numpy as np
from .fall_features import calculate_features

MODEL_PATH = "model/fall_detection_model.pkl"

model = joblib.load(MODEL_PATH)

def predict_fall(window_data):
    feats = calculate_features(window_data)
    pred = model.predict(feats)[0]
    probs = model.predict_proba(feats)[0]
    return {
        "is_fall": bool(pred == 1),
        "probability": float(probs[1])
    }
