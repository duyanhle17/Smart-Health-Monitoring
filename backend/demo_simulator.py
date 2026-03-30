"""
Demo Simulator — Mô phỏng 4 Worker di chuyển trong không gian xây dựng
========================================================================
Chạy song song với Backend. Gửi telemetry giả lập mỗi 500ms tới /api/device_telemetry.

Usage:
    python -m backend.demo_simulator

Kịch bản:
    - WK_102: Đi từ cửa vào (y=80) → lên khán đài giữa (y=20). CRITICAL event halfway.
    - WK_048: Đi vòng quanh khu vực trái. STABLE.
    - WK_089: Đứng yên ở khu phải. STABLE.
    - WK_004: Đi dọc lối giữa. WARNING gas spike.
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

# ─── WAYPOINT DEFINITIONS ─────────────────────────────
# Mỗi waypoint = (x, y) trong logical space (0-100)
# Worker sẽ di chuyển tuần tự qua các waypoint rồi lặp lại

WORKER_PATHS = {
    "WK_102": {
        "waypoints": [
            (50, 80), (50, 70), (50, 60), (50, 50), 
            (50, 40), (50, 30), (50, 25), (50, 20),
            # Quay về
            (50, 25), (50, 30), (50, 40), (50, 50),
            (50, 60), (50, 70), (50, 80)
        ],
        "speed": 1.5,  # units per tick
        "base_hr": 85,
        "base_temp": 37.2,
        "scenario": "critical"  # Will trigger critical HR halfway
    },
    "WK_048": {
        "waypoints": [
            (15, 45), (20, 50), (25, 55), (25, 65),
            (20, 70), (15, 65), (15, 55), (15, 45)
        ],
        "speed": 1.0,
        "base_hr": 72,
        "base_temp": 36.5,
        "scenario": "stable"
    },
    "WK_089": {
        "waypoints": [
            (85, 50), (80, 55), (85, 60), (80, 65),
            (85, 60), (80, 55), (85, 50)
        ],
        "speed": 0.8,
        "base_hr": 78,
        "base_temp": 36.8,
        "scenario": "stable"
    },
    "WK_004": {
        "waypoints": [
            (50, 80), (48, 70), (52, 60), (50, 50),
            (52, 60), (48, 70), (50, 80)
        ],
        "speed": 1.2,
        "base_hr": 80,
        "base_temp": 36.4,
        "scenario": "gas_spike"  # Will trigger gas spike periodically
    }
}


# Anchor configurations (Fixed environmental sensors)
ANCHOR_NODES = {
    "ANC_STAGE": {"gas_baseline": 2.5, "scenario": "stable"},
    "ANC_LEFT": {"gas_baseline": 1.2, "scenario": "stable"},
    "ANC_RIGHT": {"gas_baseline": 0.8, "scenario": "stable"}
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
        self.gas = 2.0  # Local pockets
        self.oxygen = 20.9 
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

        # Worker still carries small gas pocket sensor for instant personal alerts
        self.gas = max(0.5, 2.0 + random.gauss(0, 0.5))
        self.oxygen = 20.9 + random.gauss(0, 0.1)

        distances = distances_from_position(self.x, self.y, noise_std=0.8)

        return {
            "worker_id": self.wid,
            "telemetry": {
                "hr": round(hr, 1),
                "temp": round(temp, 1),
                "gas": round(self.gas, 2),
                "o2": round(self.oxygen, 1),
                "d1": distances[0], "d2": distances[1], "d3": distances[2],
                "ax": round(random.gauss(0, 0.1), 3), "ay": round(random.gauss(0, 0.1), 3), "az": round(random.gauss(9.8, 0.2), 3),
                "gx": 0, "gy": 0, "gz": 0,
                "fall_alert": self.fall_alert
            }
        }

def simulate_anchor(aid, config, tick_count):
    # Anchor monitors ZONE environment
    gas = config["gas_baseline"] + random.gauss(0, 0.2)
    # Scenario: Stage anchor has a leak spike
    if aid == "ANC_STAGE" and 40 < tick_count % 100 < 70:
        gas = 45 + random.gauss(0, 5)
    
    o2 = 20.9 + random.gauss(0, 0.05)
    if gas > 20: o2 = 18.5 + random.gauss(0, 0.3)

    return {
        "anchor_id": aid,
        "telemetry": {
            "gas": round(gas, 2),
            "o2": round(o2, 1)
        }
    }

def main():
    print("  SAFE WORK — Simulator V2 (Separated Worker/Anchor Sensors)")
    sims = {wid: WorkerSimulator(wid, config) for wid, config in WORKER_PATHS.items()}
    tick = 0
    while True:
        try:
            # 1. Send Anchor Data (every 2 seconds)
            if tick % 4 == 0:
                for aid, config in ANCHOR_NODES.items():
                    payload = simulate_anchor(aid, config, tick)
                    requests.post(f"{BACKEND_URL}/api/anchor_telemetry", json=payload, timeout=2)

            # 2. Send Worker Data (every 500ms)
            for wid, sim in sims.items():
                payload = sim.tick()
                requests.post(f"{BACKEND_URL}/api/device_telemetry", json=payload, timeout=2)

            tick += 1
            time.sleep(TICK_INTERVAL)
        except KeyboardInterrupt: break
        except Exception as e: print(f"Error: {e}")

if __name__ == "__main__":
    main()
