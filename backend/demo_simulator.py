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

BACKEND_URL = "http://localhost:5000"
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
        self.gas = 0.0
        self.fall_alert = "SAFE"

    def _lerp(self, a, b, t):
        return a + (b - a) * t

    def tick(self):
        self.tick_count += 1
        
        # ── Move along path ──────────────────────────────
        wp_from = self.waypoints[self.wp_index]
        wp_to = self.waypoints[(self.wp_index + 1) % len(self.waypoints)]
        
        dx = wp_to[0] - wp_from[0]
        dy = wp_to[1] - wp_from[1]
        seg_len = math.sqrt(dx**2 + dy**2)
        
        if seg_len > 0:
            self.progress += self.speed / seg_len * 0.1
        else:
            self.progress = 1.0

        if self.progress >= 1.0:
            self.progress = 0.0
            self.wp_index = (self.wp_index + 1) % len(self.waypoints)
            wp_from = self.waypoints[self.wp_index]
            wp_to = self.waypoints[(self.wp_index + 1) % len(self.waypoints)]

        self.x = self._lerp(wp_from[0], wp_to[0], self.progress)
        self.y = self._lerp(wp_from[1], wp_to[1], self.progress)

        # ── Heart Rate (sinusoidal + noise) ──────────────
        t = self.tick_count * TICK_INTERVAL
        hr = self.base_hr + 8 * math.sin(t * 0.3) + random.gauss(0, 2)
        
        if self.scenario == "critical" and 30 < self.tick_count % 80 < 50:
            hr = 135 + random.gauss(0, 5)  # Spike to critical

        # ── Temperature ──────────────────────────────────
        temp = self.base_temp + 0.3 * math.sin(t * 0.1) + random.gauss(0, 0.1)
        if self.scenario == "critical" and 30 < self.tick_count % 80 < 50:
            temp = 39.2 + random.gauss(0, 0.3)

        # ── Gas ──────────────────────────────────────────
        self.gas = max(0, 2.0 + random.gauss(0, 1.5))
        if self.scenario == "gas_spike" and 40 < self.tick_count % 60 < 55:
            self.gas = 35 + random.gauss(0, 5)  # WARNING level spike

        # ── Fall ─────────────────────────────────────────
        self.fall_alert = "SAFE"

        # ── Compute distances to anchors (with noise) ────
        distances = distances_from_position(self.x, self.y, noise_std=0.8)

        # ── Assemble telemetry ───────────────────────────
        return {
            "worker_id": self.wid,
            "telemetry": {
                "hr": round(hr, 1),
                "temp": round(temp, 1),
                "gas": round(self.gas, 2),
                "d1": distances[0],  # Distance to ANC_STAGE
                "d2": distances[1],  # Distance to ANC_LEFT
                "d3": distances[2],  # Distance to ANC_RIGHT
                "ax": round(random.gauss(0, 0.15), 3),
                "ay": round(random.gauss(0, 0.15), 3),
                "az": round(random.gauss(9.8, 0.3), 3),
                "gx": round(random.gauss(0, 2), 3),
                "gy": round(random.gauss(0, 2), 3),
                "gz": round(random.gauss(0, 2), 3),
                "fall_alert": self.fall_alert
            }
        }


def main():
    print("=" * 60)
    print("  SAFE WORK — Demo Simulator")
    print(f"  Target: {BACKEND_URL}")
    print(f"  Workers: {list(WORKER_PATHS.keys())}")
    print(f"  Tick interval: {TICK_INTERVAL}s")
    print("=" * 60)
    print()

    # Initialize simulators
    sims = {}
    for wid, config in WORKER_PATHS.items():
        sims[wid] = WorkerSimulator(wid, config)
        print(f"  [INIT] {wid} @ ({config['waypoints'][0][0]}, {config['waypoints'][0][1]}) — {config['scenario']}")

    print()
    print("  Sending telemetry... (Ctrl+C to stop)")
    print("-" * 60)

    tick = 0
    while True:
        try:
            for wid, sim in sims.items():
                payload = sim.tick()
                
                try:
                    resp = requests.post(
                        f"{BACKEND_URL}/api/device_telemetry",
                        json=payload,
                        timeout=2
                    )
                    status = resp.json().get("status", "?")
                except requests.exceptions.ConnectionError:
                    status = "OFFLINE"
                except Exception as e:
                    status = f"ERR: {e}"

                if tick % 10 == 0:  # Print every 5 seconds
                    t = payload["telemetry"]
                    print(f"  [{wid}] pos=({sim.x:.1f}, {sim.y:.1f}) hr={t['hr']} temp={t['temp']}° gas={t['gas']} → {status}")

            tick += 1
            time.sleep(TICK_INTERVAL)

        except KeyboardInterrupt:
            print("\n\n  Simulator stopped.")
            break


if __name__ == "__main__":
    main()
