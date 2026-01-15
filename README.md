# 🩺 Smart Health Monitoring Server
**Heart Rate & Fall Detection System**

## Giới thiệu
Smart Health Monitoring Server là hệ thống backend xây dựng bằng **Flask (Python)**, dùng để giám sát sức khỏe người dùng theo thời gian thực thông qua:
- ❤️ Nhịp tim (Heart Rate)
- 🚨 Phát hiện té ngã (Fall Detection)

Hệ thống phù hợp kết nối với thiết bị IoT (ESP32, wearable), ứng dụng mobile hoặc web nhằm hỗ trợ theo dõi và cảnh báo sức khỏe từ xa.

---

## Tính năng chính
- Nhận dữ liệu nhịp tim qua REST API
- Phân tích nhịp tim bằng:
  - Rule-based
  - Machine Learning
- Làm mượt và gom dữ liệu HR theo thời gian
- Phát hiện và lưu trạng thái té ngã
- Xuất dữ liệu và biểu đồ HR
- Chạy ổn định trên server (headless)

---

## Cấu trúc thư mục
```text
.
├── app.py
├── requirements.txt
├── src/
│   ├── rules/
│   ├── ml/
│   └── fall/
├── data/
└── templates/

---

## Yêu cầu hệ thống
- Python **3.8 trở lên**
- pip

---

## Hướng dẫn chạy hệ thống

### 1️⃣ Git clone và cài đặt thư viện
  - Git clone https://github.com/duyanhle17/heart_rate_check.git
  - Sau đó nhớ đi tới thư mục : cd heart_rate_check
  - Tại thư mục gốc của project, chạy lệnh:

    ```bash
    pip install -r requirements.txt

2️⃣ Chạy server

Sau khi cài đặt xong thư viện, chạy:

python app.py

Server sẽ khởi động tại địa chỉ mặc định:

http://127.0.0.1:5000

Nếu muốn thử chạy trên máy khác, bên dưới link http trong terminal sau khi chạy lệnh "python app.py" sẽ có 1 link khác 

--> đó là link có thể máy khác vào được và xem nhịp tim và phát hiện té ngã của công nhân 

(lưu ý hiện tại mới chỉ làm trong trường hợp 2 máy chạy cùng địa chỉ mạng)

3️⃣ Chạy thử data

Sau khi cài đặt xong thư viện, chạy thử ở 1 terminal mới bằng lệnh này: 
     - Trước tiên nhớ tới đúng đường dẫn folder : cd heart_rate_check
     - Sau đó chạy lệnh này trong terminal : python -m tools.simulate_hr_fall data/fall_raw/non_fall/case_001_machinery.txt
     ( bạn có thể đổi đường dẫn case_001_machinery.txt bằng 1 file .txt khác trong "heart_rate_check/data/fall_raw" nhé để check xem trường hợp fall hoặc non_fall có hiện đúng trên màn hình web không)




