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

### 1. 🔗 Connectivity & Backend Sync (Ưu tiên)
- [x] **Vite Proxy**: Cấu hình proxy Frontend gọi API tới Backend (Port 5000) thành công.
- [x] **Zustand Data Binding**: Kết nối Store để Map và Sidebar nhận dữ liệu từ Backend.
- [ ] **Real-time Page Sync**: Cập nhật trang `/environment` và `/alerts` để đọc dữ liệu từ Zustand Store thay vì dữ liệu mẫu.
- [ ] **Personnel Sync**: Kết nối danh sách nhân sự thực tế từ Backend đổ lên bảng của trang `/personnel`.

### 2. 📍 Position & Logic
- [x] **Trilateration Engine**: Thuật toán nội suy vị trí từ 3 khoảng cách (d1, d2, d3).
- [x] **Demo Simulator**: Xây dựng kịch bản di chuyển cho 4 Worker phục vụ trình diễn.
- [ ] **Movement Smoothing**: Tinh chỉnh tham số `ALPHA` trong `position_engine.py` để Worker di chuyển mượt hơn trên UI.

---

## 🚀 Hướng dẫn khởi chạy (Demo Mode)

Cần mở **3 Terminal** song song:

1. **Terminal 1 (Backend)**: `python -m backend.app`
2. **Terminal 2 (Simulator)**: `python -m backend.demo_simulator`
3. **Terminal 3 (Frontend)**: `cd frontend && npm run dev`

Mở trình duyệt tại: `http://localhost:5173/dashboard`

---

## 📈 Tương lai (Roadmap)

1. **WebSocket**: Nâng cấp từ Polling sang WebSocket để giảm độ trễ tối đa.
2. **Database**: Tích hợp PostgreSQL/MongoDB cho việc lưu trữ và truy vấn lịch sử.
3. **Analytics**: Xây dựng Dashboard biểu đồ chi tiết (Charts) tại trang phân tích.
4. **Wireless Hardware**: Kết nối dữ liệu thực từ ESP32 qua Wi-Fi thay vì Simulator.
