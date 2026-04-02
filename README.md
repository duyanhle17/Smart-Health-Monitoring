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

## 🚀 Hướng Dẫn Chuẩn Bị & Chạy Demo Toàn Dự Án

Dưới đây là checklist các bước cần thiết để khởi chạy thành công buổi demo trực tiếp với phần cứng thật (Single-Anchor PDR-Lite):

### Bước 1: Khởi động Server (Backend & Frontend)
1. Bật Docker Desktop trên máy tính.
2. Mở Terminal tại thư mục gốc của dự án, chạy lệnh khởi tạo cơ sở dữ liệu, API Backend và cả giao diện Web Frontend:
   ```bash
   docker compose up -d --build db backend frontend
   ```
   *(Lưu ý: Chúng ta không gọi service `simulator` trong lệnh này để tránh dữ liệu giả lập đụng độ với phần cứng ESP32 thật gửi lên)*
3. Mở trình duyệt web và truy cập vào **`http://localhost:5173`**. Cả hệ thống đã sẵn sàng online.

### Bước 2: Cấu hình Mạng (WiFi & IP)
1. Đảm bảo máy tính chạy Server và mạch ESP32 **kết nối chung một mạng WiFi** (hoặc dùng điện thoại phát 4G làm Hotspot).
2. Lấy IP LAN tĩnh của máy tính (vd: `192.168.1.xxx` trên Windows `ipconfig`, hoặc Mac `ifconfig`).
3. Mở file `hardware/src/config.h`:
   - Điền đúng tên WiFi (`WIFI_SSID`) và Mật khẩu (`WIFI_PASSWORD`).
   - Cập nhật biến `BACKEND_IP` thành IP LAN vừa lấy.
4. (Tuỳ chọn) Đấu nối chân cảm biến khí MQ vào `Analog 34` và nút nhấn reset góc Yaw vào `Chân 0` (Nút BOOT sẵn trên mạch ESP32 Worker).

### Bước 3: Nạp Firmware phần cứng (ESP32)
1. Dùng VSCode / PlatformIO cắm cáp USB vào mạch **Anchor** (Trạm neo).
   - Nạp mã nguồn từ file `Anchor.cpp`.
   - Cấp nguồn và đặt mạch ở cố định tại điểm giữa Sân khấu (trục toạ độ giả định `x=50, y=20`).
2. Rút cáp, cắm sang mạch **Worker** (Thiết bị đeo).
   - Nạp mã nguồn từ file `main.cpp`. 
   - Cấp nguồn pin sơ cua/sạc dự phòng cho Worker.

### Bước 4: Vận hành Giao diện (Calibration & Màn Trình Diễn)
1. Đăng nhập vào giao diện web (`http://localhost:5173/dashboard`). Bật thanh Sidebar bên phải để quan sát số lượng Anchor và Worker online.
2. **Calibration Yaw**: Đeo bộ thiết bị Worker vào người, đứng ở cuối đường dẫn (Ví dụ phía trên trục Y=80), **hướng mặt thẳng** về phía trạm Anchor ở sân khấu. Bấm **nút BOOT** trên ESP32 để reset trục hướng chuyển động (Yaw = 0 độ).
3. Bắt đầu di chuyển tiến về phía sân khấu. Mạch Worker sẽ tiến hành bắn khoảng cách d1 và góc lệch IMU (10Hz) cập nhật vị trí thời gian thực thẳng lên bản đồ 2.5D.
4. Xem bảng cảnh báo ở cột trái để thấy thông số đo Khí độc và tọa độ. (Có thể thổi khí Gas/Bật lửa gần cảm biến để kích hoạt mức DANGER đỏ rực giao diện UI).

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

---

## Cơ chế AI & Thuật toán phát hiện té ngã (Fall Detection)

Để hiểu rõ cách mô hình phát hiện ngã hoạt động, chúng ta có thể chia nhỏ luồng xử lý thành **4 bước** từ lúc nhận dữ liệu đến lúc phát hiện cú ngã. Thuật toán AI cốt lõi mà hệ thống sử dụng là **Random Forest**, kết hợp với trích xuất đặc trưng toán học.

### 1. Đọc dữ liệu và Cắt cửa sổ (Sliding Window)
Thiết bị (ví dụ: cảm biến đeo) liên tục gửi về hệ thống 6 trục: Gia tốc (Acc X, Y, Z) và Góc quay (Gyro X, Y, Z). 
Thay vì nhìn từng dòng dữ liệu thô, hệ thống gom chúng lại thành từng cụm gọi là **cửa sổ (window)**.
*   **Cấu hình hiện tại:** Cửa sổ kích thước `400` mẫu, bước trượt (step) `200` mẫu.
*   **Ví dụ thực tế:** Nếu thiết bị gửi 100 mẫu/giây, thì một cửa sổ 400 mẫu tương đương **4 giây** chuyển động. Cứ mỗi 2 giây (200 mẫu trượt), mô hình sẽ trích xuất 4 giây gần nhất để phân tích xem hành động này là "Bình thường" hay "Ngã".

### 2. Trích xuất đặc trưng (Feature Extraction) & SVM
*Lưu ý: Chữ **SVM** ở đây KHÔNG PHẢI là mô hình Support Vector Machine, mà nó là viết tắt của **Signal Vector Magnitude** (Độ lớn Vector Tín hiệu).*

Dữ liệu thô (400 dòng x 6 cột) là quá lớn và nhiễu. Hệ thống sẽ thu gọn dữ liệu này thành **22 con số đặc trưng** để báo cho AI biết mức độ mạnh của chuyển động:
*   **Tính SVM (Signal Vector Magnitude):** 
    Để không phụ thuộc vào tư thế đeo thiết bị (hướng của các trục X, Y bị lật), chúng ta tính gia tốc tổng hợp lực bằng toán học:  $SVM = \sqrt{X^2 + Y^2 + Z^2}$. Khi xảy ra va chạm hay ngã, chỉ số SVM sẽ vọt lên đột biến.
*   **Tính các thông số thống kê khác:** 
    Trên cửa sổ 400 mẫu đó, hệ thống tiếp tục tính các giá trị thống kê: **Mean** (Trung bình), **Std** (Độ lệch chuẩn - xem mức độ biến động có mạnh không), **Max** (Đỉnh lực lớn nhất), **Min**, và **RMS** (Căn quân phương) cho cả giá trị gia tốc lẫn góc quay.
*   **Kết quả:** Cửa sổ chứa 400 dòng dữ liệu thô phân mảnh giờ đây được cô đặc thành **1 dòng duy nhất gồm 22 cột (con số)**.

### 3. Thuật toán AI: Rừng ngẫu nhiên (Random Forest)
Sau khi trích xuất ra 22 đặc trưng, mảng con số này được nạp vào mô hình học máy **Random Forest Classifier**:
*   **Cấu trúc thuật toán:** Rừng ngẫu nhiên thực chất là sự tập hợp của rất nhiều **Cây Quyết Định (Decision Tree)**. Trong ứng viên AI này, số lượng cây (estimators) được set là 200, với chiều sâu tối đa (max_depth) là 15.
*   **Cơ chế học:** Khi huấn luyện, mô hình không bắt nguyên 1 cây học sạch dữ liệu. Nó tạo ra 200 cây chạy tách biệt, mỗi cây chỉ được xem một phần nhỏ dữ liệu và đặc trưng. Mỗi cây tự rút ra những bài học riêng cho mình (Ví dụ: *"Nếu SVM Max > 3G và Gyro_Std > 150 thì là NGÃ"*).
*   **Ưu điểm:** Random Forest đặc biệt mạnh, chống nhiễu cực tốt với các bộ dữ liệu cơ lý thống kê dạng bảng và hầu như không bị học vẹt (overfitting).

### 4. Luồng xử lý thời gian thực (Real-time Pipeline)
Hình dung một công nhân đang đi bộ rồi vấp cáp đập người xuống đất:
1.  **Thu thập dữ liệu:** Thiết bị liên tục đẩy dữ liệu vào bộ đệm tạm thời (Deque buffer). Khi dồn đủ 400 mẫu, nó kích hoạt nhịp phân tích.
2.  **Xử lý và Lọc đặc trưng:** Hàm tính toán nhận diện lúc đi bộ gia tốc chỉ tầm $1.5G$, nhưng khoảnh khắc rơi và chạm đất SVM Max vọt lên $4.2G$ kèm sự thay đổi góc xoay đột ngột $\rightarrow$ trả ra 1 mảng 22 con số.
3.  **Bỏ phiếu (Voting):** Mảng 22 số này được ném cho 200 nhánh cây trong Rừng ngẫu nhiên. Cây 1 bảo "Là ngã", cây 2 đồng thuận "Ngã", cây 3 bảo "Có thể nhảy bước" v.v...
4.  **Kết luận:** Hệ thống quy định ngặt nghèo trong logic (file `fall_state.py`). Nếu số lượng cây biểu quyết ngã **áp đảo vượt qua mức 70%** (`prob > 0.7`), hệ thống ngay lập tức chốt hạ là `[FALL]` và nổ tín hiệu cảnh báo ra giao diện của người quan sát.

Cách tiếp cận này dùng cửa sổ trượt trích suất đặc trưng cơ học rồi đưa qua mô hình Machine Learning biểu quyết đa số — nó rất nhanh, tốn ít tài nguyên nhưng vẫn đảm bảo độ nhạy cao. Hợp lý với máy chủ real-time hoặc các chip vi điều khiển giới hạn dung lượng tính toán.

---

## Gas Leak Prediction & Smart Routing (Training Baseline)

Mục tiêu phần này là train độc lập mô hình dự báo nồng độ khí theo thời gian + topology hầm mỏ, để bàn giao artifact cho team web/server tích hợp sau.

### 1) Chuẩn bị dữ liệu

Dataset CSV cho train dùng format:

```csv
timestamp,zone_id,methane_ppm,co_ppm,ventilation_level
0,Z1,0.62,2.10,0.71
0,Z2,0.70,2.34,0.68
30,Z1,0.60,2.07,0.72
...
```

Topology hầm dùng JSON:

```json
{
  "zones": ["Z1", "Z2", "Z3"],
  "edges": [
    {"source": "Z1", "target": "Z2", "distance_m": 70},
    {"source": "Z2", "target": "Z3", "distance_m": 65}
  ]
}
```

Repo đã có sẵn topology mẫu tại `data/mine_topology_sample.json`.

### 2) Tạo dữ liệu mẫu nhanh (nếu chưa có data thực)

```bash
python tools/generate_gas_data.py --output data/gas_training_sample.csv --steps 720 --sample-seconds 30
```

### 3) Train model dự báo khí

```bash
python model/gas_train.py \
  --gas-csv data/gas_training_sample.csv \
  --topology data/mine_topology_sample.json \
  --history-steps 6 \
  --horizons 20,60
```

Trong đó:
- `history-steps=6`: dùng 6 bước lịch sử gần nhất làm đặc trưng.
- `horizons=20,60`: dự báo ở bước +20 và +60. Nếu dữ liệu mỗi 30s thì tương ứng 10 phút và 30 phút.

### 4) Artifact đầu ra để gửi team web/server

Sau khi train xong sẽ có:
- `model/gas_forecast_bundle.pkl`: model + metadata (feature names, horizons, topology, zone list).
- `model/gas_training_report.json`: chỉ số MAE/R2 theo từng target.

### 5) Demo định tuyến sơ tán thông minh

```bash
python model/gas_route_demo.py \
  --bundle model/gas_forecast_bundle.pkl \
  --gas-csv data/gas_training_sample.csv \
  --start-zone Z3 \
  --exit-zones Z1,Z6
```

Script sẽ:
- Dự báo mức rủi ro khí theo từng zone.
- Chặn zone nguy hiểm nặng (blocked zones).
- Tính đường thoát an toàn nhất bằng Dijkstra trọng số động (distance + risk).

### 6) Thuật toán đang dùng ở baseline này

- Forecasting: `MultiOutputRegressor(RandomForestRegressor)`.
- Feature chính: lịch sử methane/CO theo zone + thông gió + trung bình khí từ zone lân cận + bậc nút đồ thị.
- Routing: Dijkstra với trọng số động theo risk để ưu tiên đường an toàn.

Baseline này nhẹ, phù hợp chạy nhanh để bàn giao sớm. Khi có đủ dữ liệu thực và tài nguyên mạnh hơn, có thể nâng cấp sang GNN + LSTM cho lan truyền khí theo topology.

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
