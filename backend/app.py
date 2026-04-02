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
import logging
from logging.handlers import RotatingFileHandler
from backend.core.position_engine import (
    estimate_position, classify_zone, get_anchor_config, reset_smooth_state
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
                db.session.add(Personnel(id='WK_102', name='Trung Nam', zone='GAMMA_STAGE'))
                db.session.add(Personnel(id='WK_048', name='Duy Anh', zone='ALPHA_LEFT'))
                db.session.add(Personnel(id='WK_089', name='Quoc Khanh', zone='BETA_RIGHT'))
                db.session.add(Personnel(id='WK_004', name='Ngoc DIem', zone='CENTER_PATH'))
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

# Setup Logging for Hardware Telemetry
log_formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
log_file = os.path.join(DATA_DIR, 'hardware_telemetry.log')
file_handler = RotatingFileHandler(log_file, maxBytes=5*1024*1024, backupCount=2)
file_handler.setFormatter(log_formatter)

console_handler = logging.StreamHandler()
console_handler.setFormatter(log_formatter)

hw_logger = logging.getLogger('hardware_telemetry')
hw_logger.setLevel(logging.INFO)
hw_logger.addHandler(file_handler)
hw_logger.addHandler(console_handler)

def calculate_aqi(ch4, co):
    if ch4 < 2.0:
        ch4_aqi = 10.0 - (ch4 / 2.0) * 3.0
    elif ch4 < 4.0:
        ch4_aqi = 7.0 - ((ch4 - 2.0) / 2.0) * 4.0
    else:
        ch4_aqi = max(0.0, 3.0 - ((ch4 - 4.0) / 2.0) * 3.0)
        
    if co < 60.0:
        co_aqi = 10.0 - (co / 60.0) * 3.0
    elif co < 120.0:
        co_aqi = 7.0 - ((co - 60.0) / 60.0) * 4.0
    else:
        co_aqi = max(0.0, 3.0 - ((co - 120.0) / 60.0) * 3.0)
        
    return round(min(ch4_aqi, co_aqi), 1)

# Global state
workers = {}
zones = {
    "ALPHA_LEFT": {"ch4": 0.3, "co": 4.0, "status": "SAFE", "aqi": 9.6},
    "DELTA_CENTER": {"ch4": 0.1, "co": 1.0, "status": "SAFE", "aqi": 9.9},
    "BETA_RIGHT": {"ch4": 0.2, "co": 3.5, "status": "SAFE", "aqi": 9.7},
    "GAMMA_STAGE": {"ch4": 0.5, "co": 6.0, "status": "SAFE", "aqi": 9.3},
    "CENTER_PATH": {"ch4": 0.1, "co": 2.0, "status": "SAFE", "aqi": 9.9}
}
current_scenario = "NORMAL"

# Admin override state
simulator_speed_config = {}
simulator_reset_flags = {}
manual_overrides = {}  # {worker_id: {"x": float, "y": float, "alert": str | None}}
hidden_nodes_global = {} # {node_id: bool}
custom_anchors = {} # {anchor_id: {"x": float, "y": float}}

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
            "history_pos": [],
            "yaw": 0.0
        }
    return workers[wid]

def evaluate_alert(w):
    # offline takes precedence in UI
    # Exception for WK_102: Must stay connected for hardware demo
    is_trung_nam = w.get("worker_id") == "WK_102"
    timeout = 3.0
    if is_trung_nam: timeout = 1000000.0 # Stay alive for demo purposes
    
    if time.time() - w.get("last_active", time.time()) > timeout:
        w["alert"] = "OFFLINE"
        return
        
    if w.get("fall_status") == "FALL":
        w["alert"] = "OFFLINE" # Ngắt kết nối mô phỏng hư phần cứng
        return

    is_danger = w["env_status"] == "DANGER" or "DANGER" in w["hr_status"]
    is_warning = w["env_status"] == "WARNING" or "WARNING" in w["hr_status"]
    
    if is_danger: w["alert"] = "DANGER"
    elif is_warning: w["alert"] = "WARNING"
    else: w["alert"] = "NORMAL"

def update_zone_data(zone_id, ch4, co, from_worker=False):
    """Update zone environmental data.
    If from_worker=True, blend worker readings into zone using exponential smoothing
    so the zone tracks toward the worst readings but can also decay.
    """
    if zone_id in zones:
        if from_worker:
            # Blend: zone moves toward the worse of (current, worker) reading
            alpha = 0.3  # responsiveness
            cur_ch4 = zones[zone_id].get("ch4", 0)
            cur_co = zones[zone_id].get("co", 0)
            ch4 = cur_ch4 + alpha * (ch4 - cur_ch4)
            co = cur_co + alpha * (co - cur_co)
        zones[zone_id]["ch4"] = round(ch4, 2)
        zones[zone_id]["co"] = round(co, 1)
        
        aqi = calculate_aqi(ch4, co)
        zones[zone_id]["aqi"] = aqi
        
        if aqi <= 3.0: zones[zone_id]["status"] = "DANGER"
        elif aqi <= 7.0: zones[zone_id]["status"] = "WARNING"
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
        
        socketio.emit('latest_status', {"workers": list(workers.values()), "zones": zones, "hiddenNodes": hidden_nodes_global, "customAnchors": custom_anchors})
        return jsonify({"status": "ACK", "zone": zone_id})
    return jsonify({"status": "ERROR", "msg": "Anchor not mapped to zone"}), 400

@app.route("/api/device_telemetry", methods=["POST"])
def receive_telemetry():
    req_data = request.get_json(force=True)
    wid = req_data.get("worker_id", "Unknown")
    data = req_data.get("telemetry", {})
    w = get_worker(wid)
    
    # Priority logic: Real hardware overrides Simulator
    is_sim = data.get("is_simulated", False)
    if is_sim:
        last_real = w.get("last_real_active", 0)
        if time.time() - last_real < 5.0:
            return jsonify({"status": "IGNORED", "reason": "Real hardware active"}), 200
    else:
        w["last_real_active"] = time.time()
    
    # 1. Position
    d1 = float(data.get("d1", 0.0))
    d2 = float(data.get("d2", 0.0))
    d3 = float(data.get("d3", 0.0))
    
    if "yaw" in data:
        w["yaw"] = float(data["yaw"])
        
    # Chỉ cần d1 và yaw là tính được tọa độ (Single-Anchor)
    if "d1" in data:
        x_est, y_est = estimate_position(wid, d1, d2, d3, w.get("yaw", 0.0))
        w["x"], w["y"] = x_est, y_est
    else:
        w["x"] = data.get("x", w["x"])
        w["y"] = data.get("y", w["y"])
        
    if wid in manual_overrides:
        if "x" in manual_overrides[wid]: w["x"] = manual_overrides[wid]["x"]
        if "y" in manual_overrides[wid]: w["y"] = manual_overrides[wid]["y"]

    w["zone"] = classify_zone(w["x"], w["y"])
    
    # 2. Vitals
    # Cảm biến ở hardware có thể gửi chữ "bpm" thay vì "hr"
    w["hr"] = data.get("hr", data.get("bpm", w["hr"]))
    w["temp"] = data.get("temp", data.get("tempC", w["temp"]))
    w["ch4"] = data.get("ch4", w["ch4"])
    w["co"] = data.get("co", w.get("co", 0.0))
    
    # 2.5 AI Fall Detection Integration
    if all(k in data for k in ["ax", "ay", "az", "gx", "gy", "gz"]):
        sample = [data["ax"], data["ay"], data["az"], data["gx"], data["gy"], data["gz"]]
        fall_res = update_fall_state(wid, sample)
        w["fall_status"] = fall_res["status"]
    else:
        w["fall_status"] = data.get("fall_alert", w["fall_status"])

    if not is_sim:
        hw_logger.info(f"Node: {wid} | HR: {w['hr']} | Temp: {w['temp']:.1f} | Fall: {w['fall_status']} | CH4: {w['ch4']} | CO: {w['co']} | Pos: ({w['x']:.1f}, {w['y']:.1f})")
        
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
    aqi = calculate_aqi(w["ch4"], w["co"])
    w["aqi"] = aqi
    if aqi <= 3.0: w["env_status"] = "DANGER"
    elif aqi <= 7.0: w["env_status"] = "WARNING"
    else: w["env_status"] = "SAFE"
    
    # Also update zone with worker's gas readings (merge = take worst/max)
    if w["zone"] in zones:
        update_zone_data(w["zone"], w["ch4"], w["co"], from_worker=True)
    
    evaluate_alert(w)

    if wid in manual_overrides and "alert" in manual_overrides[wid]:
        w["alert"] = manual_overrides[wid]["alert"]
    
    
    socketio.emit('latest_status', {"workers": list(workers.values()), "zones": zones, "hiddenNodes": hidden_nodes_global, "customAnchors": custom_anchors})
    return jsonify({"status": "ACK"})

@app.route("/api/admin/node", methods=["POST"])
def admin_override_node():
    """Admin override: drag worker to new position or force alert/env on anchor."""
    data = request.get_json(force=True)
    wid = data.get("worker_id")
    aid = data.get("anchor_id")

    if wid:
        w = get_worker(wid)
        override = {}
        if "x" in data and data["x"] != '':
            w["x"] = float(data["x"])
            override["x"] = w["x"]
        if "y" in data and data["y"] != '':
            w["y"] = float(data["y"])
            override["y"] = w["y"]
        if "alert" in data:
            w["alert"] = data["alert"]
            override["alert"] = data["alert"]
        if "speed" in data and data["speed"] != '':
            speed_val = float(data["speed"])
            simulator_speed_config[wid] = speed_val
            # Auto-release manual positional lock so the simulator can actually move the node physically
            if speed_val > 0:
                reset_smooth_state(wid) # Snap immediately to true position

                if "x" in data and data["x"] != '' and "y" in data and data["y"] != '':
                    simulator_reset_flags[wid] = {"x": float(data["x"]), "y": float(data["y"])}
                else:
                    simulator_reset_flags[wid] = True

                override.pop("x", None)
                override.pop("y", None)
                if wid in manual_overrides:
                    manual_overrides[wid].pop("x", None)
                    manual_overrides[wid].pop("y", None)
        
        if override:
            if wid not in manual_overrides:
                manual_overrides[wid] = {}
            manual_overrides[wid].update(override)
            
        # Clean up empty overrides dictionary
        if wid in manual_overrides and not manual_overrides[wid]:
            del manual_overrides[wid]
        w["zone"] = classify_zone(w["x"], w["y"])
        w["last_active"] = time.time()
        socketio.emit('latest_status', {"workers": list(workers.values()), "zones": zones, "hiddenNodes": hidden_nodes_global, "customAnchors": custom_anchors})
        return jsonify({"status": "ACK", "worker_id": wid})

    if aid:
        if "x" in data and data["x"] != '':
            if aid not in custom_anchors: custom_anchors[aid] = {}
            custom_anchors[aid]["x"] = float(data["x"])
        if "y" in data and data["y"] != '':
            if aid not in custom_anchors: custom_anchors[aid] = {}
            custom_anchors[aid]["y"] = float(data["y"])
        
        zone_map = {"ANC_STAGE": "GAMMA_STAGE", "ANC_LEFT": "ALPHA_LEFT", "ANC_RIGHT": "BETA_RIGHT"}
        zone_id = zone_map.get(aid)
        if "ch4" in data and data["ch4"] != '':
            ch4 = float(data["ch4"])
            co = float(data.get("co", 0))
            if zone_id:
                update_zone_data(zone_id, ch4, co)
        socketio.emit('latest_status', {"workers": list(workers.values()), "zones": zones, "hiddenNodes": hidden_nodes_global, "customAnchors": custom_anchors})
        return jsonify({"status": "ACK", "anchor_id": aid})

    return jsonify({"status": "ERROR", "msg": "No worker_id or anchor_id"}), 400

@app.route("/api/admin/clear_override", methods=["POST"])
def admin_clear_override():
    data = request.get_json(force=True)
    wid = data.get("worker_id")
    aid = data.get("anchor_id")
    if wid and wid in manual_overrides:
        del manual_overrides[wid]
    if wid and wid in simulator_speed_config:
        del simulator_speed_config[wid]
    return jsonify({"status": "ACK"})

@app.route("/api/admin/toggle_node", methods=["POST"])
def admin_toggle_node():
    data = request.get_json(force=True)
    nid = data.get("node_id")
    if nid:
        hidden_nodes_global[nid] = not hidden_nodes_global.get(nid, False)
        socketio.emit('latest_status', {"workers": list(workers.values()), "zones": zones, "hiddenNodes": hidden_nodes_global, "customAnchors": custom_anchors})
        return jsonify({"status": "ACK", "hiddenNodes": hidden_nodes_global})
    return jsonify({"status": "ERROR"}), 400

@app.route("/api/admin/simulator_config", methods=["GET"])
def admin_simulator_config():
    resets = simulator_reset_flags.copy()
    simulator_reset_flags.clear()
    return jsonify({
        "speed": simulator_speed_config,
        "resets": resets,
        "manual_overrides": {k: True for k in manual_overrides}
    })

@app.route("/latest_status", methods=["GET"])
def latest_status():
    return jsonify({"workers": list(workers.values()), "zones": zones, "hiddenNodes": hidden_nodes_global, "customAnchors": custom_anchors})

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
            timeout = 3.0
            if wid == "WK_102" or wid in manual_overrides:
                timeout = 1000000.0  # Prevent auto-disconnect for hardware demo node or manually controlled nodes
                
            if time.time() - w.get("last_active", time.time()) > timeout and w["alert"] != "OFFLINE":
                w["alert"] = "OFFLINE"
                changed = True
        if changed:
            socketio.emit('latest_status', {"workers": list(workers.values()), "zones": zones, "hiddenNodes": hidden_nodes_global, "customAnchors": custom_anchors})

if __name__ == "__main__":
    socketio.start_background_task(background_timeout_checker)
    socketio.run(app, host="0.0.0.0", port=int(os.environ.get('PORT', 5000)), allow_unsafe_werkzeug=True)
