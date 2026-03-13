import codecs

app_py_code = """import os
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
"""

index_html_code = """<!DOCTYPE html>
<html lang="vi">
<head>
    <meta charset="UTF-8">
    <title>Giám sát Hầm Lò Đa Tác Vụ</title>
    <script src="https://cdn.plot.ly/plotly-2.27.0.min.js"></script>
    <style>
        :root {
            --bg-color: #121212;
            --panel-bg: #1e1e1e;
            --text-color: #f1f1f1;
            --color-safe: #00e676;
            --color-warn: #ff9100;
            --color-danger: #ff1744;
            --color-cyan: #00e5ff;
        }

        body {
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            margin: 0; padding: 0;
            background-color: var(--bg-color);
            color: var(--text-color);
            height: 100vh;
            display: flex;
            flex-direction: column;
        }

        .header {
            background-color: #0d0d0d;
            padding: 15px 30px;
            display: flex;
            justify-content: space-between;
            align-items: center;
            border-bottom: 2px solid #2c2c2c;
        }
        
        .header h1 { margin: 0; font-size: 24px; color: #fff; text-shadow: 0 0 10px #00e5ff; }

        .dashboard {
            display: flex;
            flex: 1;
            overflow: hidden;
        }

        /* LEFT PANEL - WORKER LIST */
        .sidebar {
            width: 420px;
            background-color: var(--panel-bg);
            padding: 20px;
            overflow-y: auto;
            border-right: 2px solid #2c2c2c;
        }

        .worker-card {
            background: #2a2a2a;
            border-radius: 12px;
            padding: 15px;
            margin-bottom: 15px;
            border-left: 6px solid var(--color-safe);
            transition: all 0.3s;
            box-shadow: 0 4px 10px rgba(0,0,0,0.5);
        }

        .worker-card.danger { border-left-color: var(--color-danger); animation: blink 1s infinite alternate; }
        .worker-card.warning { border-left-color: var(--color-warn); }

        .worker-header {
            display: flex; justify-content: space-between; align-items: center;
            font-weight: bold; font-size: 18px; margin-bottom: 12px; border-bottom: 1px solid #444; padding-bottom: 5px;
        }
        
        .worker-status-badge {
            font-size: 13px; padding: 4px 10px; border-radius: 12px; background: var(--color-safe); color: #000;
        }

        .worker-card.danger .worker-status-badge { background: var(--color-danger); color: #fff; }
        .worker-card.warning .worker-status-badge { background: var(--color-warn); color: #000; }

        .stat-row { display: flex; justify-content: space-between; align-items: center; margin: 10px 0; font-size: 15px; }
        .stat-val { font-weight: bold; font-size: 16px; display: inline-block; min-width: 80px; text-align: right; }
        .stat-val.safe { color: var(--color-safe); }
        .stat-val.warn { color: var(--color-warn); }
        .stat-val.err { color: var(--color-danger); }

        /* RIGHT PANEL - MAP */
        .map-wrapper {
            flex: 1;
            padding: 20px;
            display: flex;
            flex-direction: column;
            position: relative;
        }
        
        .map-title {
            margin-top: 0; margin-bottom: 15px; font-size: 20px;
            display: flex; justify-content: space-between; align-items: center;
        }

        #map-container {
            flex: 1;
            background: #1e1e1e;
            border-radius: 12px;
            box-shadow: inset 0 0 30px rgba(0,0,0,0.8);
            border: 1px solid #333;
        }

        @keyframes blink {
            from { box-shadow: 0 0 10px rgba(255, 23, 68, 0.1); }
            to { box-shadow: 0 0 20px rgba(255, 23, 68, 0.6); }
        }

        .legend-badge {
            display: inline-block; width: 14px; height: 14px; border-radius: 50%; margin-right: 5px; vertical-align: middle;
        }
        .legend-item { display: inline-flex; align-items: center; margin-left: 15px; font-size: 14px; }
    </style>
</head>
<body>

    <div class="header">
        <h1>⛏️ Hệ thống Giám sát Thông minh (Đa tác vụ)</h1>
        <div>
            <span class="legend-item"><span class="legend-badge" style="background:var(--color-safe)"></span> An toàn</span>
            <span class="legend-item"><span class="legend-badge" style="background:var(--color-warn)"></span> Nhịp tim cao</span>
            <span class="legend-item"><span class="legend-badge" style="background:var(--color-danger)"></span> Ngã/Nguy kịch</span>
            <span class="legend-item"><span class="legend-badge" style="background:var(--color-cyan)"></span> Rò rỉ khí độc</span>
        </div>
    </div>

    <div class="dashboard">
        <!-- DANH SÁCH CÔNG NHÂN -->
        <div class="sidebar">
            <h3 style="margin-top: 0; border-bottom: 2px solid #333; padding-bottom: 10px;">📋 Trạng thái Đội ngũ</h3>
            <div id="worker-list">
                <p style="font-size: 14px; color:#aaa; text-align:center;">Đang chờ kết nối...</p>
            </div>
        </div>

        <!-- BẢN ĐỒ HEATMAP -->
        <div class="map-wrapper">
            <div class="map-title">
                <span>📍 Định vị thời gian thực</span>
                <span id="env-alert" style="color:var(--color-cyan); font-weight:bold; font-size: 24px;"></span>
            </div>
            <div id="map-container"></div>
        </div>
    </div>

    <script>
        const layout = {
            xaxis: { title: 'Trục X (m)', range: [0, 100], gridcolor: '#2a2a2a', zerolinecolor: '#2a2a2a' },
            yaxis: { title: 'Trục Y (m)', range: [0, 100], gridcolor: '#2a2a2a', zerolinecolor: '#2a2a2a' },
            plot_bgcolor: '#121212', paper_bgcolor: '#1e1e1e',
            font: { color: '#ecf0f1' },
            margin: { t: 20, b: 40, l: 40, r: 20 },
            showlegend: false,
            shapes: [
                // Đường viền hầm lò (T-shape) trực quan
                { type: 'rect', x0: 10, x1: 90, y0: 45, y1: 55, line: { color: '#444', width: 2 }, fillcolor: '#242424' }, // Hầm ngang
                { type: 'rect', x0: 45, x1: 55, y0: 10, y1: 45, line: { color: '#444', width: 2 }, fillcolor: '#242424' }  // Hầm dọc
            ],
            annotations: [
                { x: 80, y: 55, text: 'Khu vực khai thác (Gas risk)', showarrow: false, font: {color: '#888', size: 12} },
                { x: 50, y: 10, text: 'Lối ra', showarrow: false, font: {color: '#888', size: 12} }
            ]
        };

        // Trace 0: Lịch sử (vết đi mờ mờ)
        const traceHistory = { x: [], y: [], mode: 'markers', marker: { size: 4, color: '#ecf0f1', opacity: 0.1 }, hoverinfo: 'none' };
        
        // Trace 1: Điểm nguy hiểm (Ngã / Gas cao)
        const traceDanger = { x: [], y: [], mode: 'markers', marker: { size: 12, color: '#ff1744', symbol: 'x' }, name: 'Sự cố' };

        // Trace 2: Vị trí hiện tại các Worker
        const traceWorkers = { 
            x: [], y: [], text: [], mode: 'markers+text', textposition: 'top center',
            marker: { size: 20, color: [], symbol: 'circle', line: {width: 2, color: 'white'} },
            textfont: { color: '#fff', size: 14, weight: 'bold' }
        };

        Plotly.newPlot('map-container', [traceHistory, traceDanger, traceWorkers], layout, {responsive: true});

        async function fetchStatus() {
            try {
                const res = await fetch("/latest_status");
                if (!res.ok) return;
                const data = await res.json();
                
                const workerListDiv = document.getElementById("worker-list");
                workerListDiv.innerHTML = ''; // Clear cũ

                let wx = []; let wy = []; let wtxt = []; let wcolors = [];
                let hasGasEmergency = false;

                data.workers.sort((a,b) => a.worker_id.localeCompare(b.worker_id)).forEach(w => {
                    // Update Map Arrays
                    wx.push(w.x); wy.push(w.y); wtxt.push(w.worker_id);
                    
                    let cardClass = ""; let badgeText = "Bình thường";
                    let hrColor = "safe"; let gasColor = "safe"; let fallColor = "safe";
                    let markerColor = "var(--color-safe)"; // Green

                    if (w.alert === "DANGER") {
                        cardClass = "danger"; badgeText = "NGUY HIỂM"; markerColor = "var(--color-danger)";
                    } else if (w.alert === "WARNING") {
                        cardClass = "warning"; badgeText = "CẢNH BÁO"; markerColor = "var(--color-warn)";
                    }

                    if (w.hr_status.includes("DANGER")) hrColor = "err";
                    else if (w.hr_status.includes("WARNING")) hrColor = "warn";

                    if (w.gas_status === "DANGER") { gasColor = "err"; markerColor = "var(--color-cyan)"; hasGasEmergency = true; badgeText = "KHÍ ĐỘC!"; cardClass="danger"; } // Gas ưu tiên hiển thị màu xanh cyan chớp
                    else if (w.gas_status === "WARNING") gasColor = "warn";

                    if (w.fall_status === "FALL") { fallColor = "err"; markerColor = "var(--color-danger)"; cardClass = "danger"; badgeText = "PHÁT HIỆN NGÃ!"; }

                    wcolors.push(markerColor);

                    // Render Card
                    const card = document.createElement("div");
                    card.className = `worker-card ${cardClass}`;
                    card.innerHTML = `
                        <div class="worker-header">
                            <span>👷‍♂️ Công nhân ${w.worker_id}</span>
                            <span class="worker-status-badge">${badgeText}</span>
                        </div>
                        <div class="stat-row">
                            <span>❤️ Nhịp tim:</span>
                            <span class="stat-val ${hrColor}">${w.hr} bpm</span>
                        </div>
                        <div class="stat-row">
                            <span>☁️ Khí CH4/CO:</span>
                            <span class="stat-val ${gasColor}">${w.gas} ppm</span>
                        </div>
                        <div class="stat-row">
                            <span>🏃 Gia tốc (Ngã):</span>
                            <span class="stat-val ${fallColor}">${w.fall_status === 'FALL' ? 'Đã ngã!' : 'Ổn định'}</span>
                        </div>
                        <div class="stat-row" style="font-size:12px; color:#888; border-top: 1px solid #333; padding-top: 8px;">
                            <span>Định vị ngầm: (X: ${w.x.toFixed(1)}, Y: ${w.y.toFixed(1)})</span>
                        </div>
                    `;
                    workerListDiv.appendChild(card);
                });

                const alertEl = document.getElementById('env-alert');
                if(hasGasEmergency) {
                    alertEl.textContent = "🚨 PHÁT HIỆN RÒ RỈ KHÍ ĐỘC TẠI HẦM!";
                    alertEl.style.animation = "blink 1s infinite";
                } else {
                    alertEl.textContent = "";
                    alertEl.style.animation = "none";
                }

                Plotly.update('map-container', {
                    x: [wx], y: [wy], text: [wtxt], 'marker.color': [wcolors]
                }, {}, [2]); 

            } catch (e) { console.error("API error:", e); }
        }

        async function fetchHeatmap() {
            try {
                const res = await fetch("/api/heatmap");
                const data = await res.json();
                
                if (data.length > 0) {
                    let histX = []; let histY = [];
                    let dangX = []; let dangY = [];

                    data.forEach(p => {
                        histX.push(p.x); histY.push(p.y);
                        if (p.type === "DANGER") { dangX.push(p.x); dangY.push(p.y); }
                    });

                    Plotly.update('map-container', {
                        x: [histX, dangX],
                        y: [histY, dangY]
                    }, {}, [0, 1]); 
                }
            } catch (e) {}
        }

        setInterval(fetchStatus, 1000);
        setInterval(fetchHeatmap, 3000);
        fetchStatus(); fetchHeatmap();
    </script>
</body>
</html>
"""

sim_py_code = """import requests
import time
import random

SERVER_URL = "http://127.0.0.1:5000"

# Kịch bản 3 công nhân
workers = {
    "W1": {"x": 10.0, "y": 50.0, "base_hr": 75, "direction": 1, "path": "horizontal"},
    "W2": {"x": 50.0, "y": 10.0, "base_hr": 80, "direction": 1, "path": "vertical"},
    "W3": {"x": 48.0, "y": 48.0, "base_hr": 70, "direction": 0, "path": "stationary"}
}

def simulate_data():
    print("🚀 Bắt đầu giả lập hệ thống Mỏ hầm lò nâng cao...")
    print("- 3 Công nhân (W1, W2, W3)")
    print("- Bao gồm cảm biến HR, Fall và Toxic Gas (CH4/CO)")
    
    tick = 0
    gas_leak_active = False

    while True:
        tick += 1
        
        # Mô phỏng tình huống khẩn cấp: Rò rỉ khí độc ở nhánh phải (X > 75)
        # Bắt đầu rò rỉ sau mỗi 25-30 giây, kéo dài 10 giây
        if tick % 40 == 0:
            gas_leak_active = True
            print("🚨 CẢNH BÁO MÔ PHỎNG: RÒ RỈ KHÍ ĐỘC (Mức độ Cao) tại khu vực X > 75!")
        elif tick % 40 == 15:
            gas_leak_active = False
            print("✅ HỆ THỐNG: Quạt thông gió đã xử lý xong khí độc.")

        for wid, w in workers.items():
            # ==========================
            # 1. MOVEMENT LOGIC (Di chuyển)
            # ==========================
            if w["path"] == "horizontal":
                w["x"] += w["direction"] * 1.8
                if w["x"] > 88: w["direction"] = -1
                if w["x"] < 12: w["direction"] = 1
                w["y"] = 50 + random.uniform(-1.5, 1.5) # Bước đi loạng choạng
                
            elif w["path"] == "vertical":
                w["y"] += w["direction"] * 1.8
                if w["y"] > 43: w["direction"] = -1
                if w["y"] < 12: w["direction"] = 1
                w["x"] = 50 + random.uniform(-1.5, 1.5)
                
            elif w["path"] == "stationary": # Đứng sửa máy tại ngã 3
                w["x"] += random.uniform(-0.5, 0.5)
                w["y"] += random.uniform(-0.5, 0.5)
                w["x"] = max(45, min(55, w["x"]))
                w["y"] = max(45, min(55, w["y"]))

            requests.post(f"{SERVER_URL}/location", json={"worker_id": wid, "x": w["x"], "y": w["y"]})

            # ==========================
            # 2. TOXIC GAS SENSOR LOGIC (Cảm biến Khí độc)
            # ==========================
            gas = random.uniform(2, 6)  # Khí nền an toàn
            
            # Nếu đang có rò rỉ ở cánh phải mà công nhân đi vào đó
            is_in_gas_zone = gas_leak_active and w["x"] > 70
            
            if is_in_gas_zone:
                gas = random.uniform(55, 95) # Vượt ngưỡng 50 ppm -> Danger
                
            requests.post(f"{SERVER_URL}/gas", json={"worker_id": wid, "gas": gas})

            # ==========================
            # 3. HEART RATE LOGIC (Cảm biến nhịp tim)
            # ==========================
            hr = w["base_hr"] + random.randint(-5, 5)
            
            # Nếu hít phải khí độc, nhịp tim sẽ tăng mạnh
            if is_in_gas_zone:
                hr = random.randint(120, 150)
            # Thi thoảng tự tăng do mệt mỏi
            elif random.random() < 0.05:
                hr = random.randint(110, 130)
                
            requests.post(f"{SERVER_URL}/hr", json={"worker_id": wid, "hr": hr})

            # ==========================
            # 4. FALL DETECTION LOGIC (Cảm biến ngã)
            # ==========================
            status = "SAFE"
            
            # Nếu hít khí độc lâu -> Ngã ngất xỉu (Tỷ lệ 15% mỗi giây khi ở trong vùng khí độc)
            if is_in_gas_zone and random.random() < 0.15:
                status = "FALL"
                print(f"⚠️ {wid} đã ngất xỉu do Khí Độc tại X:{w['x']:.1f}, Y:{w['y']:.1f} !!!")
                # Không cho di chuyển nữa nếu bị ngã
                w["x"] -= w["direction"] * 1.8 
                
            # Tai nạn ngã thông thường (Công nhân W2 hay vấp)
            elif wid == "W2" and random.random() < 0.02:
                status = "FALL"
                print(f"⚠️ {wid} VẤP NGÃ TAI NẠN tại X:{w['x']:.1f}, Y:{w['y']:.1f} !")
                # Không di chuyển
                w["y"] -= w["direction"] * 1.8

            requests.post(f"{SERVER_URL}/fall", json={"worker_id": wid, "status": status})

        time.sleep(1.0) # Tick 1 giây

if __name__ == "__main__":
    simulate_data()
"""

with codecs.open("app.py", "w", "utf-8") as f: f.write(app_py_code)
with codecs.open("templates/index.html", "w", "utf-8") as f: f.write(index_html_code)
with codecs.open("tools/simulate_mine_env.py", "w", "utf-8") as f: f.write(sim_py_code)

print("Files successfully upgraded.")
