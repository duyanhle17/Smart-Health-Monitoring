# Giải thích chi tiết Thuật toán Phát hiện Té ngã (Fall Detection)

Bài viết này nhằm làm sáng tỏ các khái niệm kỹ thuật trong cơ chế xử lý AI của hệ thống phát hiện té ngã, được chia làm 3 phần chính đi theo luồng xử lý thông tin.

---

## 1. Cắt cửa sổ dữ liệu (Sliding Window) là làm gì?

Cảm biến đo lường (như cảm biến đeo tay, ESP32) liên tục thu thập và gửi các thông số vật lý của người dùng. Hệ thống của bạn đo **6 trục**: X, Y, Z của gia tốc kế (đo lực tốc độ) và X, Y, Z của con quay hồi chuyển (đo độ góc xoay người).

### Hiểu về tần số và các mẫu (Samples)
- **1 mẫu (Sample):** Là 1 lần cảm biến "chớp" lấy thông tin. Nó gồm một bộ 6 con số ứng với 6 trục ở ngay khoảnh khắc đó.
- Cáo biến của bạn lấy mẫu ở tần số **10Hz** (10 lần trong 1 giây). Tức là cứ khoảng **100 mili-giây** (0.1 giây), chúng ta lại có 1 mẫu dữ liệu mới. Một mẫu lẻ tẻ này (diễn ra trong 0.1 giây) là quá ngắn ngủi và hoàn toàn không đủ dữ kiện để AI khẳng định một người đang làm gì.

### 40 mẫu = 4 giây chuyển động (Cần lưu ý thay đổi cấu hình)
*Vì cảm biến của bạn chạy ở 10Hz, ta cần điều chỉnh kích thước cửa sổ so với cấu hình mặc định cũ (100Hz).*

Để máy tính nhìn nhận một chuỗi hành động trọn vẹn, hệ thống cần gom **40 mẫu liên tiếp** lại để xét duyệt 1 lần (gọi là 1 cửa sổ dữ liệu - *Window*). Với tần số 10 mẫu/giây thu được, nhóm 40 mẫu này sẽ tương đương chính xác với **4 giây** thời gian thực.
Khoảng 4 giây là đủ dài để ghi nhận trọn vẹn 3 giai đoạn của một cú ngã thực tế: (1) Trạng thái đứng bình thường -> (2) Mất thăng bằng rơi tự do trong không khí -> (3) Khoảnh khắc va đập mạnh xuống đất và nằm im.

*(Lưu ý: Nếu code hiện tại của bạn vẫn đang để "cửa sổ 400 mẫu", với tần số 10Hz nó sẽ thu thập tới tận **40 giây** – quá dài cho một cú ngã. Bạn cần sửa code lại thành **Window Size = 40** nhé).*

### Bước trượt (Step) 20 mẫu (2 giây)
Nếu hệ thống đợi đủ 4 giây (40 mẫu) để chốt một đoạn, rồi mới đợi tiếp 4 giây (40 mẫu tiếp theo) lấy đoạn hai, sẽ sinh ra *điểm mù thời gian*. *Ví dụ: Nếu trượt chân bắt đầu từ giây thứ 3 và nằm im ở giây thứ 5? Việc cắt phăng đôi đồ thị ở ngay giây thứ 4 như thế khiến AI chỉ nhìn thấy một mảng đứt gãy.*

**Giải pháp "Cửa sổ trượt" (Sliding Window):**
- **Lần phân tích 1:** Hệ thống cắt khúc từ **Giây 0 đến Giây 4** (Mẫu số 0 đến 40).
- Thay vì tiếp tục ở mẫu thứ 40, hệ thống biểu diễn **trượt lên phía trước 2 giây** (tức là tịnh tiến 20 mẫu).
- **Lần phân tích 2:** Cắt khúc bù trừ kéo dài từ **Giây 2 đến Giây 6** (Mẫu 20 đến 60).
- **Lần phân tích 3:** Trượt tiếp từ **Giây 4 đến Giây 8** (Mẫu 40 đến 80).

Sự giao thoa đan xen (overlap) này giúp hệ thống quét liên tục 2 giây một lần và bắt trọn chuỗi hành động ngã dẫu nó xảy ra đứt quãng ngay ranh giới thời gian.

---

## 2. Trích xuất đặc trưng (Feature Extraction) & Độ đo SVM

Khi đã có mảng ma trận của 40 dòng dữ liệu (thay vì 400 như ở chuẩn 100Hz), ta cần thu gọn ma trận này thành một chùm thông số cốt lõi. Quá trình chọn lọc này gọi là **Trích xuất đặc trưng**.


### SVM là gì và tại sao cần tính toán Vector?
- **Vấn đề của trục dữ liệu thô:** Nếu người đó đeo thiết bị lộn ngược, con số lực của trục X thay vì mang dấu dương ($+X$) lại báo dấu âm ($-X$). Hoặc cú ngã đập mạng sườn ngang sẽ khác hoàn toàn với ngã sấp đập bụng (lực dồn vào trục Y khác với Z). 
- **Giải pháp - Tính SVM (Signal Vector Magnitude):** Đây không phải thuật toán phân loại máy học Support Vector Machine, mà là **Mức độ lớn tổng hợp lực**. Công thức Pytago quy đổi năng lượng 3 chiều thành một thông số chấn động:
  $$SVM = \sqrt{X^2 + Y^2 + Z^2}$$
- **Lợi ích:** Công thức này đo đếm năng lượng của 3 chiều. Nó xóa bỏ rào cản về việc thiết bị úp hay ngửa hay người dùng ngã tư thế nào. Dù ngã hướng nào, miễn cơ thể đập bùm xuống mặt đất, tổng năng lượng giải phóng là SVM trên biểu đồ sẽ nhảy một đỉnh rất lớn.

### Mục đích của tính toán thông số Thống kê?
Thông qua 400 mẫu lưu trữ được, các chỉ số sau đây được dùng để điền "Bệnh án" giao cho Trí tuệ AI chẩn bệnh:
- **Max (Đỉnh cực đại):** Lực va đập mạnh nhất đạt đỉnh bao nhiêu G? Cao trên mức 3G-4G là vô cùng đáng ngờ.
- **Min (Mức rơi tĩnh):** Bắt khoảnh khắc các cảm biến đo trạng thái rơi không trọng lượng khi ngã trong không khí.
- **Std (Độ lệch chuẩn - Mức phân tán năng lượng):** Rất dễ để AI phân biệt được việc té ngã mất kiểm soát (lực lúc yên lúc vọt cực đại $\rightarrow$ Std cao) với chạy bộ (Lực cũng cao nhưng vọt lên xuống đều đặn nhịp nhàng $\rightarrow$ mô hình Std khác hẳn).
- **Mean (Trung bình) & RMS (Căn quân phương):** Các thông số hỗ trợ đo lường tổng thể 4 giây và phân biệt cú ngã thực (ngã xong nằm in) với một cú vung tay mạnh thông thường.

Nhờ bước này, bộ dữ liệu 400 dòng gốc cồng kềnh biến thành **1 hàng gồm 22 cột chỉ số duy nhất**.

---

## 3. Bản chất của thuật toán Rừng ngẫu nhiên (Random Forest)

Giờ máy đã thu được 22 con số đặc tính rút gọn đó, nó đưa thông số vào buồng kiểm định cuối. Buồng máy này áp dụng AI **Random Forest (Rừng ngẫu nhiên)**.

### Tựu chung về Cây Quyết định đến Rừng:
- **Cây quyết định (Decision Tree):** Giống như một bản đồ hỏi đáp (Ví dụ: *Hỏi 1 -> Có phải $SVM_{Max}$ > 3.0? -> Phải thì rẽ trái; Hỏi 2 -> $Std$ có vượt 1.5 không? -> Phải thì kết luận: Ngã*). Tuy nhiên, một cây duy nhất cực kì rủi ro và thiếu tinh vi.
- **Dựng nên 200 chuyên gia (Random Forest):** Hệ thống không dùng 1 cây đơn nhất. Thuật toán này sinh ra một cánh rừng chứa **200 cây quyết định** ghép lại để hoạt động song song nhau trên cùng tập tin dữ kiện.

### Yếu tố "Ngẫu nhiên" mang lại tác dụng gì?
Trong quá trình máy tự huấn luyện (training), người ta lấp che một số cột dữ liệu của vài cây, và ép từng cây chỉ được học một lượng mẫu riêng lẻ tự tráo. Yêu cầu này rèn cho 200 cây phải hình thành tư duy chuyên biệt tránh học vẹt. Sẽ có những cây ưu tiên xét gia tốc rơi gãy, có cây ưu tiên nhịp quay hồi chuyển để xem người có nhào lộn hay không...

### Luồng Hoạt động Biểu Quyết Thực tế (Voting)
Khi đưa vào phân tích thực dụng:
1. Có một gói dữ liệu phân tích 22 thông số của người dùng được gởi tới.
2. Hệ thống phát sóng để toàn bộ 200 nhánh cây cùng lên tiếng quyết định.
3. Cây 1 gõ búa: "Phản hồi mẫu này là NGÃ!"
4. Cây 2 gõ búa: "Đúng là Ngã."
5. Cây 3 không đồng ý: "Dựa vào chỉ số này thì nghiêng trục giống cúi nhặt vật."
...
Cuối cùng, hệ thống tính tỷ lệ bình chọn (Voting Probability). Thuật toán cài đặt điều kiện `prob > 0.7` — có nghĩa là: Bắt buộc phải có **ít nhất 140 cây đồng thuận có ngã (chiếm ngưỡng 70% trong 200 cây)** thì còi báo động mới nhảy kết luận **[FALL]** phát lên ứng dụng. 

Chính cơ chế Biểu quyết đông đảo này giúp cho thuật toán Random Forest cực kỳ đáng tin cậy. Nó dọn sạch thông tin nhiễu vặt và chạy phân loại nhanh như chớp.
