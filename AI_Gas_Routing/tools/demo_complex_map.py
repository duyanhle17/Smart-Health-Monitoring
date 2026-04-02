import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from src.gas.topology import MineTopology
from src.gas.routing import compute_safest_path

# ==============================================================
# PHẦN TEST BẢN ĐỒ PHỨC TẠP
# ==============================================================
METHANE_THRESHOLD = 50.0  
CO_THRESHOLD = 30.0       

def current_gas_to_risk(methane: float, co: float) -> float:
    risk = 0.0
    if methane > METHANE_THRESHOLD or co > CO_THRESHOLD:
        risk += 5000.0  # Phạt cực nặng để khóa đường
        
    risk += (methane / METHANE_THRESHOLD) * 10
    risk += (co / CO_THRESHOLD) * 10
    return risk

def main():
    print("="*80)
    print("🗺️ TEST ĐỊNH TUYẾN TRÊN BẢN ĐỒ HẦM MỎ PHỨC TẠP (10 NODE)")
    print("="*80)

    # 1. Tải bản đồ khu mỏ mới
    topo_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "complex_mine_map.json")
    topology = MineTopology.from_json(topo_path)
    
    # Giả sử công nhân đang ở Gate 1 (Khu vực Cổng vào khai thác sâu)
    start = "Gate_1"
    # Có 2 lối thoát hiểm: Exit_1, Exit_2
    exits = ["Exit_1", "Exit_2"]

    # ==========================
    # KỊCH BẢN 1: BÌNH THƯỜNG
    # ==========================
    sensor_normal = {z: {"methane": 1.0, "co": 1.0} for z in topology.zones}
    risk_normal = {z: current_gas_to_risk(data["methane"], data["co"]) 
                   for z, data in sensor_normal.items()}
    
    path1, cost1 = compute_safest_path(
        topology=topology, start_zone=start, exit_zones=exits, 
        zone_risk=risk_normal, distance_weight=1.0, risk_weight=5.0
    )
    print("\n[ KỊCH BẢN 1: TẤT CẢ KHU VỰC AN TOÀN ]")
    print(f"📍 Công nhân ở: {start} | 🎯 Các lối ra: {exits}")
    print(f"👉 Lộ trình ngắn nhất: {' -> '.join(path1)}")
    print(f"📏 Tổng chi phí (Khoảng cách + Rủi ro): {cost1:.2f}\n")


    # ==========================
    # KỊCH BẢN 2: CHÁY NỔ Ở ZONE_C (Đường chính bị chặn)
    # ==========================
    sensor_fire_C = dict(sensor_normal)
    sensor_fire_C["Zone_C"] = {"methane": 80.0, "co": 50.0} # Vượt ngưỡng
    
    risk_fire_C = {z: current_gas_to_risk(data["methane"], data["co"]) 
                   for z, data in sensor_fire_C.items()}
    
    path2, cost2 = compute_safest_path(
        topology=topology, start_zone=start, exit_zones=exits, 
        zone_risk=risk_fire_C, distance_weight=1.0, risk_weight=5.0
    )
    print("\n[ KỊCH BẢN 2: 🚨 BÁO ĐỘNG KHÍ ĐỘC TẠI ZONE_C ]")
    print(f"⚠️ Điểm rò rỉ: Zone_C (Methane={sensor_fire_C['Zone_C']['methane']}ppm, CO={sensor_fire_C['Zone_C']['co']}ppm)")
    print(f"👉 Lộ trình tự động bẻ lái: {' -> '.join(path2)}")
    print("✅ Giải thích: Thay vì đi qua Zone_C, hệ thống dắt công nhân đi vòng rẽ lên Zone_B -> Zone_D -> Zone_F -> Exit_1.\n")


    # ==========================
    # KỊCH BẢN 3: LAN TOẢ KHÍ ĐỘC SANG ZONE_D VÀ ZONE_F
    # ==========================
    sensor_worse = dict(sensor_fire_C)
    sensor_worse["Zone_D"] = {"methane": 60.0, "co": 40.0} # Lan sang D
    sensor_worse["Zone_F"] = {"methane": 90.0, "co": 80.0} # Bít đường đến Exit_1
    
    risk_worse = {z: current_gas_to_risk(data["methane"], data["co"]) 
                  for z, data in sensor_worse.items()}
    
    path3, cost3 = compute_safest_path(
        topology=topology, start_zone=start, exit_zones=exits, 
        zone_risk=risk_worse, distance_weight=1.0, risk_weight=5.0
    )
    print("\n[ KỊCH BẢN 3: 🚨 KHÍ ĐỘC LAN SANG KHU KHÁC (ZONE_D, ZONE_F) ]")
    print(f"⚠️ Khí lan rộng! Đường đi qua Exit_1 bị khoá do Zone_F độc hại.")
    print(f"👉 Lộ trình tìm lối thoát cuối: {' -> '.join(path3)}")
    print("✅ Giải thích: Hệ thống đã bỏ hoàn toàn Exit_1 (bị Zone_F chắn). Dắt công nhân chạy ngược lại Gate_2 hoặc đi đường cực xa để tránh khí độc!")
    print("="*80)

if __name__ == "__main__":
    main()