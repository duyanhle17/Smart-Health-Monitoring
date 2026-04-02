import os
import sys
import json

# Add root folder so we can import src
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from src.gas.topology import MineTopology
from src.gas.routing import compute_safest_path

# ==============================================================
# HƯỚNG DẪN DEMO THUẬT TOÁN ĐỊNH TUYẾN DỰA THEO KHÍ ĐỘC 
# (Không dùng AI, chỉ dùng Sensor Real-time)
# ==============================================================

# Ngưỡng an toàn (ppm) - nếu quá mức này thì sẽ bị đánh trọng số rủi ro rất cao
METHANE_THRESHOLD = 50.0  
CO_THRESHOLD = 30.0       

def current_gas_to_risk(methane: float, co: float) -> float:
    """
    Hàm biến đổi dữ liệu Sensor hiện tại (Current Gas Level) thành Trọng số rủi ro (Risk Value).
    Nếu khí vượt mức trần an toàn -> chặn đường đó (điểm rủi ro = vô cực hoặc rất cao).
    """
    risk = 0.0
    
    # Cộng dồn risk nếu Methane hoặc CO vượt một mức báo động nhẹ (ví dụ 50% mức nguy hiểm)
    # Nhưng nếu nguy hiểm thật sự, gán rủi ro cực kì lớn để thuật toán tự đổi đường
    if methane > METHANE_THRESHOLD or co > CO_THRESHOLD:
        risk += 1000.0  # Phạt đường này tận 1000 điểm 
        
    # Tính tỉ lệ phần trăm rủi ro nhẹ
    risk += (methane / METHANE_THRESHOLD) * 10
    risk += (co / CO_THRESHOLD) * 10
    
    return risk

def main():
    print("="*60)
    print("🚀 DEMO: THUẬT TOÁN ĐỊNH TUYẾN THOÁT HIỂM CƠ BẢN (KHÔNG AI)")
    print("="*60)

    # 1. Tải bản đồ khu mỏ
    topo_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "mine_topology_sample.json")
    topology = MineTopology.from_json(topo_path)
        
    start = "Z1"
    end = "Z6"

    print("\n[ KỊCH BẢN 1: MÔI TRƯỜNG BÌNH THƯỜNG ]")
    # Tất cả sensor báo về chỉ số bình thường (gần số 0)
    sensor_data_normal = {
        "Z1": {"methane": 1.5, "co": 0.5},
        "Z2": {"methane": 2.0, "co": 1.0},
        "Z3": {"methane": 1.8, "co": 0.5},
        "Z4": {"methane": 1.0, "co": 0.0},
        "Z5": {"methane": 2.5, "co": 2.0},  # Hơi cao xíu nhưng vẫn an toàn
        "Z6": {"methane": 1.0, "co": 0.0},
    }
    
    # Tính Risk Vector cho toàn bộ mỏ từ Sensor Data  
    risk_vector = {zone: current_gas_to_risk(data["methane"], data["co"]) 
                   for zone, data in sensor_data_normal.items()}
    
    # Tìm đường bằng Dijkstra Thuần (Dựa vào chiều dài + Base Risk thấp)
    path, cost = compute_safest_path(
        topology=topology,
        start_zone=start,
        exit_zones=[end],
        zone_risk=risk_vector,
        distance_weight=1.0,
        risk_weight=5.0
    )
    print(f"👉 Dữ liệu Sensor: Zone 5 đang trong ngưỡng AN TOÀN ({sensor_data_normal['Z5']['methane']} ppm Methane)")
    print(f"👉 Đường đi tối ưu: {path} (Chi phí tổng hợp: {cost:.2f})")
    print("✅ Công nhân từ Z1 đi thẳng sang Z5 tới khu thoát hiểm vì đây là lối gần nhất.")


    print("\n" + "-"*60)
    print("\n[ KỊCH BẢN 2: PHÁT HIỆN RÒ RỈ GAS TẠI ZONE 5 ]")
    # ESP32 ở Zone 5 phát hiện Methane tăng vọt lên 75 ppm (vượt ngưỡng 50)
    sensor_data_leak = dict(sensor_data_normal)
    sensor_data_leak["Z5"] = {"methane": 75.0, "co": 10.0} # Vượt ngưỡng Methane!
    
    risk_vector_leak = {zone: current_gas_to_risk(data["methane"], data["co"]) 
                        for zone, data in sensor_data_leak.items()}
                        
    # Thuật toán bắt buộc tự bẻ lái
    path_safe, cost_safe = compute_safest_path(
        topology=topology,
        start_zone=start,
        exit_zones=[end],
        zone_risk=risk_vector_leak,
        distance_weight=1.0,    # Ưu tiên độ dài như cũ
        risk_weight=5.0         # Nhưng đẩy chi phí Risk hiện lên để block đường độc
    )
    
    print(f"👉 Dữ liệu Sensor: ⚠️ Zone 5 RÒ RỈ METHANE! ({sensor_data_leak['Z5']['methane']} ppm)")
    print(f"👉 Đường đi MỚI: {path_safe}")
    print("✅ Thuật toán đã đóng chốt Zone 5 và bẻ lái vòng qua Z3 -> Z4 dẫu cho lối này xa hơn!")
    print("="*60)

if __name__ == "__main__":
    main()
