from flask import Flask, request, jsonify, send_file
from src.rules import rule_based_hr
from src.ml import ml_check_hr

import csv
import time
import os
import pandas as pd

import matplotlib
matplotlib.use("Agg")   # BẮT BUỘC cho server
import matplotlib.pyplot as plt

app = Flask(__name__)

# ======================
# PATH
# ======================
BASE_DIR = os.path.dirname(__file__)
DATA_DIR = os.path.join(BASE_DIR, "data")
LOG_PATH = os.path.join(DATA_DIR, "hr_log.csv")
PLOT_PATH = os.path.join(DATA_DIR, "hr_plot.png")
# print ("[INFO] Data directory:", DATA_DIR)

# đảm bảo thư mục data tồn tại
os.makedirs(DATA_DIR, exist_ok=True)

# ======================
# LOGGING
# ======================
def log_hr(hr, rule_status, rule_message, ml_status):
    file_exists = os.path.exists(LOG_PATH)

    with open(LOG_PATH, "a", newline="") as f:
        writer = csv.writer(f)

        # ghi header nếu file mới
        if not file_exists:
            writer.writerow([
                "timestamp",
                "hr",
                "rule_status",
                "rule_message",
                "ml_status"
            ])

        writer.writerow([
            time.time(),
            hr,
            rule_status,
            rule_message,
            ml_status
        ])

# ======================
# API: RECEIVE HR
# ======================
@app.route("/hr", methods=["POST"])
def receive_hr():
    data = request.get_json(force=True)
    hr = float(data["hr"])

    # rule-based
    rule_status, rule_msg = rule_based_hr(hr)

    # ML check
    ml_status = ml_check_hr(hr)

    # log
    log_hr(hr, rule_status, rule_msg, ml_status)

    return jsonify({
        "hr": hr,
        "rule_status": rule_status,
        "rule_message": rule_msg,
        "ml_status": ml_status
    })

# ======================
# API: PLOT
# ======================
@app.route("/plot", methods=["GET"])
def plot_hr():
    if not os.path.exists(LOG_PATH):
        return "No data yet", 400

    df = pd.read_csv(LOG_PATH)

    if df.empty or "timestamp" not in df.columns:
        return "No valid data yet", 400

    # time relative
    t0 = df["timestamp"].iloc[0]
    df["t"] = df["timestamp"] - t0

    normal = df[df["ml_status"] == "NORMAL"]
    abnormal = df[df["ml_status"] == "ABNORMAL"]

    # plt.figure(figsize=(10, 4))
    plt.figure(figsize=(8, 3), dpi=100)


    if not normal.empty:
        plt.plot(normal["t"], normal["hr"], label="Normal", color="blue")

    if not abnormal.empty:
        plt.scatter(
            abnormal["t"],
            abnormal["hr"],
            color="red",
            label="Abnormal",
            zorder=3
        )

    plt.xlabel("Time (s)")
    plt.ylabel("Heart Rate (bpm)")
    plt.title("Heart Rate Monitoring")
    plt.legend()
    plt.grid(True)

    plt.savefig(PLOT_PATH)
    plt.close()

    return send_file(PLOT_PATH, mimetype="image/png")

# ======================
# RUN
# ======================
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)
