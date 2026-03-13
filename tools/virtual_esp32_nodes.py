import time
import random
import requests
import threading

SERVER_URL = "http://127.0.0.1:5000"
WORKERS = ["W1", "W2", "W3"]

state = {
    "W1": {"x": 15, "y": 50, "dir": "right", "hr": 75, "is_falling": False, "fall_timer": 0},
    "W2": {"x": 50, "y": 20, "dir": "up",    "hr": 80, "is_falling": False, "fall_timer": 0},
    "W3": {"x": 80, "y": 50, "dir": "left",  "hr": 72, "is_falling": False, "fall_timer": 0}
}

def generate_imu(is_falling):
    if is_falling:
        return {
            "ax": random.uniform(-3.5, 3.5), "ay": random.uniform(-3.5, 3.5), "az": random.uniform(-3.5, 3.5),
            "gx": random.uniform(-200, 200), "gy": random.uniform(-200, 200), "gz": random.uniform(-200, 200)
        }
    else:
        return {
            "ax": random.uniform(-0.2, 0.2), "ay": random.uniform(0.8, 1.2), "az": random.uniform(-0.2, 0.2),
            "gx": random.uniform(-10, 10), "gy": random.uniform(-10, 10), "gz": random.uniform(-10, 10)
        }

def simulate_worker(wid):
    while True:
        w = state[wid]
        step = random.uniform(0.5, 1.5)
        
        if w["dir"] == "right": w["x"] += step
        elif w["dir"] == "left": w["x"] -= step
        elif w["dir"] == "up": w["y"] += step
        elif w["dir"] == "down": w["y"] -= step

        if w["dir"] in ["left", "right"]:
            w["y"] = 50
            if w["x"] >= 90: w["dir"] = "left"
            if w["x"] <= 10: w["dir"] = "right"
            if 48 < w["x"] < 52 and random.random() < 0.15:
                w["dir"] = random.choice(["up", "down"])
                w["x"] = 50
        elif w["dir"] in ["up", "down"]:
            w["x"] = 50
            if w["y"] <= 10: w["dir"] = "up"
            if w["y"] >= 50: 
                w["y"] = 50
                w["dir"] = random.choice(["left", "right"])

        fall_alert = "SAFE"
        if not w["is_falling"] and random.random() < 0.01:
            w["is_falling"] = True
            w["fall_timer"] = 5 
        
        if w["is_falling"]:
            fall_alert = "FALL"
            w["fall_timer"] -= 1
            if w["fall_timer"] <= 0: w["is_falling"] = False

        imu = generate_imu(w["is_falling"])
        gas_level = random.uniform(0.5, 5.0)
        if w["x"] > 75: gas_level += random.uniform(30.0, 70.0)

        w["hr"] += random.randint(-2, 2)
        if w["hr"] < 60: w["hr"] = 60
        if w["hr"] > 110: w["hr"] = 110
        if w["is_falling"] or gas_level > 30: w["hr"] = random.randint(120, 160)

        payload = {
            "worker_id": wid,
            "telemetry": {
                "x": round(w["x"], 2), "y": round(w["y"], 2),
                "hr": round(w["hr"], 1), "gas": round(gas_level, 2),
                "ax": round(imu["ax"], 2), "ay": round(imu["ay"], 2), "az": round(imu["az"], 2),
                "gx": round(imu["gx"], 2), "gy": round(imu["gy"], 2), "gz": round(imu["gz"], 2),
                "fall_alert": fall_alert
            }
        }
        try:
            requests.post(f"{SERVER_URL}/api/device_telemetry", json=payload, timeout=2)
        except Exception:
            pass

        time.sleep(1)

print("Starting Virtual Workers (Anti-Fly-Out mode)...")
for wid in WORKERS:
    t = threading.Thread(target=simulate_worker, args=(wid,))
    t.daemon = True
    t.start()

try:
    while True: time.sleep(1)
except KeyboardInterrupt:
    pass
