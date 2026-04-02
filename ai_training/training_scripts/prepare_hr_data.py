import pandas as pd
import numpy as np

# đọc data
df = pd.read_csv("ai_training/data/hr_history.csv")

WINDOW = 5   # mỗi mẫu ML nhìn 5 nhịp tim liên tiếp
X, y = [], []

for i in range(len(df) - WINDOW):
    window = df.iloc[i:i+WINDOW]["hr"].values

    features = [
        np.mean(window),          # HR trung bình
        np.std(window),           # độ dao động
        np.max(window),           # HR cao nhất
        np.min(window),           # HR thấp nhất
        window[-1] - window[0]    # xu hướng tăng / giảm
    ]

    X.append(features)
    y.append(df["label"].iloc[i+WINDOW])

X = np.array(X)
y = np.array(y)

np.save("ai_training/data/hr_X.npy", X)
np.save("ai_training/data/hr_y.npy", y)

print("HR dataset created:")
print("X shape:", X.shape)
print("y:", y)
