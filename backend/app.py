import os
import csv
import time
import pandas as pd
from flask import Flask, request, jsonify, render_template
from flask_cors import CORS

from backend.core.rules import rule_based_hr
from backend.core.fall.fall_state import update_fall_state
from backend.core.position_engine import (
    estimate_position, classify_zone, get_anchor_config
)

app = Flask(__name__)
CORS(app)

BASE_DIR = os.path.dirname(__file__)
DATA_DIR = os.path.join(BASE_DIR, "data")
os.makedirs(DATA_DIR, exist_ok=True)

LOCATION_LOG_PATH = os.path.join(DATA_DIR, "mine_location_log.csv")
INCIDENT_LOG_PATH = os.path.join(DATA_DIR, "incident_log.csv")

# Global state
workers = {}
zones = {
    "ALPHA_LEFT": {"gas": 1.2, "o2": 20.9, "status": "SAFE"},
    "BETA_RIGHT": {"gas": 0.8, "o2": 20.9, "status": "SAFE"},
    "GAMMA_STAGE": {"gas": 2.5, "o2": 20.9, "status": "SAFE"},
    "CENTER_PATH": {"gas": 0.5, "o2": 20.9, "status": "SAFE"}
}

def get_worker(wid):
    if wid not in workers:
        workers[wid] = {
            "worker_id": wid,
            "hr": 75,
            "hr_status": "NORMAL",
            "hr_msg": "",
            "temp": 36.5,
            "gas": 0.0,
            "o2": 20.9,
            "gas_status": "SAFE",
            "fall_status": "SAFE",
            "x": 50.0,
            "y": 50.0,
            "zone": "CENTER_PATH",
            "last_active": time.time(),
            "alert": "NORMAL",
            "history_imu": {"ax":[], "ay":[], "az":[], "gx":[], "gy":[], "gz":[]},
            "history_hr": [],
            "history_gas": [],
            "history_o2": [],
            "history_pos": []
        }
    return workers[wid]

def evaluate_alert(w):
    is_danger = w["fall_status"] == "FALL" or w["gas_status"] == "DANGER" or "DANGER" in w["hr_status"]
    is_warning = w["gas_status"] == "WARNING" or "WARNING" in w["hr_status"]
    
    if is_danger: w["alert"] = "DANGER"
    elif is_warning: w["alert"] = "WARNING"
    else: w["alert"] = "NORMAL"

def update_zone_data(zone_id, gas, o2):
    if zone_id in zones:
        zones[zone_id]["gas"] = round(gas, 2)
        zones[zone_id]["o2"] = round(o2, 1)
        if gas >= 50 or o2 <= 18.5: zones[zone_id]["status"] = "DANGER"
        elif gas >= 25 or o2 <= 19.5: zones[zone_id]["status"] = "WARNING"
        else: zones[zone_id]["status"] = "SAFE"

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/api/anchors", methods=["GET"])
def api_anchors():
    return jsonify({"anchors": get_anchor_config()})

@app.route("/api/anchor_telemetry", methods=["POST"])
def receive_anchor_telemetry():
    """Endpoint dành riêng cho các trạm Anchor cố định gửi dữ liệu môi trường khu vực."""
    req_data = request.get_json(force=True)
    anchor_id = req_data.get("anchor_id", "Unknown")
    zone_map = {
        "ANC_STAGE": "GAMMA_STAGE",
        "ANC_LEFT": "ALPHA_LEFT",
        "ANC_RIGHT": "BETA_RIGHT"
    }
    zone_id = zone_map.get(anchor_id)
    data = req_data.get("telemetry", {})
    if zone_id:
        update_zone_data(zone_id, data.get("gas", 0), data.get("o2", 20.9))
        return jsonify({"status": "ACK", "zone": zone_id})
    return jsonify({"status": "ERROR", "msg": "Anchor not mapped to zone"}), 400

@app.route("/api/device_telemetry", methods=["POST"])
def receive_telemetry():
    req_data = request.get_json(force=True)
    wid = req_data.get("worker_id", "Unknown")
    data = req_data.get("telemetry", {})
    w = get_worker(wid)
    
    # 1. Position
    if "d1" in data and "d2" in data and "d3" in data:
        x_est, y_est = estimate_position(wid, float(data["d1"]), float(data["d2"]), float(data["d3"]))
        w["x"], w["y"] = x_est, y_est
    else:
        w["x"] = data.get("x", w["x"])
        w["y"] = data.get("y", w["y"])
    w["zone"] = classify_zone(w["x"], w["y"])
    
    # 2. Vitals
    w["hr"] = data.get("hr", w["hr"])
    w["temp"] = data.get("temp", w["temp"])
    w["gas"] = data.get("gas", w["gas"])
    w["o2"] = data.get("o2", w.get("o2", 20.9))
    w["fall_status"] = data.get("fall_alert", w["fall_status"])
    w["last_active"] = time.time()
    
    # 3. History
    for k in ["ax", "ay", "az", "gx", "gy", "gz"]:
        w["history_imu"][k].append(data.get(k, 0))
        if len(w["history_imu"][k]) > 20: w["history_imu"][k].pop(0)
    w["history_hr"].append(w["hr"])
    if len(w["history_hr"]) > 20: w["history_hr"].pop(0)

    # 4. Alert Logic
    rule_status, rule_msg = rule_based_hr(w["hr"])
    w["hr_status"] = rule_status
    if w["gas"] >= 50 or w["o2"] <= 18.5: w["gas_status"] = "DANGER"
    elif w["gas"] >= 25 or w["o2"] <= 19.5: w["gas_status"] = "WARNING"
    else: w["gas_status"] = "SAFE"
    evaluate_alert(w)
    
    return jsonify({"status": "ACK"})

@app.route("/latest_status", methods=["GET"])
def latest_status():
    return jsonify({"workers": list(workers.values()), "zones": zones})

@app.route("/api/heatmap", methods=["GET"])
def api_heatmap():
    if not os.path.exists(LOCATION_LOG_PATH): return jsonify([])
    try:
        df = pd.read_csv(LOCATION_LOG_PATH)
        return jsonify(df.tail(1000).to_dict(orient="records"))
    except: return jsonify([])

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
