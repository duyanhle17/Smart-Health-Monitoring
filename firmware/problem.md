# DWM3000 + ESP32-S3 — Nhật ký debug bring-up UWB

Ghi lại toàn bộ quá trình debug lỗi không giao tiếp được với module UWB, các giả
thuyết đã loại trừ, nguyên nhân gốc và cách sửa. (Cập nhật: 08/07/2026)

---

## TL;DR (kết luận cuối)
- ✅ **Phần cứng TỐT**, module còn sống: đọc thô SPI ra `DEV_ID = 0xDECA0302` **ổn định**.
- ✅ **Chân đúng (đã xác minh 2 cách):** `SCK=11, MOSI=9, MISO=12, CS=10, RST=17, IRQ=18`.
- ❌ **KHÔNG phải sụt nguồn / brownout**, KHÔNG phải chip chết, KHÔNG phải sai chân.
- 🎯 **Nguyên nhân gốc:** thư viện chạy **SPI 8 MHz** khi `dwt_initialise()`, dây dupold/breadboard **dài không tải nổi** → dữ liệu hỏng → init fail. Đọc thô ở **2 MHz** thì hoàn hảo.
- 🔧 **Sửa:** rút dây SPI thật ngắn (<5 cm) **hoặc** hạ tốc SPI của thư viện xuống 2 MHz.

---

## 1. Cấu hình
- **MCU:** ESP32-S3 dev board thường (marking `N16R8`/`R8N16` = 16 MB flash + 8 MB PSRAM). *Không* phải board 4D Systems có màn hình (dù profile PlatformIO ban đầu để `4d_systems_...`).
- **UWB:** module **Qorvo DWM3000** hàn tay lên **adapter YCHIOT (loại của DWM1000)** — footprint tương thích, hàn thay trực tiếp được.
- **Nối dây:** dây dupont / breadboard.
- **Nguồn:** 3.3V từ chân `3V3` của ESP32-S3.

## 2. Triệu chứng
`dwt_initialise()` luôn trả `ERROR`. Log SPI trong lúc init ra rác, không ổn định:
```
[SPI Debug] Read=00 00 00 00
[SPI Debug] Read=FF 88 01 00
[SPI Debug] Read=00 0C 1C 00
DEVICE ID FAILED: last read = 0
```

## 3. Các giả thuyết đã LOẠI TRỪ
| Giả thuyết | Ai đề xuất | Vì sao SAI |
|---|---|---|
| Chip chết | — | Đọc thô ra `0xDECA0302` → còn sống |
| Sụt nguồn/brownout khi `dwt_initialise` kích PLL/LDO | Gemini | Đọc DEV_ID *trước init* (gần như không rút dòng) mà vẫn ra loạn → không thể do inrush lúc init. Sau khi xác minh đọc thô ổn định thì loại hẳn |
| Tranh chấp chân với màn hình TFT | Claude | Board thực tế **không có màn hình** |
| Sai footprint DWM3000 vs DWM1000 | — | Qorvo cố ý làm tương thích chân; đọc thô OK đã chứng minh |
| Hàn nguội / dây đứt | Claude | Đọc thô ổn định 4/4 lần → kết nối vật lý tốt |

## 4. Bằng chứng QUYẾT ĐỊNH
Sketch đọc thô SPI (không dùng thư viện, **2 MHz**) với `SCK=11, MOSI=9, MISO=12, CS=10`:
```
-> Raw SPI read DEV_ID: 0xDECA0302   (ổn định 4/4 lần khởi động)
```
→ Ngay sau đó gọi `dwt_initialise()` (thư viện chuyển SPI lên tốc cao) → rác → FAIL.

**Bruteforce quét chân** (1680 tổ hợp) xác nhận lại: tổ hợp sạch = `SCK=11 MOSI=9 MISO=12 CS=10`
(vài tổ hợp khác trúng giả vì phép đọc DEV_ID dễ dãi với MOSI/CS).

## 5. Nguyên nhân gốc
Trong `lib/Dw3000/src/dw3000_port.cpp`:
```cpp
SPISettings _fastSPI = SPISettings(8000000L, MSBFIRST, SPI_MODE0);  // 8 MHz
const SPISettings _slowSPI = SPISettings(2000000L, MSBFIRST, SPI_MODE0);  // 2 MHz
const SPISettings* _currentSPI = &_fastSPI;   // <-- mặc định chạy 8 MHz
```
`dwt_initialise()` đọc/ghi thanh ghi ở **8 MHz**. Dây dupont dài + adapter → mất tính toàn vẹn tín hiệu ở 8 MHz → đọc rác. Đọc thô ở 2 MHz thì sạch → **đây là lỗi signal-integrity do tốc độ, không phải nguồn**.

## 6. CÁCH SỬA (chọn 1 hoặc cả 2)
**A. Vật lý (khuyên làm trước):** cắm module **sát** ESP32-S3, dây SPI **<5 cm** (đặc biệt SCK & MISO). Thường đủ để 8 MHz chạy.

**B. Hạ tốc SPI trong thư viện** — sửa `lib/Dw3000/src/dw3000_port.cpp`:
```cpp
// đổi 8 MHz -> 2 MHz cho chắc trên dây dupont
SPISettings _fastSPI = SPISettings(2000000L, MSBFIRST, SPI_MODE0);
```
(hoặc để `_currentSPI = &_slowSPI`.) Sau khi mạch chạy ổn có thể tăng dần lên.

## 7. Việc cần cập nhật vào code (chưa làm)
- Sửa **chân trong `config.h` + `-D` (platformio.ini)** từ `SCK=12/MOSI=11/MISO=13` (SAI) → **`SCK=11/MOSI=9/MISO=12/CS=10`** (ĐÚNG). RST=17, IRQ=18 giữ nguyên.
- Áp cách sửa mục 6.

## 8. Bài học
- Luôn tách **đọc thô ở tốc thấp** để xác minh phần cứng/chân TRƯỚC khi đổ lỗi cho nguồn.
- `0xDECA0302` ổn định = phần cứng OK; lỗi init sau đó gần như luôn là **tốc độ SPI** hoặc **cấu hình thư viện**, không phải brownout.
- Bruteforce chân là cách nhanh nhất để loại trừ giả thuyết "sai chân".
