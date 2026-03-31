"""
Kịch bản demo Giám khảo: Rò rỉ khí độc & AI Tìm đường sơ tán
============================================================
Công cụ này đóng vai trò như một hệ thống IoT dưới hầm mỏ, liên tục
bắn từng frame (cột mốc thời gian) dữ liệu khí lên Server (Backend).

Kịch bản 3 giai đoạn để Giám khảo xem (chạy trong khoảng 1-2 phút):
  - Phút 0-20: Hầm mỏ bình thường, các Zone có nồng độ khí thấp. AI không báo động. Path đi đường ngắn nhất.
  - Phút 21-40: Một vụ nổ/rò rỉ ống dẫn Methane tại Zone 3. Chỉ số tăng vọt. AI lập tức dự báo khu vực Zone 2 lân cận sẽ nhiễm độc sau 10 phút do gió.
  - Phút 41-60: Hệ thống Routing tự bẻ đường (khóa Zone 3, Zone 2) và điều hướng nhân viên từ Zone 4 thoát ra Exit 2 (Zone 6) thay vì đi qua Zone 2 để ra Exit 1.
"""

import time
import requests
import json
import argparse

# Dữ liệu giả lập theo đúng kịch bản tuyến tính (Hardcoded để demo hoàn hảo 100%)
# Mô hình topology đang dùng: Z1 - Z2 - Z3 - Z4 - Z6
#                                 | 
#                                 Z5 - Z6
# Lối thoát hiểm: Z1 và Z6
SCENARIO_TICKS = []

# Phase 1: Bình thường (Tick 1 -> 5)
for i in range(1, 6):
    SCENARIO_TICKS.append({
        "tick_id": i,
        "zones": [
            {"zone_id": "Z1", "methane_ppm": 0.5, "co_ppm": 2.0, "ventilation": 0.8},
            {"zone_id": "Z2", "methane_ppm": 0.6, "co_ppm": 2.1, "ventilation": 0.8},
            {"zone_id": "Z3", "methane_ppm": 0.4, "co_ppm": 1.9, "ventilation": 0.8},
            {"zone_id": "Z4", "methane_ppm": 0.5, "co_ppm": 2.2, "ventilation": 0.8},
            {"zone_id": "Z5", "methane_ppm": 0.7, "co_ppm": 2.5, "ventilation": 0.8},
            {"zone_id": "Z6", "methane_ppm": 0.4, "co_ppm": 1.8, "ventilation": 0.8},
        ]
    })

# Phase 2: Rò rỉ tại Z3 bắt đầu (Tick 6 -> 10)
for i in range(6, 11):
    SCENARIO_TICKS.append({
        "tick_id": i,
        "zones": [
            {"zone_id": "Z1", "methane_ppm": 0.5, "co_ppm": 2.0, "ventilation": 0.8},
            {"zone_id": "Z2", "methane_ppm": 0.8, "co_ppm": 3.0, "ventilation": 0.8},
            {"zone_id": "Z3", "methane_ppm": 3.5 + (i-5)*1.2, "co_ppm": 20.0 + (i-5)*10, "ventilation": 0.8}, # Z3 Báo động đỏ
            {"zone_id": "Z4", "methane_ppm": 0.9, "co_ppm": 4.5, "ventilation": 0.8},
            {"zone_id": "Z5", "methane_ppm": 0.7, "co_ppm": 2.5, "ventilation": 0.8},
            {"zone_id": "Z6", "methane_ppm": 0.4, "co_ppm": 1.8, "ventilation": 0.8},
        ]
    })

# Phase 3: Khí lan sang Z2 (Lan theo gió, Z2 Báo động đỏ, Z3 vẫn cực rủi ro) (Tick 11 -> 15)
for i in range(11, 16):
    SCENARIO_TICKS.append({
        "tick_id": i,
        "zones": [
            {"zone_id": "Z1", "methane_ppm": 1.2, "co_ppm": 5.0, "ventilation": 0.8},
            {"zone_id": "Z2", "methane_ppm": 4.0, "co_ppm": 40.0, "ventilation": 0.8}, # Lan tới Z2
            {"zone_id": "Z3", "methane_ppm": 6.8, "co_ppm": 65.0, "ventilation": 0.8},
            {"zone_id": "Z4", "methane_ppm": 1.5, "co_ppm": 8.0, "ventilation": 0.8},
            {"zone_id": "Z5", "methane_ppm": 1.2, "co_ppm": 4.0, "ventilation": 0.8},
            {"zone_id": "Z6", "methane_ppm": 0.5, "co_ppm": 2.0, "ventilation": 0.8},
        ]
    })

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://127.0.0.1:5000/api/gas_update", help="API URL của Backend")
    parser.add_argument("--delay", type=float, default=2.0, help="Giây nghỉ giữa mỗi frame")
    args = parser.parse_args()

    print("🚀 BẮT ĐẦU CHẠY IoT SIMULATOR CHO DEMO GIÁM KHẢO...")
    print(f"Target URL: {args.url}")
    print("-" * 50)

    for frame in SCENARIO_TICKS:
        tick = frame["tick_id"]
        
        # In ra màn hình để biết đang ở phase nào
        if tick == 1:
            print("\n[PHASE 1] 🟢 HẦM MỎ BÌNH THƯỜNG - Công nhân đang hoạt động")
        elif tick == 6:
            print("\n[PHASE 2] 🔴 SỰ CỐ RÒ RỈ: Ống Methane tại Zone Z3 vỡ. Chỉ số tăng vọt!")
        elif tick == 11:
            print("\n[PHASE 3] ⚠️ KHÍ LAN TRUYỀN: Gió thổi khí độc từ Z3 lan sang Z2. AI đổi hướng sơ tán!")

        print(f"  👉 Gửi dữ liệu Tick #{tick}... ", end="")
        try:
            # Comment dòng gửi thật đi nếu bên BE chưa code xong endpoint
            # resp = requests.post(args.url, json=frame, timeout=2)
            # if resp.status_code == 200:
            #     print("OK")
            # else:
            #     print(f"Lỗi: {resp.status_code}")
            
            # Giả lập gửi OK
            print("OK (Simulated Network)")
        except Exception as e:
            print(f"Lỗi kết nối ({e})")
            
        time.sleep(args.delay)

    print("\n✅ HOÀN THÀNH KỊCH BẢN DEMO.")

if __name__ == "__main__":
    main()
