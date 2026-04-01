# SafeWork Hardware Firmware

Thư mục này chứa toàn bộ source code (C++) cho firmware của các thiết bị **ESP32-S3**. Mã nguồn tại đây đã được cấu hình và sử dụng nền tảng **PlatformIO** để biên dịch. Các board mạch thực tế bao gồm thiết bị **Anchor** cố định và các **Worker** di động (được trang bị UWB, IMU, cảm biến nhịp tim, nhiệt độ).

---

## 💻 Môi trường Cài đặt

Để biên dịch và nạp code cho phần cứng, bạn cần phải cài đặt **PlatformIO**. Nếu bạn sử dụng Visual Studio Code (VSCode), việc này rất đơn giản:

1. Tải và cài đặt [Visual Studio Code](https://code.visualstudio.com/).
2. Trong VSCode, mở tab **Extensions** (`Ctrl+Shift+X` hoặc `Cmd+Shift+X`).
3. Tìm kiếm **PlatformIO IDE** và nhấn Install. Bạn có thể phải đợi một chút để PlatformIO cài đặt nhân hệ thống của nó.
4. Sau khi cài đặt xong, hãy **khởi động lại VSCode**. Bạn sẽ thấy một biểu tượng con kiến (logo của PlatformIO) ở thanh Sidebar bên trái.

---

## 🛠️ Cấu hình trước khi nạp

Trước khi nạp code vào mạch, bạn cần phải cấu hình thông tin mạng và Backend (để thiết bị phần cứng biết cách gửi HTTP POST đến).

1. Mở file cấu hình tại: `src/config.h`
2. Cập nhật tên WiFi, mật khẩu và IP của Backend đang chạy:
   ```cpp
   #define WIFI_SSID     "Tên_WiFi_Của_Bạn"
   #define WIFI_PASSWORD "Mật_khẩu_WiFi"

   // IP máy tính chạy Backend (Bạn có thể dùng lệnh `ifconfig` trên Mac để lấy inet IP)
   #define BACKEND_IP    "192.168.1.X"
   #define BACKEND_PORT  5000
   ```
*(**Lưu ý:** Thiết bị phần cứng và laptop chạy Backend cần phải kết nối chung vào một mạng WiFi).*

---

## 🚀 Hướng dẫn Build (Biên dịch) và Nạp Code (Upload)

1. Cắm cáp USB nối từ máy tính Mac của bạn tới mạch ESP32.
2. Tại thanh công cụ phía dưới cùng của cửa sổ VSCode (thanh màu xanh / tím), bạn sẽ thấy các biểu tượng của PlatformIO. Hãy sử dụng chúng:
   
   - **Build (Dấu vết tik `✓`)**: Click vào đây để PlatformIO bắt đầu tải các thư viện cần thiết (ArduinoJson, HTTPClient, MAX30105...) và biên dịch source code sang ngôn ngữ máy. Nếu bạn thấy `SUCCESS`, code của bạn không có lỗi cú pháp.
   - **Upload (Mũi tên chỉ sang phải `→`)**: Click vào đây để nạp code thẳng vào board mạch thông qua cổng COM/Serial. Quá trình nạp sẽ mất vài giây. Nếu mạch yêu cầu, bạn có thể phải giữ nút `BOOT` trên board trong lúc quá trình `Connecting...` hiển thị trên màn hình console.
   - **Serial Monitor (Biểu tượng phích cắm điện `🔌`)**: Click vào đây để mở màn hình Terminal nhằm xem log (debug) thiết bị in ra. Tính năng này giúp bạn giám sát xem phần cứng cài đặt kết nối WiFi, Calibrate mức Ocm và việc gửi request HTTP POST thành công hay thất bại.

### Bằng dòng lệnh (Terminal)

Hoặc bạn có thể mở Terminal bên trong thư mục `hardware`, và chạy:

- Build:
  ```bash
  pio run
  ```

- Upload code cho bo mạch đang cắm:
  ```bash
  pio run -t upload
  ```

- Mở Serial Monitor:
  ```bash
  pio device monitor
  ```

Chúc bạn thuận lợi hoàn thành phần Code IoT!
