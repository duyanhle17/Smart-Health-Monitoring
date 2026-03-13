import os
import csv
import time
import pandas as pd
from flask import Flask, request, jsonify, render_template

from src.rules import rule_based_hr
from src.fall.fall_state import update_fall_state, fall_state

app = Flask(__name__)

BASE_DIR = os.path.dirname(__file__)
DATA_DIR = os.path.join(BASE_DIR, "data")
os.makedirs(DATA_DIR, exist_ok=True)

LOCATION_LOG_PATH = os.path.join(DATA_DIR, "mine_location_log.csv")
INCIDENT_LOG_PATH = os.path.join(DATA_DIR, "incident_log.csv")

workers = {}

def get_worker(wid):
    if wid not in workers:
        workers[wid] = {
            "worker_id": wid,
            "hr": 75,
            "hr_status": "NORMAL",
            "hr_msg": "",
            "gas": 0.0,
            "gas_status": "SAFE",
            "fall_status": "SAFE",
            "x": 50.0,
            "y": 50.0,
            "last_active": time.time(),
            "alert": "NORMAL"
        }
    return workers[wid]

def evaluate_alert(w):
    is_danger = w["fall_status"] == "FALL" or w["gas_status"] == "DANGER" or "DANGER" in w["hr_status"]
    is_warning = w["gas_status"] == "WARNING" or "WARNING" in w["hr_status"]
    
    if is_danger:
        w["alert"] = "DANGER"
    elif is_warning:
        w["alert"] = "WARNING"
    else:
        w["alert"] = "NORMAL"

def log_incident(wid, alert_type, x, y, env_data):
    file_exists = os.path.exists(INCIDENT_LOG_PATH)
    with open(INCIDENT_LOG_PATH, "a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        if not file_exists:
            writer.writerow(["timestamp", "worker_id", "alert_type", "x", "y", "env_data"])
        writer.writerow([time.time(), wid, alert_type, x, y, env_data])

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/hr", methods=["POST"])
def receive_hr():
    data = request.get_json(force=True)
    wid = data.get("worker_id", "W1")
    hr = float(data.get("hr", 75))
    
    w = get_worker(wid)
    w["hr"] = hr
    rule_status, rule_msg = rule_based_hr(hr)
    w["hr_status"] = rule_status
    w["hr_msg"] = rule_msg
    w["last_active"] = time.time()
    
    evaluate_alert(w)
    return jsonify({"status": "OK", "worker": w})

@app.route("/gas", methods=["POST"])
def receive_gas():
    data = request.get_json(force=True)
    wid = data.get("worker_id", "W1")
    gas = float(data.get("gas", 0))
    
    w = get_worker(wid)
    w["gas"] = round(gas, 2)
    
    if gas >= 50:
        w["gas_status"] = "DANGER"
    elif gas >= 25:
        w["gas_status"] = "WARNING"
    else:
        w["gas_status"] = "SAFE"
        
    w["last_active"] = time.time()
    evaluate_alert(w)
    if w["gas_status"] == "DANGER":
        log_incident(wid, "GAS_LEAK", w["x"], w["y"], f"Gas: {gas} ppm")
        
    return jsonify({"status": "OK", "worker": w})

@app.route("/fall", methods=["POST"])
def receive_fall():
    data = request.get_json(force=True)
    wid = data.get("worker_id", "W1")
    force_status = data.get("status")
    samples = data.get("samples", [])
    
    w = get_worker(wid)
    
    if force_status:
        w["fall_status"] = force_status
    else:
        result = {"status": w["fall_status"], "prob": 0.0}
        for s in samples:
            if len(s) == 6:
                result = update_fall_state(s)
        w["fall_status"] = result.get("status", "SAFE")
        
    w["last_active"] = time.time()
    evaluate_alert(w)
    
    if w["fall_status"] == "FALL":
        log_incident(wid, "FALL", w["x"], w["y"], f"HR: {w['hr']}")
        
    return jsonify({"status": "OK", "worker": w})

@app.route("/location", methods=["POST"])
def receive_location():
    data = request.get_json(force=True)
    wid = data.get("worker_id", "W1")
    
    w = get_worker(wid)
    if "x" in data and "y" in data:
        w["x"] = float(data["x"])
        w["y"] = float(data["y"])
        
    w["last_active"] = time.time()
    evaluate_alert(w)
    
    file_exists = os.path.exists(LOCATION_LOG_PATH)
    with open(LOCATION_LOG_PATH, "a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        if not file_exists:
            writer.writerow(["timestamp", "worker_id", "x", "y", "alert_type"])
        writer.writerow([time.time(), wid, w["x"], w["y"], w["alert"]])
        
    return jsonify({"status": "OK"})

@app.route("/api/device_telemetry", methods=["POST"])
def receive_telemetry():
    '''
    Endpoint duy nhất hứng dữ liệu tổng hợp từ các Node ESP32 dưới hầm lên.
    Mẫu JSON Node gửi:
    { "worker_id": "W1", "telemetry": { "hr": 78, "gas": 3.4, "x": 10, "y": 20, "ax": 0.1, "ay": 1.0, ... "fall_alert": "SAFE" } }
    '''
    req_data = request.get_json(force=True)
    wid = req_data.get("worker_id", "Unknown")
    data = req_data.get("telemetry", {})
    
    w = get_worker(wid)
    
    # 1. Update Core
    w["x"] = data.get("x", w["x"])
    w["y"] = data.get("y", w["y"])
    w["hr"] = data.get("hr", w["hr"])
    w["gas"] = data.get("gas", w["gas"])
    w["fall_status"] = data.get("fall_alert", w["fall_status"])
    w["last_active"] = time.time()
    
    # 2. Update buffer lịch sử biểu đồ (giữ 20 điểm vẽ spline)
    if "history_imu" not in w:
        w["history_imu"] = {"ax":[], "ay":[], "az":[], "gx":[], "gy":[], "gz":[]}
        w["history_hr"] = []
        w["history_gas"] = []
        
    for k in ["ax", "ay", "az", "gx", "gy", "gz"]:
        w["history_imu"][k].append(data.get(k, 0))
        if len(w["history_imu"][k]) > 20: 
            w["history_imu"][k] = w["history_imu"][k][-20:]
            
    w["history_hr"].append(w["hr"])
    if len(w["history_hr"]) > 20: w["history_hr"] = w["history_hr"][-20:]
    
    w["history_gas"].append(w["gas"])
    if len(w["history_gas"]) > 20: w["history_gas"] = w["history_gas"][-20:]

    # 3. Phân loại mức độ Cảnh báo chung
    rule_status, rule_msg = rule_based_hr(w["hr"])
    w["hr_status"] = rule_status
    
    if w["gas"] >= 50: w["gas_status"] = "DANGER"
    elif w["gas"] >= 25: w["gas_status"] = "WARNING"
    else: w["gas_status"] = "SAFE"
    
    evaluate_alert(w)
    
    # Trace lại nhật ký cho Heatmap
    file_exists = os.path.exists(LOCATION_LOG_PATH)
    with open(LOCATION_LOG_PATH, "a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        if not file_exists:
            writer.writerow(["timestamp", "worker_id", "x", "y", "alert_type"])
        writer.writerow([time.time(), wid, w["x"], w["y"], w["alert"]])

    return jsonify({"status": "ACK", "system_time": time.time()})

@app.route("/latest_status", methods=["GET"])
def latest_status():
    return jsonify({"workers": list(workers.values())})

@app.route("/api/heatmap", methods=["GET"])
def api_heatmap():
    if not os.path.exists(LOCATION_LOG_PATH):
        return jsonify([])
    try:
        df = pd.read_csv(LOCATION_LOG_PATH)
        if df.empty: return jsonify([])
        df = df.tail(1500)
        points = df.to_dict(orient="records")
        return jsonify(points)
    except:
        return jsonify([])

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
