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




