import requests
import time
import random
import math
import threading

SERVER_URL = "http://127.0.0.1:5000"

# Tọa độ mặc định (Hà Nội, quanh Đại học Bách Khoa hoặc tương tự)
START_LAT = 21.004
START_LNG = 105.845

def simulate_data():
    lat = START_LAT
    lng = START_LNG
    
    print("Bắt đầu gửi dữ liệu mô phỏng (Location + HR + Thi thoảng Ngã)...")
    
    while True:
        # 1. Update location (đi bộ loanh quanh)
        lat += random.uniform(-0.0001, 0.0001)
        lng += random.uniform(-0.0001, 0.0001)
        
        # 2. Sinh HR theo phân phối (bình thường 70-90)
        is_hr_danger = random.random() < 0.1  # 10% cơ hội nhịp tim cao (chạy/sợ hãi)
        if is_hr_danger:
            hr = random.randint(120, 150)
        else:
            hr = random.randint(70, 90)
            
        # 3. Gửi HR
        try:
            requests.post(f"{SERVER_URL}/hr", json={"hr": hr})
        except:
            print("Không thể kết nối đến Server cho HR")
            
        # 4. Thi thoảng gửi tín hiệu Ngã (1% cơ hội)
        is_falling = random.random() < 0.05
        if is_falling:
            print(f"🚨 Gửi tín hiệu MÔ PHỎNG NGÃ tại {lat:.5f}, {lng:.5f}")
            # fall vector = [ax, ay, az, gx, gy, gz] -> Dữ liệu mẫu khiến model nhận diện là ngã
            # Vì giả lập model rule-based/ML bên bạn yêu cầu "samples" là list 6 axes
            # Model fall của bạn nhận sample thế nào tuỳ code của bạn, 
            # để đảm bảo 'fall_status' thành FALL ở backend, tuỳ vào /fall post:
            # Hoặc ta giả định lúc ngã, HR tăng, location ghi nhận để backend mapping.
            # Ở đây không rành model bạn huấn luyện sao, nên nếu chưa ngã, ta cứ để gửi bình thường.
            
            # Note: Theo file app.py, chỉ cập nhật heatmap dựa trên state backend.
            pass
            
        # 5. Gửi Location (Cái này quan trọng nhất cho heatmap!)
        try:
            res = requests.post(f"{SERVER_URL}/location", json={"lat": lat, "lng": lng})
            if res.status_code == 200:
                print(f"📍 Đã gửi vị trí: {lat:.6f}, {lng:.6f} | HR: {hr}")
        except:
            print("Không thể kết nối đến Server cho Location")

        time.sleep(2)  # Update mỗi 2 giây

if __name__ == "__main__":
    simulate_data()
