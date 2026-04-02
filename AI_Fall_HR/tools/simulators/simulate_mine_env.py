import requests
import time
import random

SERVER_URL = "http://127.0.0.1:5000"

# Kịch bản 3 công nhân
workers = {
    "W1": {"x": 70.0, "y": 50.0, "base_hr": 75, "direction": 1, "path": "horizontal"},
    "W2": {"x": 50.0, "y": 10.0, "base_hr": 80, "direction": 1, "path": "vertical"},
    "W3": {"x": 48.0, "y": 48.0, "base_hr": 70, "direction": 0, "path": "stationary"}
}

def simulate_data():
    print("🚀 Bắt đầu giả lập hệ thống Mỏ hầm lò nâng cao...")
    print("- 3 Công nhân (W1, W2, W3)")
    print("- Bao gồm cảm biến HR, Fall và Toxic Gas (CH4/CO)")
    
    tick = 0
    gas_leak_active = False

    # Giả lập cho server khởi tạo file lưu với một vài sự cố đã diễn ra để test Heatmap tức thì
    print("=> Bơm một vài sự cố ban đầu vào server để Heatmap hiện lên lập tức...")
    for _ in range(5):
        # Mô phỏng W1 bị ngã quanh x=80, y=50
        rx = 80 + random.uniform(-1, 1)
        ry = 50 + random.uniform(-1, 1)
        requests.post(f"{SERVER_URL}/location", json={"worker_id": "W1", "x": rx, "y": ry})
        requests.post(f"{SERVER_URL}/gas", json={"worker_id": "W1", "gas": 90}) # Khí độc kích hoạt danger

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
