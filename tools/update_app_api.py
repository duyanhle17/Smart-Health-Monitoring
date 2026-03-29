import re

with open("app.py", "r", encoding="utf-8") as f:
    app_code = f.read()

new_api_code = """
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

@app.route("/latest_status", methods=["GET"])"""

# Replace GET old point insert
app_code = re.sub(r'@app\.route\("/latest_status", methods=\["GET"\]\)', new_api_code.strip(), app_code)

with open("app.py", "w", encoding="utf-8") as f:
    f.write(app_code)

print("Đã update Backend thành công!")
