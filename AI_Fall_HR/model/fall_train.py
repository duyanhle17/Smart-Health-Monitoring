"""
Train Fall Detection Model - Mining Safety
===========================================
Train từ data/mining_cases/ (100 file, 10 loại tình huống)
Output: model/fall_model.pkl

Sử dụng:
    python model/fall_train.py
"""

import os
import sys
import numpy as np
from sklearn.ensemble import RandomForestClassifier, GradientBoostingClassifier
from sklearn.model_selection import train_test_split, cross_val_score
from sklearn.metrics import classification_report, confusion_matrix
import joblib

# Thêm root vào path để import src
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from src.fall.fall_features import (
    load_txt_file,
    sliding_window,
    extract_features,
    get_case_type,
    FALL_TYPES,
    NON_FALL_TYPES,
    CLASS_MAP,
)

# ==============================================================
# CONFIG
# ==============================================================
DATA_DIR = os.path.join("data", "mining_cases")
MODEL_OUTPUT = os.path.join("model", "fall_model.pkl")
WINDOW_SIZE = 400
STEP = 200


def main():
    print("=" * 60)
    print("🏗️  TRAINING FALL DETECTION MODEL - Mining Safety")
    print("=" * 60)

    if not os.path.isdir(DATA_DIR):
        print(f"❌ Không tìm thấy thư mục: {DATA_DIR}")
        sys.exit(1)

    X = []
    y_binary = []   # 0 = NON-FALL, 1 = FALL
    y_multi = []    # multi-class
    file_stats = {}

    # ── Đọc từng file và trích xuất features ──
    files = sorted([f for f in os.listdir(DATA_DIR) if f.endswith(".txt")])
    print(f"📂 Tìm thấy {len(files)} file trong {DATA_DIR}\n")

    for fname in files:
        case_type = get_case_type(fname)

        if case_type not in CLASS_MAP:
            print(f"⚠️  Bỏ qua file không nhận diện: {fname} (type={case_type})")
            continue

        is_fall = 1 if case_type in FALL_TYPES else 0
        multi_label = CLASS_MAP[case_type]

        path = os.path.join(DATA_DIR, fname)
        try:
            data = load_txt_file(path)
            windows = sliding_window(data, WINDOW_SIZE, STEP)

            for w in windows:
                feats = extract_features(w)
                X.append(feats)
                y_binary.append(is_fall)
                y_multi.append(multi_label)

            file_stats.setdefault(case_type, {"files": 0, "windows": 0})
            file_stats[case_type]["files"] += 1
            file_stats[case_type]["windows"] += len(windows)

        except Exception as e:
            print(f"❌ Lỗi đọc {fname}: {e}")

    X = np.array(X)
    y_binary = np.array(y_binary)
    y_multi = np.array(y_multi)

    # ── In thống kê dữ liệu ──
    print("\n📊 Thống kê dữ liệu:")
    print(f"{'Loại':<20} {'Files':>6} {'Windows':>8} {'Label':>8}")
    print("-" * 50)
    for ct, stats in sorted(file_stats.items()):
        label = "FALL" if ct in FALL_TYPES else "NON-FALL"
        print(f"{ct:<20} {stats['files']:>6} {stats['windows']:>8} {label:>8}")

    print(f"\n{'TỔNG':.<20} {'':>6} {len(X):>8}")
    print(f"  FALL windows: {np.sum(y_binary == 1)}")
    print(f"  NON-FALL windows: {np.sum(y_binary == 0)}")
    print(f"  Feature dimension: {X.shape[1]}")

    # ── Train / Test Split ──
    X_train, X_test, y_train, y_test = train_test_split(
        X, y_binary, test_size=0.2, stratify=y_binary, random_state=42
    )

    print(f"\n🔀 Train: {len(X_train)} | Test: {len(X_test)}")

    # ── Train model: Random Forest ──
    print("\n🌲 Training Random Forest...")
    rf_model = RandomForestClassifier(
        n_estimators=300,
        max_depth=20,
        min_samples_split=3,
        min_samples_leaf=2,
        class_weight="balanced",
        random_state=42,
        n_jobs=-1,
    )
    rf_model.fit(X_train, y_train)

    rf_train_acc = rf_model.score(X_train, y_train)
    rf_test_acc = rf_model.score(X_test, y_test)
    print(f"  Train Accuracy: {rf_train_acc:.4f}")
    print(f"  Test Accuracy:  {rf_test_acc:.4f}")

    # ── Train model: Gradient Boosting ──
    print("\n🚀 Training Gradient Boosting...")
    gb_model = GradientBoostingClassifier(
        n_estimators=200,
        max_depth=6,
        learning_rate=0.1,
        subsample=0.8,
        random_state=42,
    )
    gb_model.fit(X_train, y_train)

    gb_train_acc = gb_model.score(X_train, y_train)
    gb_test_acc = gb_model.score(X_test, y_test)
    print(f"  Train Accuracy: {gb_train_acc:.4f}")
    print(f"  Test Accuracy:  {gb_test_acc:.4f}")

    # ── Chọn model tốt nhất ──
    if gb_test_acc > rf_test_acc:
        best_model = gb_model
        best_name = "Gradient Boosting"
        best_acc = gb_test_acc
    else:
        best_model = rf_model
        best_name = "Random Forest"
        best_acc = rf_test_acc

    print(f"\n🏆 Best Model: {best_name} (Test Acc = {best_acc:.4f})")

    # ── Đánh giá chi tiết ──
    y_pred = best_model.predict(X_test)
    print("\n📋 Classification Report:")
    print(classification_report(
        y_test, y_pred,
        target_names=["NON-FALL", "FALL"],
        digits=4,
    ))

    print("📉 Confusion Matrix:")
    cm = confusion_matrix(y_test, y_pred)
    print(f"  TN={cm[0][0]}  FP={cm[0][1]}")
    print(f"  FN={cm[1][0]}  TP={cm[1][1]}")

    # ── Cross Validation ──
    print("\n🔄 5-Fold Cross Validation:")
    cv_scores = cross_val_score(best_model, X, y_binary, cv=5, scoring="accuracy")
    print(f"  Scores: {cv_scores}")
    print(f"  Mean: {cv_scores.mean():.4f} ± {cv_scores.std():.4f}")

    # ── Feature Importance (top 10) ──
    if hasattr(best_model, "feature_importances_"):
        importances = best_model.feature_importances_
        indices = np.argsort(importances)[::-1]
        print("\n📊 Top 10 Features:")
        for rank, idx in enumerate(indices[:10]):
            print(f"  {rank+1:2d}. Feature[{idx:2d}] importance={importances[idx]:.4f}")

    # ── Lưu model ──
    joblib.dump(best_model, MODEL_OUTPUT)
    print(f"\n✅ Model saved: {MODEL_OUTPUT}")
    print("=" * 60)


if __name__ == "__main__":
    main()
