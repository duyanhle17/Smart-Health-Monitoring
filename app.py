from flask import Flask, request, jsonify, send_file, render_template
from src.rules import rule_based_hr
from src.ml import ml_check_hr
from src.fall.fall_state import update_fall_state

import csv
import time
import os
import pandas as pd

import matplotlib
matplotlib.use("Agg")   # bắt buộc cho server
import matplotlib.pyplot as plt

# ======================
# APP
# ======================
app = Flask(__name__)

# ======================
# PATH
# ======================
BASE_DIR = os.path.dirname(__file__)
DATA_DIR = os.path.join(BASE_DIR, "data")

HR_LOG_PATH = os.path.join(DATA_DIR, "hr_log.csv")
HR_PLOT_PATH = os.path.join(DATA_DIR, "hr_plot.png")

FALL_LOG_PATH = os.path.join(DATA_DIR, "fall_log.csv")

os.makedirs(DATA_DIR, exist_ok=True)

# ======================
# GLOBAL STATE (REALTIME)
# ======================
latest_hr_state = {
    "hr": None,
    "rule_status": None,
    "rule_message": None,
    "ml_status": None,
    "is_danger": False,
    "timestamp": 0
}

latest_fall_state = {
    "status": "WAITING",   # WAITING | SAFE | FALL | RECOVERED
    "prob": 0.0,
    "timestamp": 0
}

# ======================
# WEB
# ======================
@app.route("/")
def index():
    return render_template("index.html")

# ======================
# LOGGING
# ======================
def log_hr(hr, rule_status, rule_message, ml_status):
    file_exists = os.path.exists(HR_LOG_PATH)
    with open(HR_LOG_PATH, "a", newline="") as f:
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

def log_fall(status, prob):
    file_exists = os.path.exists(FALL_LOG_PATH)
    with open(FALL_LOG_PATH, "a", newline="") as f:
        writer = csv.writer(f)
        if not file_exists:
            writer.writerow([
                "timestamp",
                "status",
                "probability"
            ])
        writer.writerow([
            time.time(),
            status,
            prob
        ])

# ======================
# API: RECEIVE HR
# ======================
@app.route("/hr", methods=["POST"])
def receive_hr():
    data = request.get_json(force=True)
    hr = float(data["hr"])

    # rule based check
    rule_status, rule_msg = rule_based_hr(hr)
    # xác định có `nguy hiểm` không
    is_danger = rule_status.startswith("DANGER")
    #ml check
    ml_status = ml_check_hr(hr)

    #log
    log_hr(hr, rule_status, rule_msg, ml_status)

    # update global state
    latest_hr_state.update({
        "hr": int(hr),
        "rule_status": rule_status,
        "rule_message": rule_msg,
        "ml_status": ml_status,
        "is_danger": is_danger,
        "timestamp": time.time()
    })

    return jsonify({
        "status": "OK",
        **latest_hr_state
    })

# ======================
# API: RECEIVE FALL DATA
# ======================
@app.route("/fall", methods=["POST"])
def receive_fall():
    data = request.get_json(force=True)
    samples = data.get("samples", [])

    result = {"status": "WAITING", "prob": 0.0}

    for s in samples:
        if len(s) == 6:
            result = update_fall_state(s)

    latest_fall_state.update({
        "status": result.get("status", "WAITING"),
        "prob": result.get("prob", 0.0),
        "timestamp": time.time()
    })

    log_fall(latest_fall_state["status"], latest_fall_state["prob"])

    return jsonify({
        "status": "OK",
        **latest_fall_state
    })

# ======================
# API: LATEST STATUS (FRONTEND DÙNG)
# ======================
@app.route("/latest_status", methods=["GET"])
def latest_status():
    alert = (
        latest_hr_state["is_danger"] or
        latest_fall_state["status"] == "FALL"
    )

    return jsonify({
        "hr": latest_hr_state["hr"],
        "hr_danger": latest_hr_state["is_danger"],
        "hr_message": latest_hr_state["rule_message"],
        "fall_status": latest_fall_state["status"],
        "fall_prob": latest_fall_state["prob"],
        "alert": alert
    })

# ======================
# API: HR PLOT
# ======================
@app.route("/plot", methods=["GET"])
def plot_hr():
    if not os.path.exists(HR_LOG_PATH):
        return "No data yet", 400

    df = pd.read_csv(HR_LOG_PATH)
    if df.empty or "timestamp" not in df.columns:
        return "No valid data yet", 400
    #time relatives
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

    plt.savefig(HR_PLOT_PATH)
    plt.close()

    return send_file(HR_PLOT_PATH, mimetype="image/png")

# ======================
# RUN
# ======================
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)
