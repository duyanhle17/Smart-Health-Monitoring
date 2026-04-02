"""
Demo Simulator — Mô phỏng 4 Worker di chuyển trong không gian xây dựng
========================================================================
Chạy song song với Backend. Gửi telemetry giả lập mỗi 500ms tới /api/device_telemetry.

Usage:
    python -m backend.demo_simulator

Kịch bản:
    - WK_077: Đi từ cửa vào (y=80) → lên khán đài giữa (y=20). CRITICAL event halfway.
    - WK_048: Đi vòng quanh khu vực trái. STABLE.
    - WK_089: Đứng yên ở khu phải. STABLE.
    - WK_004: Đi dọc lối giữa. WARNING ch4 spike.
"""

import time
import math
import random
import requests
import sys

from backend.core.position_engine import distances_from_position

import os
BACKEND_URL = os.environ.get("BACKEND_URL", "http://localhost:5000")
TICK_INTERVAL = 0.5  # seconds

GLOBAL_SCENARIO = "NORMAL"

# ─── WAYPOINT DEFINITIONS ─────────────────────────────
# Mỗi waypoint = (x, y) trong logical space (0-100)
# Worker sẽ di chuyển tuần tự qua các waypoint rồi lặp lại

WORKER_PATHS = {
    "WK_077": {
        "waypoints": [
            (30, 85), (30, 70), (30, 50), (30, 30),         # Move up Pathway 1
            (33, 30), (33, 25), (33, 15),                   # Slide right across front of stage
            (40, 15), (45, 15), (55, 15),                   # Move up into center of stage
            # Quay về
            (45, 15), (40, 15), (33, 15), (33, 25), (33, 30), 
            (30, 30),
            (30, 50), (30, 70), (30, 85)
        ],
        "speed": 30,
        "base_hr": 85,
        "base_temp": 37.2,
        "scenario": "critical"
    },
    "WK_048": {
        "waypoints": [
            (18, 50), (22, 55), (22, 65), (18, 70),
            (15, 65), (15, 55), (18, 50)
        ],
        "speed": 1.0,
        "base_hr": 72,
        "base_temp": 36.5,
        "scenario": "stable"
    },
    "WK_089": {
        "waypoints": [
            (82, 50), (86, 55), (86, 65), (82, 70),
            (78, 65), (78, 55), (82, 50)
        ],
        "speed": 0.8,
        "base_hr": 78,
        "base_temp": 36.8,
        "scenario": "stable"
    },
    "WK_004": {
        "waypoints": [
            (50, 50), (55, 60), (55, 75), (50, 85),
            (45, 75), (45, 60), (50, 50)
        ],
        "speed": 1.2,
        "base_hr": 80,
        "base_temp": 36.4,
        "scenario": "gas_spike"
    }
}


# Anchor configurations (Fixed environmental sensors)
ANCHOR_NODES = {
    "ANC_STAGE": {"ch4_baseline": 0.5, "co_baseline": 6.0, "scenario": "stable"},
    "ANC_LEFT": {"ch4_baseline": 0.3, "co_baseline": 4.0, "scenario": "stable"},
    "ANC_RIGHT": {"ch4_baseline": 0.2, "co_baseline": 3.5, "scenario": "stable"}
}

class WorkerSimulator:
    def __init__(self, worker_id, config):
        self.wid = worker_id
        self.waypoints = config["waypoints"]
        self.speed = config["speed"]
        self.base_hr = config["base_hr"]
        self.base_temp = config["base_temp"]
        self.scenario = config["scenario"]
        
        self.wp_index = 0
        self.progress = 0.0  # 0.0 → 1.0 between waypoints
        self.x, self.y = self.waypoints[0]
        self.tick_count = 0
        self.ch4 = 0.5 
        self.co = 5.0 
        self.fall_alert = "SAFE"

    def _lerp(self, a, b, t):
        return a + (b - a) * t

    def tick(self):
        self.tick_count += 1
        
        # ── Move along path ──────────
        wp_from = self.waypoints[self.wp_index]
        wp_to = self.waypoints[(self.wp_index + 1) % len(self.waypoints)]
        
        dx = wp_to[0] - wp_from[0]
        dy = wp_to[1] - wp_from[1]
        seg_len = math.sqrt(dx**2 + dy**2)
        
        if seg_len > 0: self.progress += self.speed / seg_len * 0.1
        else: self.progress = 1.0

        if self.progress >= 1.0:
            self.progress = 0.0
            self.wp_index = (self.wp_index + 1) % len(self.waypoints)
            wp_from = self.waypoints[self.wp_index]
            wp_to = self.waypoints[(self.wp_index + 1) % len(self.waypoints)]

        self.x = self._lerp(wp_from[0], wp_to[0], self.progress)
        self.y = self._lerp(wp_from[1], wp_to[1], self.progress)

        # ── Vitals (HR/Temp) ─────────
        t = self.tick_count * TICK_INTERVAL
        hr = self.base_hr + 8 * math.sin(t * 0.3) + random.gauss(0, 2)
        if self.scenario == "critical" and 30 < self.tick_count % 80 < 50:
            hr = 135 + random.gauss(0, 5)

        temp = self.base_temp + 0.3 * math.sin(t * 0.1) + random.gauss(0, 0.1)
        if self.scenario == "critical" and 30 < self.tick_count % 80 < 50:
            temp = 39.2 + random.gauss(0, 0.3)

        # Gas readings — spike during critical/gas_spike scenarios
        if self.scenario == "critical" and 30 < self.tick_count % 80 < 50:
            self.ch4 = max(0.5, 3.5 + random.gauss(0, 0.5))
            self.co = max(5.0, 80.0 + random.gauss(0, 10.0))
        elif self.scenario == "gas_spike" and 20 < self.tick_count % 60 < 45:
            self.ch4 = max(0.5, 2.8 + random.gauss(0, 0.4))
            self.co = max(5.0, 65.0 + random.gauss(0, 8.0))
        else:
            self.ch4 = max(0.1, 0.4 + random.gauss(0, 0.15))
            self.co = max(1.0, 5.0 + random.gauss(0, 1.0))

        distances = distances_from_position(self.x, self.y, noise_std=0.8)
        
        # Calculate yaw to accurately reverse-engineer the position in position_engine.py
        # x_est = x_anchor + d1 * sin(yaw)  => sin(yaw) = (x - x_anchor) / d1
        # y_est = y_anchor + d1 * cos(yaw)  => cos(yaw) = (y - y_anchor) / d1
        # Therefore yaw = atan2(x - x_anchor, y - y_anchor)
        x_anchor = 50.0
        y_anchor = 17.0
        sim_yaw = math.degrees(math.atan2(self.x - x_anchor, self.y - y_anchor))

        return {
            "worker_id": self.wid,
            "telemetry": {
                "hr": round(hr, 1),
                "temp": round(temp, 1),
                "ch4": round(self.ch4, 2),
                "co": round(self.co, 1),
                "d1": distances[0], "d2": distances[1], "d3": distances[2],
                "ax": round(random.gauss(0, 0.1), 3), "ay": round(random.gauss(0, 0.1), 3), 
                "az": round(random.gauss(9.8, 0.2), 3),
                "yaw": round(sim_yaw, 1),
                "gx": 0, "gy": 0, "gz": round(sim_yaw, 1),
                "fall_alert": self.fall_alert,
                "is_simulated": True
            }
        }

def simulate_anchor(aid, config, tick_count):
    global GLOBAL_SCENARIO
    if GLOBAL_SCENARIO == "EVACUATION":
        return {
            "anchor_id": aid,
            "telemetry": {
                "ch4": round(6.5 + random.gauss(0, 0.5), 2),
                "co": round(150.0 + random.gauss(0, 10), 1)
            }
        }
    
    if GLOBAL_SCENARIO == "CAVE_IN":
        return {
            "anchor_id": aid,
            "telemetry": {
                "ch4": round(5.0 + random.gauss(0, 0.8), 2),
                "co": round(130.0 + random.gauss(0, 15), 1)
            }
        }

    # Anchor monitors ZONE environment
    ch4 = config["ch4_baseline"] + random.gauss(0, 0.1)
    # Scenario: Stage anchor has a leak spike
    if aid == "ANC_STAGE" and 40 < tick_count % 100 < 70:
        ch4 = 5.2 + random.gauss(0, 0.5)
    
    co = config["co_baseline"] + random.gauss(0, 1.0)
    if ch4 > 2.0: co = 120.5 + random.gauss(0, 15)

    return {
        "anchor_id": aid,
        "telemetry": {
            "ch4": round(ch4, 2),
            "co": round(co, 1)
        }
    }

def main():
    global GLOBAL_SCENARIO
    print("  SAFE WORK — Simulator V2 (Separated Worker/Anchor Sensors)")
    sims = {wid: WorkerSimulator(wid, config) for wid, config in WORKER_PATHS.items()}
    tick = 0
    while True:
        try:
            # 1. Fetch current scenario & config
            if tick % 4 == 0:
                try:
                    res = requests.get(f"{BACKEND_URL}/api/scenario", timeout=1)
                    if res.status_code == 200:
                        GLOBAL_SCENARIO = res.json().get("scenario", "NORMAL")
                    
                    # Fetch speed admin config
                    cfg_res = requests.get(f"{BACKEND_URL}/api/admin/simulator_config", timeout=1)
                    if cfg_res.status_code == 200:
                        spd_cfg = cfg_res.json().get("speed", {})
                        for w_id, speed_val in spd_cfg.items():
                            if w_id in sims and speed_val > 0:
                                sims[w_id].speed = speed_val
                except:
                    pass

            # 2. Send Anchor Data (every 2 seconds)
            if tick % 4 == 0:
                for aid, config in ANCHOR_NODES.items():
                    payload = simulate_anchor(aid, config, tick)
                    requests.post(f"{BACKEND_URL}/api/anchor_telemetry", json=payload, timeout=2)

            # 3. Send Worker Data (every 500ms) (COMMENTED OUT AS REQUESTED)
            # for wid, sim in sims.items():
            #     if GLOBAL_SCENARIO == "CAVE_IN" and wid == "WK_004":
            #         continue  # Stop sending data for WK_004 to simulate cave-in signal loss
            #
            #     payload = sim.tick()
            #     requests.post(f"{BACKEND_URL}/api/device_telemetry", json=payload, timeout=2)

            tick += 1
            time.sleep(TICK_INTERVAL)
        except KeyboardInterrupt: break
        except Exception as e: print(f"Error: {e}")

if __name__ == "__main__":
    main()
