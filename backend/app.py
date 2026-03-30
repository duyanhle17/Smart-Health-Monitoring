import os
import csv
import time
import pandas as pd
from flask import Flask, request, jsonify, render_template
from flask_socketio import SocketIO
from flask_sqlalchemy import SQLAlchemy
from flask_cors import CORS

from backend.core.rules import rule_based_hr
from backend.core.fall.fall_state import update_fall_state
from backend.core.position_engine import (
    estimate_position, classify_zone, get_anchor_config
)

app = Flask(__name__)
CORS(app)
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL', 'sqlite:///local.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)
socketio = SocketIO(app, cors_allowed_origins="*")

class Personnel(db.Model):
    id = db.Column(db.String(50), primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    zone = db.Column(db.String(50), nullable=True)

import time
from sqlalchemy.exc import OperationalError

with app.app_context():
    retries = 15
    while retries > 0:
        try:
            db.create_all()
            # Mock data if empty
            if not Personnel.query.first():
                db.session.add(Personnel(id='WK_102', name='A. Chen', zone='GAMMA_STAGE'))
                db.session.add(Personnel(id='WK_048', name='J. Vance', zone='ALPHA_LEFT'))
                db.session.add(Personnel(id='WK_089', name='M. Johnson', zone='BETA_RIGHT'))
                db.session.add(Personnel(id='WK_004', name='E. Davis', zone='CENTER_PATH'))
                db.session.commit()
            print("Successfully connected to Database!")
            break
        except Exception as e:
            retries -= 1
            print(f"Database not ready, waiting... ({retries} retries left)")
            time.sleep(2)


BASE_DIR = os.path.dirname(__file__)
DATA_DIR = os.path.join(BASE_DIR, "data")
os.makedirs(DATA_DIR, exist_ok=True)

LOCATION_LOG_PATH = os.path.join(DATA_DIR, "mine_location_log.csv")
INCIDENT_LOG_PATH = os.path.join(DATA_DIR, "incident_log.csv")

# Global state
workers = {}
zones = {
    "ALPHA_LEFT": {"ch4": 0.3, "co": 4.0, "status": "SAFE", "aqi": 1},
    "BETA_RIGHT": {"ch4": 0.2, "co": 3.5, "status": "SAFE", "aqi": 1},
    "GAMMA_STAGE": {"ch4": 0.5, "co": 6.0, "status": "SAFE", "aqi": 1},
    "CENTER_PATH": {"ch4": 0.1, "co": 2.0, "status": "SAFE", "aqi": 0}
}
current_scenario = "NORMAL"

def get_worker(wid):
    if wid not in workers:
        workers[wid] = {
            "worker_id": wid,
            "hr": 75,
            "hr_status": "NORMAL",
            "hr_msg": "",
            "temp": 36.5,
            "ch4": 0.0,
            "co": 0.0,
            "env_status": "SAFE",
            "aqi": 0,
            "fall_status": "SAFE",
            "x": 50.0,
            "y": 50.0,
            "zone": "CENTER_PATH",
            "last_active": time.time(),
            "alert": "NORMAL",
            "history_imu": {"ax":[], "ay":[], "az":[], "gx":[], "gy":[], "gz":[]},
            "history_hr": [],
            "history_ch4": [],
            "history_co": [],
            "history_pos": []
        }
    return workers[wid]

def evaluate_alert(w):
    # offline takes precedence in UI
    if time.time() - w.get("last_active", time.time()) > 3.0:
        w["alert"] = "OFFLINE"
        return

    is_danger = w["fall_status"] == "FALL" or w["env_status"] == "DANGER" or "DANGER" in w["hr_status"]
    is_warning = w["env_status"] == "WARNING" or "WARNING" in w["hr_status"]
    
    if is_danger: w["alert"] = "DANGER"
    elif is_warning: w["alert"] = "WARNING"
    else: w["alert"] = "NORMAL"

def update_zone_data(zone_id, ch4, co):
    if zone_id in zones:
        zones[zone_id]["ch4"] = round(ch4, 2)
        zones[zone_id]["co"] = round(co, 1)
        
        aqi = round(max(0, min(10, max(ch4 * 2.0, co / 15.0))), 1)
        zones[zone_id]["aqi"] = aqi
        
        if aqi >= 8.0: zones[zone_id]["status"] = "DANGER"
        elif aqi >= 4.0: zones[zone_id]["status"] = "WARNING"
        else: zones[zone_id]["status"] = "SAFE"

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/api/scenario", methods=["GET", "POST"])
def api_scenario():
    global current_scenario
    if request.method == "POST":
        req_data = request.get_json(force=True)
        new_scenario = req_data.get("scenario", "NORMAL")
        current_scenario = new_scenario
        socketio.emit('scenario_changed', {"scenario": current_scenario})
        return jsonify({"status": "ACK", "scenario": current_scenario})
    return jsonify({"scenario": current_scenario})

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
        update_zone_data(zone_id, data.get("ch4", 0.0), data.get("co", 0.0))
        
        socketio.emit('latest_status', {"workers": list(workers.values()), "zones": zones})
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
    w["ch4"] = data.get("ch4", w["ch4"])
    w["co"] = data.get("co", w.get("co", 0.0))
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
    aqi = round(max(0, min(10, max(w["ch4"] * 2.0, w["co"] / 15.0))), 1)
    w["aqi"] = aqi
    if aqi >= 8.0: w["env_status"] = "DANGER"
    elif aqi >= 4.0: w["env_status"] = "WARNING"
    else: w["env_status"] = "SAFE"
    evaluate_alert(w)
    
    
    socketio.emit('latest_status', {"workers": list(workers.values()), "zones": zones})
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

@app.route("/api/personnel", methods=["GET"])
def get_personnel():
    people = Personnel.query.all()
    return jsonify([{'id': p.id, 'name': p.name, 'zone': p.zone} for p in people])

def background_timeout_checker():
    while True:
        socketio.sleep(1.0)
        changed = False
        for wid, w in workers.items():
            if time.time() - w.get("last_active", time.time()) > 3.0 and w["alert"] != "OFFLINE":
                w["alert"] = "OFFLINE"
                changed = True
        if changed:
            socketio.emit('latest_status', {"workers": list(workers.values()), "zones": zones})

if __name__ == "__main__":
    socketio.start_background_task(background_timeout_checker)
    socketio.run(app, host="0.0.0.0", port=int(os.environ.get('PORT', 5000)), allow_unsafe_werkzeug=True)
