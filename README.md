# Smart Health Monitoring — SAFE WORK Integrated System

Hệ thống giám sát an toàn lao động và cảnh báo sớm tích hợp định vị 2.5D, phân tích chỉ số sinh tồn (HR, Temp) và nồng độ khí độc (Gas) thời gian thực.

## 🏗️ Kiến trúc Codebase

Dự án được chia làm 3 tầng chính:

### 1. Frontend (`/frontend`)
- **Framework**: React 19 + Vite 7 + Tailwind CSS v4 + DaisyUI.
- **State Management**: Zustand (Global Store) để đồng bộ dữ liệu worker từ backend.
- **Isometric Map**: Bản đồ 2.5D tùy chỉnh sử dụng CSS Transform, hỗ trợ rendering node động, hover label 2D và hiệu ứng di chuyển mượt mà.
- **Data Hook**: `useWorkerData` thực hiện polling dữ liệu sau mỗi 800ms từ backend.

### 2. Backend (`/backend`)
- **Framework**: Flask (Python).
- **Core Engine**:
    - `position_engine.py`: Thuật toán **Trilateration Least-Squares** nội suy vị trí (x, y) từ 3 khoảng cách (ToF) kèm lọc nhiễu Exponential Smoothing.
    - `rules.py` & `ml.py`: Phân loại trạng thái nhịp tim và phát hiện té ngã (ML RandomForest).
- **Simulator**: `demo_simulator.py` mô phỏng 4 công nhân di chuyển với các kịch bản khác nhau (bình thường, nguy kịch, rò rỉ khí).

### 3. Firmware (`/firmware`)
- **Hardware**: ESP32S3 + MAX30102 (HR/Temp) + MPU6050 (IMU).
- **Framework**: Arduino / PlatformIO.
- **Chức năng**: Thu thập dữ liệu cảm biến thô và gửi JSON qua Serial/HTTP.

---

## ✅ Các phần đã hoàn thành

- [x] **Giao diện Dashboard**: Thiết kế công nghiệp (Black/Red/Yellow), map 2.5D hoàn chỉnh.
- [x] **Thuật toán định vị**: Nội suy vị trí tương đối dựa trên 3 Anchor Nodes cố định thành công.
- [x] **Real-time Pipeline**: Kết nối thành công Frontend -> Backend Proxy -> Simulator.
- [x] **Phân vùng thông minh**: Tự động nhận diện Worker đang ở Zone nào (Stage, Left, Right) dựa trên tọa độ.
- [x] **Cảnh báo đa cấp**: Tích hợp cảnh báo nhịp tim, nhiệt độ cao và nồng độ khí độc trên toàn hệ thống.
- [x] **Quản lý nhân sự**: Giao diện CRUD Personnel với Modal và Form.

---

## 🛠️ Lộ trình hoàn thiện để Demo (Critical Steps)

Để đạt trạng thái **"Sẵn sàng Demo"** 100%, cần thực hiện các hạng mục sau:

### 1. 🔌 Tích hợp Phần cứng (Hardware Sync Checklist)
- [ ] **Khai báo IP tĩnh**: Setup IP LAN tĩnh cho Backend server để ESP32 có thể gửi gói tin `device_telemetry` đến đúng địa chỉ cục bộ (Ví dụ: `192.168.1.100:5000/api/device_telemetry`).
- [ ] **Chuẩn hóa Packet JSON**: Chuyển đổi dữ liệu C C++ sang format JSON theo mẫu: `{"worker_id": "WK_102", "telemetry": {"hr": 80, ...}}`.
- [ ] **Xử lý khuất sóng (Queue buffer)**: Lập trình ESP lưu đệm dữ liệu cảm biến vào RAM/Flash khi vào vùng sập hầm hoặc mất WiFi. Khi có sóng lại, xả queue về Backend để phục hồi đồ thị.
- [ ] **Ánh xạ ID định danh**: Map MAC Address của vi điều khiển ESP32 với mã nhân viên tĩnh `WK_102`.
- [ ] Cập nhật kết nối từ HTTP POST sang WebSocket để tiết kiệm băng thông và tăng tần số mẫu lên 10Hz.

### 2. 🔗 Connectivity & Backend Sync (Đã xử lý Proxy)
- [x] **Vite Proxy**: Cấu hình proxy Frontend gọi API tới Backend (Port 5000) thành công.
- [x] **Zustand Data Binding**: Kết nối Store để Map và Sidebar nhận dữ liệu từ Backend.
- [x] **Real-time Page Sync**: Cập nhật trang `/environment` và `/alerts` để đọc dữ liệu từ Zustand Store thay vì dữ liệu mẫu.
- [x] **Worker Sync**: Kết nối danh sách worker thực tế từ Backend đổ lên bảng của trang `/dashboard`, xử lý cập nhật vị trí, nhịp tim, nhiệt độ, nồng độ khí độc thời gian thực đúng với data trả về từ sensor -> backend.

### 2. 📍 Position & Logic
- [x] **Trilateration Engine**: Thuật toán nội suy vị trí từ 3 khoảng cách (d1, d2, d3).
- [x] **Demo Simulator**: Xây dựng kịch bản di chuyển cho 4 Worker phục vụ trình diễn.
- [x] **Movement Smoothing**: Tinh chỉnh tham số `ALPHA` trong `position_engine.py` để Worker di chuyển mượt hơn trên UI.

---

## 🚀 Hướng dẫn khởi chạy (Demo Mode)

Cần mở **3 Terminal** song song:

1. **Terminal 1 (Backend)**: 
```bash
docker compose up -d --build
```
2. **Terminal 2 (Simulator)**: Chạy tự động trong Docker.
3. **Terminal 3 (Frontend)**: Chạy tự động trong Docker, truy cập `http://localhost:5173/dashboard`

---

## 📡 Giao thức kết nối & Payload

Hệ thống sử dụng **WebSocket (Socket.IO)** để đồng bộ dữ liệu thời gian thực giữa Backend và Client nhằm giảm độ trễ (latency).

### 1. Sự kiện `latest_status` (Backend -> Client)
Gói tin được Backend phát (emit) liên tục mỗi khi có dữ liệu mới từ phần cứng/Simulator.
```json
{
  "workers": [
    {
      "worker_id": "WK_102",
      "hr": 85.5,
      "temp": 37.2,
      "gas": 2.5,
      "o2": 20.9,
      "x": 45.3,
      "y": 20.1,
      "zone": "GAMMA_STAGE",
      "alert": "NORMAL",
      "hr_status": "NORMAL",
      "gas_status": "SAFE",
      "fall_status": "SAFE"
    }
  ],
  "zones": {
    "GAMMA_STAGE": {
      "gas": 2.5,
      "o2": 20.9,
      "status": "SAFE"
    }
  }
}
```

### 2. Sự kiện WebSocket `device_telemetry` (Phần cứng -> Backend)
Phần cứng (ESP32) kết nối với Backend thông qua WebSocket. Các gói tin đo lường (telemetry) được thiết bị gửi lên qua sự kiện (event) `device_telemetry` định kỳ (tần số khuyến nghị 1-10Hz) để cập nhật trạng thái thời gian thực, giảm tối đa độ trễ so với HTTP POST.

Cấu trúc JSON Payload:
```json
{
  "worker_id": "WK_102",
  "telemetry": {
    "hr": 85.0,
    "temp": 37.2,
    "gas": 1.5,
    "o2": 20.9,
    "d1": 15.2, "d2": 20.5, "d3": 18.0,
    "ax": 0.05, "ay": 0.02, "az": 9.8,
    "gx": 0, "gy": 0, "gz": 0,
    "fall_alert": "SAFE"
  }
}
```

**Giải thích các trường dữ liệu (Fields Explanation):**

*   **`worker_id`** *(String)*: Mã định danh duy nhất của thiết bị/công nhân (VD: "WK_102"). Thường được ánh xạ (mapping) từ địa chỉ MAC của board ESP32.
*   **`telemetry`** *(Object)*: Đối tượng chứa toàn bộ dữ liệu cảm biến đo đạc được ở chu kỳ hiện tại:
    *   **Sinh tồn:**
        *   `hr` *(Float)*: Nhịp tim (Heart Rate) tính bằng nhịp/phút (BPM), đo từ cảm biến (VD: MAX30102).
        *   `temp` *(Float)*: Nhiệt độ cơ thể tính bằng độ C (°C).
    *   **Môi trường:**
        *   `gas` *(Float)*: Nồng độ khí độc (VD: CH4, CO...) tính bằng ppm, đo từ cảm biến khí (VD: MQ series).
        *   `o2` *(Float)*: Nồng độ Oxy trong không khí tính theo %. Mức an toàn bình thường là khoảng 20.9%.
    *   **Định vị (ToF/UWB):**
        *   `d1`, `d2`, `d3` *(Float)*: Khoảng cách từ thiết bị (Tag) đến 3 Trạm neo cố định (Anchor Nodes), tính bằng mét (m). Dữ liệu này được gửi lên để Backend nội suy tọa độ 2D (x, y) bằng thuật toán Trilateration Least-Squares.
    *   **Chuyển động (IMU - MPU6050):**
        *   `ax`, `ay`, `az` *(Float)*: Gia tốc 3 trục X, Y, Z (Acceleration). Dùng để phát hiện va chạm hoặc rơi tự do.
        *   `gx`, `gy`, `gz` *(Float)*: Vận tốc góc 3 trục X, Y, Z (Gyroscope). Dùng để xác định góc nghiêng và tư thế ngã.
        *   `fall_alert` *(String)*: Cờ trạng thái té ngã sơ bộ tính toán ngay trên vi điều khiển (VD: `SAFE`, `WARNING`, `DANGER`). Backend sử dụng trường này, kết hợp với dữ liệu IMU thô đưa qua mô hình Machine Learning để ra quyết định cảnh báo chính xác nhất.

---

## 📈 Tương lai (Roadmap)

1. **Firmware WebSocket**: Cập nhật firmware ESP32 chuyển từ HTTP POST sang WebSocket để tiết kiệm băng thông mạng nhúng.
2. **Wireless Hardware**: Kết nối dữ liệu thực từ thiết bị đeo thay vì Simulator.
