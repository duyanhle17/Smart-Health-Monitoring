import os
import numpy as np
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import train_test_split
from sklearn.metrics import classification_report
import joblib

from backend.core.fall.fall_features import load_txt_file, sliding_window, extract_features

import os; _cur = os.path.dirname(__file__); DATA_DIR = os.path.abspath(os.path.join(_cur, "..", "data", "fall_raw"))
FALL_DIR = os.path.join(DATA_DIR, "fall")
NON_FALL_DIR = os.path.join(DATA_DIR, "non_fall")

X = []
y = []

# NON-FALL = 0
for fname in os.listdir(NON_FALL_DIR):
    path = os.path.join(NON_FALL_DIR, fname)
    data = load_txt_file(path)
    windows = sliding_window(data)
    for w in windows:
        X.append(extract_features(w))
        y.append(0)

# FALL = 1
for fname in os.listdir(FALL_DIR):
    path = os.path.join(FALL_DIR, fname)
    data = load_txt_file(path)
    windows = sliding_window(data)
    for w in windows:
        X.append(extract_features(w))
        y.append(1)

X = np.array(X)
y = np.array(y)

print("Dataset:", X.shape, "Labels:", np.unique(y, return_counts=True))

X_train, X_test, y_train, y_test = train_test_split(
    X, y, test_size=0.2, stratify=y, random_state=42
)

model = RandomForestClassifier(
    n_estimators=200,
    max_depth=15,
    class_weight="balanced",
    random_state=42
)

model.fit(X_train, y_train)

print("Train acc:", model.score(X_train, y_train))
print("Test acc:", model.score(X_test, y_test))
print(classification_report(y_test, model.predict(X_test)))

joblib.dump(model, "ai_training/training_scripts/fall_model.pkl")
print("✅ Saved model/fall_model.pkl")
