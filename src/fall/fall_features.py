import numpy as np

def calculate_features(window):
    features = []
    acc = window[:, 0:3]
    gyro = window[:, 3:6]

    svm_acc = np.sqrt(np.sum(acc**2, axis=1))
    svm_gyro = np.sqrt(np.sum(gyro**2, axis=1))

    features += [
        np.mean(svm_acc),
        np.std(svm_acc),
        np.max(svm_acc),
        np.min(svm_acc),
        np.sqrt(np.mean(svm_acc**2)),
        np.mean(svm_gyro),
        np.std(svm_gyro),
        np.max(svm_gyro),
        np.min(svm_gyro),
        np.sqrt(np.mean(svm_gyro**2)),
    ]

    for i in range(3):
        features.append(np.mean(acc[:, i]))

    for i in range(6):
        features.append(np.sqrt(np.mean(window[:, i]**2)))

    return np.array(features).reshape(1, -1)
