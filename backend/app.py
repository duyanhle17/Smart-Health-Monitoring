import math
import os
import csv
import time
import pandas as pd
import hmac
from flask import Flask, request, jsonify
from flask_socketio import SocketIO
from flask_sqlalchemy import SQLAlchemy
from flask_cors import CORS

from backend.core.rules import rule_based_hr
from backend.core.fall.fall_state import update_fall_state
from backend.core.exhaustion.exhaustion_state import update_exhaustion_state
import logging
from logging.handlers import RotatingFileHandler
from backend.core.position_engine import (
    estimate_position, classify_zone, get_anchor_config, get_fix_status,
    get_position_config, is_publishable_uwb_fix, reset_smooth_state
)
from backend.core.uwb_calibration import RangeCalibrationCapture


def _env_bool(name, default=False):
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _env_float(name, default, minimum=0.0):
    try:
        value = float(os.environ.get(name, default))
    except (TypeError, ValueError):
        return default
    return value if math.isfinite(value) and value >= minimum else default


# The public deployment is a live safety dashboard. Simulated telemetry is
# rejected unless a demo stack opts in explicitly via env.
ALLOW_SIMULATED_TELEMETRY = _env_bool("SAFEWORK_ALLOW_SIMULATOR", False)
# Loss-of-vitals alarm (owner-approved thresholds): a tag that keeps posting
# telemetry without a valid pulse escalates WARNING → DANGER; a tag that stops
# posting entirely goes OFFLINE. All three are per-deployment tunable.
PULSE_WARNING_SECONDS = _env_float("SAFEWORK_PULSE_WARNING_SECONDS", 15.0, minimum=1.0)
PULSE_DANGER_SECONDS = _env_float("SAFEWORK_PULSE_DANGER_SECONDS", 30.0, minimum=1.0)
OFFLINE_TIMEOUT_SECONDS = _env_float("SAFEWORK_OFFLINE_TIMEOUT_SECONDS", 60.0, minimum=1.0)
# Admin override endpoints are open only when no PIN is configured (local dev).
ADMIN_PIN = os.environ.get("SAFEWORK_ADMIN_PIN", "").strip()
# A single lost UWB response must not make a real marker disappear on the next
# telemetry cycle. Held coordinates are explicitly labelled stale and expire
# quickly; they are never a substitute for a new position calculation.
UWB_FIX_HOLD_SECONDS = _env_float("UWB_FIX_HOLD_SECONDS", 15.0, minimum=0.0)
# After the short orange hold window, retain a clearly-labelled gray last-known
# marker while telemetry is still alive. This avoids a healthy worker blinking
# off the map during a burst of invalid UWB geometry without claiming that the
# old coordinate is a fresh range solution.
UWB_LAST_KNOWN_VISIBLE_SECONDS = _env_float("UWB_LAST_KNOWN_VISIBLE_SECONDS", 60.0, minimum=0.0)

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
                db.session.add(Personnel(id='WK_004', name='Ngoc Diem', zone='CENTER_PATH'))
                db.session.commit()
            print("Successfully connected to Database!")
            break
        except Exception as e:
            retries -= 1
            print(f"Database not ready, waiting... ({retries} retries left)")
            time.sleep(2)


BASE_DIR = os.path.dirname(__file__)
# Deployment mounts /app/data as a persistent Docker volume. Keep hardware
# telemetry and incident/location exports there instead of losing them on a
# container rebuild.
DATA_DIR = os.environ.get("SAFEWORK_DATA_DIR", os.path.join(BASE_DIR, "data"))
os.makedirs(DATA_DIR, exist_ok=True)

LOCATION_LOG_PATH = os.path.join(DATA_DIR, "mine_location_log.csv")
INCIDENT_LOG_PATH = os.path.join(DATA_DIR, "incident_log.csv")
# Vitals stream + operator-supplied Borg RPE labels. Together these let us
# train an exhaustion model on GROUND TRUTH that is independent of the PSI
# formula (train_exhaustion_real.py joins them by worker + timestamp).
VITALS_HISTORY_PATH = os.path.join(DATA_DIR, "vitals_history.csv")
EXHAUSTION_LABEL_PATH = os.path.join(DATA_DIR, "exhaustion_rpe_labels.csv")


def _append_csv(path, header, row):
    """Append one row, writing the header first if the file is new/empty."""
    try:
        new = not os.path.exists(path) or os.path.getsize(path) == 0
        with open(path, "a", newline="") as fh:
            w = csv.writer(fh)
            if new:
                w.writerow(header)
            w.writerow(row)
    except OSError as exc:
        hw_logger.warning(f"csv append failed {path}: {exc}")

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

# Global state. Do not seed the live dashboard with demo gas values: a zone is
# unknown until an anchor or a declared gas-capable worker reports it.
workers = {}


def _unknown_zone():
    return {"ch4": None, "co": None, "status": "UNKNOWN", "aqi": None, "source": "unavailable"}


zones = {
    "ALPHA_LEFT": _unknown_zone(),
    "DELTA_CENTER": _unknown_zone(),
    "BETA_RIGHT": _unknown_zone(),
    "GAMMA_STAGE": _unknown_zone(),
    "CENTER_PATH": _unknown_zone(),
}
current_scenario = "NORMAL"

# Admin override state
simulator_speed_config = {}
simulator_reset_flags = {}
manual_overrides = {}  # {worker_id: {"x": float, "y": float, "alert": str | None}}
hidden_nodes_global = {} # {node_id: bool}
custom_anchors = {} # {anchor_id: {"x": float, "y": float}}
last_valid_uwb_fixes = {}  # worker -> {"at": epoch, "status": UWB diagnostic}
# Operator-started known-point captures. They recommend offsets but never
# mutate live calibration automatically.
uwb_calibration_captures = {}


def calibration_status(capture):
    """Attach active deployment values so offsets are replaced, never added."""
    status = capture.status()
    active_offsets = get_position_config()["range_offsets_m"]
    status["active_offsets_m"] = active_offsets
    recommendation = status.get("recommended_offsets_m")
    if recommendation:
        status["replacement_delta_m"] = {
            key: round(recommendation[key] - active_offsets[key], 4)
            for key in ("d1", "d2")
        }
    return status

def get_worker(wid):
    if wid not in workers:
        workers[wid] = {
            "worker_id": wid,
            "hr": "--",
            "hr_status": "NORMAL",
            "hr_msg": "",
            "temp": "--",
            "ch4": None,
            "co": None,
            "gas_available": False,
            "env_status": "UNKNOWN",
            "aqi": None,
            "fall_status": "SAFE",
            # Kiệt sức (exhaustion) — chỉ số strain sinh lý từ nhịp tim + thân
            # nhiệt (+ huyết áp nếu có). NORMAL/MILD/MODERATE/SEVERE, điểm 0-10.
            "exhaustion_status": "NORMAL",
            "exhaustion_level": 0,
            "exhaustion_score": 0.0,
            "exhaustion_load": 0.0,
            "exhaustion_source": "none",
            "x": 50.0,
            "y": 50.0,
            "zone": "CENTER_PATH",
            "last_active": time.time(),
            # Loss-of-pulse tracking: last time a valid HR reading arrived and
            # the current escalation ("", "WARNING", "DANGER").
            "last_pulse_at": time.time(),
            "pulse_lost": "",
            "alert": "NORMAL",
            "history_imu": {"ax":[], "ay":[], "az":[], "gx":[], "gy":[], "gz":[]},
            "history_hr": [],
            "history_ch4": [],
            "history_co": [],
            "history_pos": [],
            "yaw": 0.0,
            "steps": None,
            "location_valid": False,
            "location_stale": False,
            "location_last_known": False,
            # True only for the explicitly labelled, on-anchor-line fallback.
            # It is a real range-derived along-line estimate, but never 2-D.
            "location_degraded": False,
            # A map coordinate can be derived from current real UWB ranges
            # before its RF link offsets have been surveyed. Keep that
            # confidence separate from validity so the UI never hides a real
            # measurement behind the harmless default coordinate.
            "location_calibrated": False,
        }
    return workers[wid]


def hold_or_invalidate_uwb_fix(wid, worker, reason, current_status=None):
    """Retain a real last UWB coordinate with explicit freshness states."""
    now = time.time()
    cached = last_valid_uwb_fixes.get(wid)
    if cached:
        age_s = max(0.0, now - cached["at"])
        if age_s <= UWB_FIX_HOLD_SECONDS:
            held = dict(cached["status"])
            held.update({
                "valid": False,
                "reason": reason,
                "held": True,
                "fix_age_ms": int(age_s * 1000),
            })
            if current_status and current_status.get("reason"):
                held["last_measurement_reason"] = current_status["reason"]
            worker["uwb"] = held
            worker["location_valid"] = True
            worker["location_stale"] = True
            worker["location_last_known"] = False
            worker["location_calibrated"] = bool(held.get("calibrated"))
            worker["location_degraded"] = bool(
                held.get("degraded") or held.get("geometry_mode") == "line"
            )
            return
        if age_s <= UWB_LAST_KNOWN_VISIBLE_SECONDS:
            known = dict(cached["status"])
            known.update({
                "valid": False,
                "reason": reason,
                "last_known": True,
                "fix_age_ms": int(age_s * 1000),
            })
            if current_status and current_status.get("reason"):
                known["last_measurement_reason"] = current_status["reason"]
            worker["uwb"] = known
            worker["location_valid"] = False
            worker["location_stale"] = True
            worker["location_last_known"] = True
            worker["location_calibrated"] = bool(known.get("calibrated"))
            worker["location_degraded"] = bool(
                known.get("degraded") or known.get("geometry_mode") == "line"
            )
            return
        last_valid_uwb_fixes.pop(wid, None)

    worker["uwb"] = current_status or {
        "valid": False,
        "reason": reason,
        "calibrated": get_position_config()["calibrated"],
        "pdr_available": False,
    }
    worker["location_valid"] = False
    worker["location_stale"] = False
    worker["location_last_known"] = False
    worker["location_calibrated"] = False
    worker["location_degraded"] = False


def update_worker_zone(worker):
    """Do not assign an environmental zone from a deliberately 1-D UWB fix."""
    if worker.get("location_degraded"):
        worker["zone"] = "LINE_1D"
    else:
        worker["zone"] = classify_zone(worker["x"], worker["y"])

def evaluate_alert(w):
    # offline takes precedence in UI
    if time.time() - w.get("last_active", time.time()) > OFFLINE_TIMEOUT_SECONDS:
        w["alert"] = "OFFLINE"
        # A silent tag is a signal-loss incident, not a pulse-loss one; a
        # frozen pulse_lost flag would mislabel the failure mode in the UI.
        w["pulse_lost"] = ""
        return
        
    if w.get("fall_status") == "FALL":
        w["alert"] = "DANGER" # Chuyển thẳng sang DANGER để UI Dashboard nổ báo động đỏ
        return

    is_danger = w["env_status"] == "DANGER" or "DANGER" in w["hr_status"]
    is_warning = (
        w["env_status"] == "WARNING"
        or "WARNING" in w["hr_status"]
        # Kiệt sức nặng là mối lo an toàn thật nhưng không cấp tính như ngã/khí
        # độc -> nâng cảnh báo VÀNG, không nhảy thẳng ĐỎ. Bỏ dòng này nếu chỉ
        # muốn hiển thị cấp độ mà không đổi trạng thái cảnh báo.
        or w.get("exhaustion_status") == "SEVERE"
    )

    if is_danger: w["alert"] = "DANGER"
    elif is_warning: w["alert"] = "WARNING"
    else: w["alert"] = "NORMAL"

def update_zone_data(zone_id, ch4, co, from_worker=False):
    """Update zone environmental data.
    If from_worker=True, blend worker readings into zone using exponential smoothing
    so the zone tracks toward the worst readings but can also decay.
    """
    if zone_id in zones:
        try:
            ch4 = float(ch4)
            co = float(co)
        except (TypeError, ValueError):
            return
        if not math.isfinite(ch4) or not math.isfinite(co):
            return
        if from_worker:
            # Blend: zone moves toward the worse of (current, worker) reading
            alpha = 0.3  # responsiveness
            cur_ch4 = zones[zone_id].get("ch4")
            cur_co = zones[zone_id].get("co")
            if isinstance(cur_ch4, (int, float)) and isinstance(cur_co, (int, float)):
                ch4 = cur_ch4 + alpha * (ch4 - cur_ch4)
                co = cur_co + alpha * (co - cur_co)
        zones[zone_id]["ch4"] = round(ch4, 2)
        zones[zone_id]["co"] = round(co, 1)
        zones[zone_id]["source"] = "worker" if from_worker else "anchor"
        
        aqi = calculate_aqi(ch4, co)
        zones[zone_id]["aqi"] = aqi
        
        if aqi <= 3.0: zones[zone_id]["status"] = "DANGER"
        elif aqi <= 7.0: zones[zone_id]["status"] = "WARNING"
        else: zones[zone_id]["status"] = "SAFE"

@app.route("/")
def index():
    # The legacy Leaflet dashboard (templates/index.html) is retired; the React
    # app served by nginx is the only UI. Keep "/" as a plain service banner.
    return jsonify({"service": "SafeWork API", "status": "ok"})


def require_admin_pin():
    """403 unless the request carries the configured admin PIN.

    With SAFEWORK_ADMIN_PIN unset (local dev), admin endpoints stay open."""
    if not ADMIN_PIN:
        return None
    supplied = request.headers.get("X-Admin-Pin", "")
    # Compare as bytes: compare_digest raises TypeError on non-ASCII str.
    if not hmac.compare_digest(supplied.encode("utf-8"), ADMIN_PIN.encode("utf-8")):
        return jsonify({"status": "ERROR", "msg": "Admin PIN required"}), 403
    return None


@app.route("/api/admin/verify", methods=["POST"])
def admin_verify():
    denied = require_admin_pin()
    if denied:
        return denied
    return jsonify({"status": "OK", "pin_required": bool(ADMIN_PIN)})


@app.route("/api/scenario", methods=["GET", "POST"])
def api_scenario():
    global current_scenario
    if request.method == "POST":
        denied = require_admin_pin()
        if denied:
            return denied
        req_data = request.get_json(force=True)
        new_scenario = req_data.get("scenario", "NORMAL")
        current_scenario = new_scenario
        socketio.emit('scenario_changed', {"scenario": current_scenario})
        return jsonify({"status": "ACK", "scenario": current_scenario})
    return jsonify({"scenario": current_scenario})

@app.route("/api/anchors", methods=["GET"])
def api_anchors():
    return jsonify({"anchors": get_anchor_config(), "uwb": get_position_config()})

@app.route("/api/uwb/config", methods=["GET"])
def api_uwb_config():
    """Read-only calibration assumptions used by the two-anchor solver."""
    return jsonify(get_position_config())


@app.route("/api/uwb/calibration/start", methods=["POST"])
def start_uwb_calibration_capture():
    """Start a stationary known-point raw-range capture for one worker.

    This endpoint never changes an offset.  It exposes a robust recommendation
    after BNO-gated samples have been collected, which an operator must review
    before placing replacement values in the deployment environment.
    """
    payload = request.get_json(force=True, silent=True) or {}
    worker_id = str(payload.get("worker_id", "")).strip()
    d1_m = payload.get("known_d1_m", payload.get("d1_m"))
    d2_m = payload.get("known_d2_m", payload.get("d2_m"))
    try:
        capture = RangeCalibrationCapture(
            worker_id,
            d1_m,
            d2_m,
            min_samples=payload.get("min_samples", 80),
            max_mad_m=payload.get("max_mad_m", 0.04),
        )
    except (TypeError, ValueError) as error:
        return jsonify({
            "status": "ERROR",
            "msg": str(error),
            "required": {"worker_id": "WK_102", "known_d1_m": 1.0, "known_d2_m": 1.0},
        }), 400

    uwb_calibration_captures[worker_id] = capture
    worker = get_worker(worker_id)
    worker["uwb_calibration"] = calibration_status(capture)
    return jsonify({"status": "CAPTURING", "calibration": worker["uwb_calibration"]})


@app.route("/api/uwb/calibration/<worker_id>", methods=["GET", "DELETE"])
def uwb_calibration_capture_status(worker_id):
    capture = uwb_calibration_captures.get(worker_id)
    if request.method == "DELETE":
        uwb_calibration_captures.pop(worker_id, None)
        worker = workers.get(worker_id)
        if worker:
            worker.pop("uwb_calibration", None)
        return jsonify({"status": "CLEARED", "worker_id": worker_id})
    if capture is None:
        return jsonify({"status": "ERROR", "msg": "No active capture for this worker"}), 404
    return jsonify({"status": "CAPTURING", "calibration": calibration_status(capture)})

@app.route("/api/health", methods=["GET"])
def api_health():
    return jsonify({
        "status": "OK",
        "service": "safework_backend",
        "simulated_telemetry_enabled": ALLOW_SIMULATED_TELEMETRY,
    })


@app.route("/api/exhaustion/label", methods=["POST"])
def post_exhaustion_label():
    """Ghi một nhãn Borg RPE (6-20) do người vận hành nhập cho một worker.

    Đây là GROUND TRUTH độc lập với công thức PSI: nó cho phép train lại model
    kiệt sức bằng cảm nhận thật của thợ, thay vì học lại chính công thức.
    """
    data = request.get_json(force=True, silent=True) or {}
    wid = str(data.get("worker_id", "")).strip()
    try:
        rpe = float(data.get("rpe"))
    except (TypeError, ValueError):
        return jsonify({"status": "ERROR", "msg": "rpe (6-20) la bat buoc"}), 400
    if not wid or not (6.0 <= rpe <= 20.0):
        return jsonify({"status": "ERROR", "msg": "worker_id + rpe trong [6,20]"}), 400
    note = str(data.get("note", "")).strip()
    ts = round(float(data.get("timestamp") or time.time()), 3)
    w = workers.get(wid, {})
    # Đính kèm ảnh chụp vitals lúc gán nhãn để tiện đối chiếu/khôi phục.
    _append_csv(
        EXHAUSTION_LABEL_PATH,
        ["timestamp", "worker_id", "rpe", "note", "hr_at_label", "temp_at_label"],
        [ts, wid, rpe, note,
         w.get("hr", ""), w.get("temp", "")],
    )
    return jsonify({"status": "ACK", "worker_id": wid, "rpe": rpe, "timestamp": ts})


@app.route("/api/exhaustion/labels", methods=["GET"])
def get_exhaustion_labels():
    """Đọc lại các nhãn RPE đã ghi (để review/kiểm đếm dữ liệu train)."""
    if not os.path.exists(EXHAUSTION_LABEL_PATH):
        return jsonify({"labels": [], "count": 0})
    try:
        df = pd.read_csv(EXHAUSTION_LABEL_PATH)
        rows = df.tail(500).to_dict(orient="records")
        return jsonify({"labels": rows, "count": int(len(df))})
    except Exception as exc:
        return jsonify({"labels": [], "count": 0, "error": str(exc)})

@app.route("/api/anchor_telemetry", methods=["POST"])
def receive_anchor_telemetry():
    """Endpoint dành riêng cho các trạm Anchor cố định gửi dữ liệu môi trường khu vực."""
    req_data = request.get_json(force=True)
    anchor_id = req_data.get("anchor_id", "Unknown")
    # The simulator gate must also cover zone gas: without it, fake anchor
    # readings become live environmental data on a production server.
    is_sim = bool(req_data.get("is_simulated") or req_data.get("telemetry", {}).get("is_simulated"))
    if (is_sim or anchor_id == "ANC_STAGE") and not ALLOW_SIMULATED_TELEMETRY:
        return jsonify({"status": "IGNORED", "reason": "Simulator disabled on this server"}), 200
    # Chỉ còn 2 anchor thật (xem core/position_engine.py). GAMMA_STAGE không có
    # anchor nào phụ trách nên chỉ nhận dữ liệu khí từ simulator.
    zone_map = {
        "ANC_LEFT": "ALPHA_LEFT",
        "ANC_RIGHT": "BETA_RIGHT",
        "ANC_STAGE": "GAMMA_STAGE",   # giữ lại cho simulator/tương thích ngược
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
    distances = req_data.get("distances", data.get("distances", {}))
    if isinstance(distances, dict):
        # Firmware older than the two-anchor update may send distances as
        # {"ANC_LEFT": x, "ANC_RIGHT": y} outside telemetry. Normalize it into
        # the flat keys that the current position engine consumes.
        if "d1" not in data and "ANC_LEFT" in distances:
            data["d1"] = distances["ANC_LEFT"]
        if "d2" not in data and "ANC_RIGHT" in distances:
            data["d2"] = distances["ANC_RIGHT"]
    # Priority logic: Real hardware overrides Simulator
    is_sim = data.get("is_simulated", False)
    if is_sim and not ALLOW_SIMULATED_TELEMETRY:
        return jsonify({"status": "IGNORED", "reason": "Simulator disabled on this server"}), 200

    w = get_worker(wid)

    if is_sim:
        last_real = w.get("last_real_active", 0)
        # Lock simulation for 5 seconds if real hardware is active
        if time.time() - last_real < 5.0:
            return jsonify({"status": "IGNORED", "reason": "Real hardware (WK_102) active"}), 200
    else:
        w["last_real_active"] = time.time()

    # A calibration capture consumes the untouched firmware ranges before the
    # live solver applies offsets/filters. It is BNO-gated inside the capture
    # and only produces a recommendation; normal positioning remains active.
    capture = uwb_calibration_captures.get(wid)
    if capture is not None and not is_sim and "d1" in data and "d2" in data:
        capture.add(
            data["d1"], data["d2"],
            imu_stability=data.get("imu_stability"),
            gx=data.get("gx"), gy=data.get("gy"), gz=data.get("gz"),
            linear_accel=data.get("lin_acc"),
            range_seq=data.get("range_seq"),
            range_age_ms=data.get("range_age_ms"),
            steps=data.get("steps"),
            range_epoch=data.get("range_epoch"),
            imu_age_ms=data.get("imu_age_ms"),
        )
        w["uwb_calibration"] = calibration_status(capture)
    
    # 1. Position
    if "yaw" in data:
        try:
            yaw = float(data["yaw"])
            if math.isfinite(yaw):
                w["yaw"] = yaw
        except (TypeError, ValueError):
            pass
    if "steps" in data:
        try:
            steps = int(float(data["steps"]))
            if steps >= 0:
                w["steps"] = steps
        except (TypeError, ValueError):
            pass

    # Cần CẢ d1 và d2 (mét) mới giao được 2 đường tròn. Thiếu một cái — anchor
    # bị che, NLOS — thì giữ nguyên vị trí cũ thay vì hút worker về anchor.
    if "d1" in data and "d2" in data:
        nlos_flags = data.get("nlos_flags")
        if nlos_flags is None and ("nlos_d1" in data or "nlos_d2" in data):
            nlos_flags = (bool(data.get("nlos_d1")), bool(data.get("nlos_d2")))
        fix = estimate_position(
            wid,
            data["d1"],
            data["d2"],
            w.get("yaw", 0.0),
            steps=data.get("steps", w.get("steps")),
            imu_ok=bool(data.get("imu_ok", w.get("imu_ok", False))),
            gyro_x=data.get("gx"),
            gyro_y=data.get("gy"),
            gyro_z=data.get("gz"),
            linear_accel=data.get("lin_acc"),
            stability=data.get("imu_stability"),
            yaw_accuracy=data.get("yaw_accuracy"),
            gyro_accuracy=data.get("gyro_accuracy"),
            linear_accel_x=data.get("lin_ax"),
            linear_accel_y=data.get("lin_ay"),
            yaw_accuracy_rad=data.get("yaw_accuracy_rad"),
            range_seq=data.get("range_seq"),
            range_age_ms=data.get("range_age_ms"),
            range_epoch=data.get("range_epoch"),
            imu_age_ms=data.get("imu_age_ms"),
            range_trusted=data.get("range_trusted"),
            nlos_flags=nlos_flags,
            yaw_age_ms=data.get("yaw_age_ms"),
            linear_accel_age_ms=data.get("linear_accel_age_ms"),
            imu_epoch=data.get("imu_epoch"),
            linear_accel_accuracy=data.get("linear_accel_accuracy"),
        )
        current_uwb = get_fix_status(wid)
        # The 2 m physical baseline and both *current* ranges produced this
        # coordinate. Calibration affects its accuracy label, not whether the
        # dashboard may show the actual measurement. This prevents the map
        # from remaining at / hiding the default point while a worker moves.
        # Invalid/missing pairs still take the hold-or-invalidate path below;
        # no synthetic coordinate is ever published.
        if is_publishable_uwb_fix(fix, current_uwb):
            w["uwb"] = current_uwb
            w["location_valid"] = True
            w["location_stale"] = False
            w["location_last_known"] = False
            w["location_calibrated"] = bool(current_uwb.get("calibrated"))
            w["location_degraded"] = bool(
                current_uwb.get("degraded") or current_uwb.get("geometry_mode") == "line"
            )
            w["x"], w["y"] = fix
            last_valid_uwb_fixes[wid] = {"at": time.time(), "status": dict(current_uwb)}
        else:
            hold_or_invalidate_uwb_fix(wid, w, "no_current_uwb_fix", current_uwb)
    else:
        w["x"] = data.get("x", w["x"])
        w["y"] = data.get("y", w["y"])
        hold_or_invalidate_uwb_fix(wid, w, "missing_d1_or_d2")
        
    if wid in manual_overrides:
        if "x" in manual_overrides[wid]: w["x"] = manual_overrides[wid]["x"]
        if "y" in manual_overrides[wid]: w["y"] = manual_overrides[wid]["y"]

    update_worker_zone(w)
    
    # 2. Vitals
    # Cảm biến ở hardware có thể gửi chữ "bpm" thay vì "hr"
    w["hr"] = data.get("hr", data.get("bpm", w["hr"]))
    w["temp"] = data.get("temp", data.get("tempC", w["temp"]))
    # Preserve provenance/quality fields from the ESP32. This makes a
    # MAX30205 body-temperature sample distinguishable from a MAX30102 die
    # temperature, and lets the dashboard expose cached/failed I2C reads.
    w["temp_source"] = data.get("temp_source", w.get("temp_source", "unknown"))
    w["temp_fresh"] = data.get("temp_fresh", w.get("temp_fresh", False))
    w["temp_age_ms"] = data.get("temp_age_ms", w.get("temp_age_ms", -1))
    w["ir"] = data.get("ir", w.get("ir", 0))
    w["imu_ok"] = data.get("imu_ok", w.get("imu_ok", False))
    w["imu_addr"] = data.get("imu_addr", w.get("imu_addr"))
    # Preserve BNO08x quality/motion fields so the dashboard and UWB filter
    # can make their confidence visible. Values are sensor observations, not
    # an IMU-only location estimate.
    for key in ("gx", "gy", "gz", "lin_acc", "lin_ax", "lin_ay", "lin_az",
                "imu_stability", "yaw_accuracy", "yaw_accuracy_rad", "gyro_accuracy", "imu_age_ms",
                "yaw_age_ms", "linear_accel_age_ms", "linear_accel_accuracy", "imu_epoch",
                "bno_probe_4a", "bno_probe_4b",
                # Vitals quality: SpO2 + tin cậy nhịp tim (perfusion/quality) từ MAX30102.
                "spo2", "spo2_available", "hr_quality", "hr_perfusion",
                "range_seq", "range_age_ms", "range_epoch", "range_trusted", "nlos_d1", "nlos_d2"):
        if key in data:
            w[key] = data[key]
    # Zero is not a valid substitute for an absent gas sensor. Only accept gas
    # readings from a hardware packet that explicitly declares the sensor, or
    # from the opt-in local simulator. This protects production from older
    # firmware that emitted ch4/co=0 despite having no gas module.
    gas_available = data.get("gas_available") is True or (
        is_sim and "ch4" in data and "co" in data
    )
    w["gas_available"] = gas_available
    if gas_available:
        try:
            w["ch4"] = float(data["ch4"])
            w["co"] = float(data["co"])
        except (KeyError, TypeError, ValueError):
            w["gas_available"] = False
            w["ch4"] = None
            w["co"] = None
    else:
        w["ch4"] = None
        w["co"] = None
    
    # 2.5 Fall Detection — Tin tưởng trực tiếp phần cứng
    hw_fall = data.get("fall_alert", w.get("fall_status", "SAFE"))
    
    # Chỉ bác bỏ nếu dữ liệu IMU rõ ràng là rác I2C (g > 100 hoặc = 0)
    ax = float(data.get("ax", 0.0))
    ay = float(data.get("ay", 0.0))
    az = float(data.get("az", 0.0))
    g_total = (ax**2 + ay**2 + az**2) ** 0.5
    is_garbage = (g_total > 100.0) or (g_total < 0.1 and hw_fall == "DANGER")
    
    if is_garbage:
        pass  # Giữ nguyên trạng thái cũ, không cập nhật
    elif hw_fall == "DANGER":
        w["fall_status"] = "FALL"
    else:
        w["fall_status"] = "SAFE"

    # 2.6 Exhaustion (kiệt sức) — strain sinh lý thời gian thực từ nhịp tim +
    # thân nhiệt bề mặt (+ huyết áp nếu worker có cảm biến). Model rơi về công
    # thức PSI nếu chưa nạp được .pkl, nên route không bao giờ hỏng vì việc này.
    hr_val = None
    try:
        if w["hr"] not in ("--", None, "") and float(w["hr"]) > 0:
            hr_val = float(w["hr"])
    except (TypeError, ValueError):
        hr_val = None
    temp_val = w["temp"] if isinstance(w["temp"], (int, float)) else None
    if hr_val is not None:
        try:
            ex = update_exhaustion_state(wid, {
                "hr": hr_val,
                "temp": temp_val,
                "bp_map": data.get("bp_map"),   # tuỳ chọn: None khi chưa có cảm biến BP
                "activity": data.get("activity"),
                "timestamp": time.time(),
            })
            w["exhaustion_status"] = ex["status"]
            w["exhaustion_level"] = ex["level"]
            w["exhaustion_score"] = ex["score"]
            w["exhaustion_load"] = ex["load"]
            w["exhaustion_source"] = ex["source"]
        except Exception as exc:  # không để lỗi model chặn telemetry
            hw_logger.warning(f"exhaustion update failed for {wid}: {exc}")

    if not is_sim:
        temp_disp = f"{w['temp']:.1f}" if isinstance(w['temp'], (int, float)) else w['temp']
        hw_logger.info(
            f"Node: {wid} | HR: {w['hr']} | Temp: {temp_disp} | "
            f"Fall: {w['fall_status']} | CH4: {w['ch4']} | CO: {w['co']} | "
            f"Pos: ({w['x']:.1f}, {w['y']:.1f}) | UWB: {w.get('uwb')}"
        )
        # Structured vitals stream for offline exhaustion training. Only real
        # hardware is logged; joined later with operator RPE labels.
        _append_csv(
            VITALS_HISTORY_PATH,
            ["timestamp", "worker_id", "hr", "temp", "bp_map", "activity",
             "exhaustion_score", "exhaustion_load", "exhaustion_source"],
            [round(time.time(), 3), wid,
             hr_val if hr_val is not None else "",
             temp_val if temp_val is not None else "",
             data.get("bp_map", ""), data.get("activity", ""),
             w.get("exhaustion_score", ""), w.get("exhaustion_load", ""),
             w.get("exhaustion_source", "")],
        )
        
    w["last_active"] = time.time()
    
    # 3. History
    for k in ["ax", "ay", "az", "gx", "gy", "gz"]:
        w["history_imu"][k].append(data.get(k, 0))
        if len(w["history_imu"][k]) > 20: w["history_imu"][k].pop(0)
    w["history_hr"].append(w["hr"])
    if len(w["history_hr"]) > 20: w["history_hr"].pop(0)

    # 4. Alert Logic — judge HR by the same validity rule the pulse ladder
    # uses (numeric and > 0); "0.0"/negative/garbage must not reach the
    # LOW-HR danger rule, they are no-pulse conditions.
    if hr_val is None:
        rule_status, rule_msg = "NORMAL", ""
    else:
        rule_status, rule_msg = rule_based_hr(hr_val)
    w["hr_status"] = rule_status
    w["hr_msg"] = rule_msg

    # 4.1 Loss-of-pulse escalation. The tag is still talking to us (this route
    # ran), but the wearer's pulse has not been read for too long — either the
    # strap came off or the wearer is in trouble. Never silently show "--".
    # A packet that omits hr entirely must not refresh the pulse clock off the
    # sticky previous reading.
    hr_key_present = "hr" in data or "bpm" in data
    now = time.time()
    if hr_key_present and hr_val is not None:
        w["last_pulse_at"] = now
        w["pulse_lost"] = ""
    else:
        pulse_age = now - w.get("last_pulse_at", now)
        if pulse_age >= PULSE_DANGER_SECONDS:
            w["pulse_lost"] = "DANGER"
            w["hr_status"] = "DANGER_NO_PULSE"
            w["hr_msg"] = "Pulse signal lost — check on worker immediately"
        elif pulse_age >= PULSE_WARNING_SECONDS:
            w["pulse_lost"] = "WARNING"
            if "DANGER" not in w["hr_status"]:
                w["hr_status"] = "WARNING_NO_PULSE"
            w["hr_msg"] = "No pulse reading from sensor"
    if w["gas_available"]:
        aqi = calculate_aqi(w["ch4"], w["co"])
        w["aqi"] = aqi
        if aqi <= 3.0: w["env_status"] = "DANGER"
        elif aqi <= 7.0: w["env_status"] = "WARNING"
        else: w["env_status"] = "SAFE"

        # Also update zone with worker's actual gas readings.
        if w["zone"] in zones:
            update_zone_data(w["zone"], w["ch4"], w["co"], from_worker=True)
    else:
        w["aqi"] = None
        w["env_status"] = "UNKNOWN"
    
    evaluate_alert(w)

    if wid in manual_overrides:
        if "alert" in manual_overrides[wid]:
            w["alert"] = manual_overrides[wid]["alert"]
        if "fall_status" in manual_overrides[wid]:
            w["fall_status"] = manual_overrides[wid]["fall_status"]
    
    
    socketio.emit('latest_status', {"workers": list(workers.values()), "zones": zones, "hiddenNodes": hidden_nodes_global, "customAnchors": custom_anchors})
    return jsonify({"status": "ACK"})

@app.route("/api/admin/node", methods=["POST"])
def admin_override_node():
    """Admin override: drag worker to new position or force alert/env on anchor."""
    denied = require_admin_pin()
    if denied:
        return denied
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
        if "fall_status" in data:
            w["fall_status"] = data["fall_status"]
            override["fall_status"] = data["fall_status"]
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
        update_worker_zone(w)
        w["last_active"] = time.time()
        socketio.emit('latest_status', {"workers": list(workers.values()), "zones": zones, "hiddenNodes": hidden_nodes_global, "customAnchors": custom_anchors})
        return jsonify({"status": "ACK", "worker_id": wid})

    if aid:
        # ANC_LEFT/ANC_RIGHT are the physical UWB reference pair. Their map
        # coordinates encode the surveyed, fixed 2 m baseline, so accepting a
        # drag here would make the visual anchor layout disagree with the
        # geometry solver. Environmental data for those anchors remains
        # editable below.
        if aid in {"ANC_LEFT", "ANC_RIGHT"} and any(
            key in data and data[key] != '' for key in ("x", "y")
        ):
            return jsonify({
                "status": "ERROR",
                "msg": "Physical UWB anchors are fixed; their 2 m baseline cannot be moved on the map.",
            }), 409
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
    denied = require_admin_pin()
    if denied:
        return denied
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
    denied = require_admin_pin()
    if denied:
        return denied
    data = request.get_json(force=True)
    nid = data.get("node_id")
    if nid:
        hidden_nodes_global[nid] = not hidden_nodes_global.get(nid, False)
        socketio.emit('latest_status', {"workers": list(workers.values()), "zones": zones, "hiddenNodes": hidden_nodes_global, "customAnchors": custom_anchors})
        return jsonify({"status": "ACK", "hiddenNodes": hidden_nodes_global})
    return jsonify({"status": "ERROR"}), 400

@app.route("/api/admin/simulator_config", methods=["GET"])
def admin_simulator_config():
    denied = require_admin_pin()
    if denied:
        return denied
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


@app.route("/api/personnel", methods=["POST"])
def create_personnel():
    denied = require_admin_pin()
    if denied:
        return denied
    data = request.get_json(force=True, silent=True) or {}
    pid = str(data.get('id', '')).strip()
    name = str(data.get('name', '')).strip()
    zone = str(data.get('zone', '')).strip()
    if not pid or not name:
        return jsonify({'error': 'Worker ID and Name are required'}), 400
    if Personnel.query.get(pid):
        return jsonify({'error': f'ID {pid} already exists'}), 409
    p = Personnel(id=pid, name=name, zone=zone)
    db.session.add(p)
    db.session.commit()
    return jsonify({'id': p.id, 'name': p.name, 'zone': p.zone}), 201


@app.route("/api/personnel/<pid>", methods=["PUT", "PATCH"])
def update_personnel(pid):
    denied = require_admin_pin()
    if denied:
        return denied
    p = Personnel.query.get(pid)
    if not p:
        return jsonify({'error': 'Personnel not found'}), 404
    data = request.get_json(force=True, silent=True) or {}
    if 'name' in data:
        new_name = str(data.get('name', '')).strip()
        if not new_name:
            return jsonify({'error': 'Name must not be empty'}), 400
        p.name = new_name
    if 'zone' in data:
        p.zone = str(data.get('zone', '')).strip()
    db.session.commit()
    return jsonify({'id': p.id, 'name': p.name, 'zone': p.zone})


@app.route("/api/personnel/<pid>", methods=["DELETE"])
def delete_personnel(pid):
    denied = require_admin_pin()
    if denied:
        return denied
    p = Personnel.query.get(pid)
    if not p:
        return jsonify({'error': 'Personnel not found'}), 404
    db.session.delete(p)
    db.session.commit()
    return jsonify({'status': 'deleted', 'id': pid})

def background_timeout_checker():
    while True:
        socketio.sleep(1.0)
        changed = False
        now = time.time()
        for w in workers.values():
            if now - w.get("last_active", now) > OFFLINE_TIMEOUT_SECONDS and w["alert"] != "OFFLINE":
                w["alert"] = "OFFLINE"
                # Signal loss supersedes a frozen pulse-loss escalation.
                w["pulse_lost"] = ""
                changed = True
        if changed:
            socketio.emit('latest_status', {"workers": list(workers.values()), "zones": zones, "hiddenNodes": hidden_nodes_global, "customAnchors": custom_anchors})

if __name__ == "__main__":
    socketio.start_background_task(background_timeout_checker)
    socketio.run(app, host="0.0.0.0", port=int(os.environ.get('PORT', 5000)), allow_unsafe_werkzeug=True)
