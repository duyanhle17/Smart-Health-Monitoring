import numpy as np
import joblib
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler
from sklearn.pipeline import Pipeline
from sklearn.model_selection import train_test_split

# load data
X = np.load("ai_training/data/hr_X.npy")
y = np.load("ai_training/data/hr_y.npy")

# chia train / test
X_train, X_test, y_train, y_test = train_test_split(
    X, y, test_size=0.3, random_state=42
)

# pipeline: scale + model
pipe = Pipeline([
    ("scaler", StandardScaler()),
    ("clf", LogisticRegression())
])

# train
pipe.fit(X_train, y_train)

print("Train accuracy:", pipe.score(X_train, y_train))
print("Test accuracy:", pipe.score(X_test, y_test))

# save model
joblib.dump(pipe, "ai_training/training_scripts/hr_model.pkl")
print("✅ HR model trained & saved to model/hr_model.pkl")
