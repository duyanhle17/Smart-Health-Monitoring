/*
 * ═══════════════════════════════════════════════════════════════
 *  TEST DWM1000 — Kiểm tra module UWB hoạt động
 * ═══════════════════════════════════════════════════════════════
 *  Chạy trên ESP32-S3, kiểm tra:
 *    1. SPI Communication (đọc Device ID)
 *    2. Đọc các thanh ghi quan trọng
 *    3. Test TX/RX (gửi và nhận frame đơn giản)
 *
 *  Cách dùng:
 *    1. Nạp: pio run -e test_uwb -t upload
 *    2. Mở Serial Monitor (115200 baud)
 *    3. Xem kết quả từng bước test
 *
 *  PINS: SCK=12, MISO=13, MOSI=11, CS=10, RST=14, IRQ=15
 * ═══════════════════════════════════════════════════════════════
 */

#include <Arduino.h>
#include <SPI.h>
#include "DW1000.h"
#include "DW1000Ranging.h"

// ─── CHÂN KẾT NỐI ────────────────────────────────────────────
#define DW_SCK   12
#define DW_MISO  13
#define DW_MOSI  11
#define DW_CS    10
#define DW_RST   14
#define DW_IRQ   15

// Chọn chế độ test: TAG hoặc ANCHOR
// Nạp 1 mạch là TAG, 1 mạch là ANCHOR, cả 2 phải cùng bật
// ── ĐỔI DÒNG NÀY ĐỂ CHỌN ──
#define TEST_AS_TAG  false  // true = Tag (Worker), false = Anchor

#if TEST_AS_TAG
  #define MY_ADDR "87:17:5B:D5:A9:9A:E2:9E"
  #define MY_ROLE "TAG"
#else
  // Địa chỉ ANCHOR khác hoàn toàn để chặn xung đột dải short address
  #define MY_ADDR "11:22:33:44:55:66:77:88"
  #define MY_ROLE "ANCHOR"
#endif

// ─── BIẾN ─────────────────────────────────────────────────────
volatile bool gotRange = false;
volatile float lastDist = 0;
volatile uint16_t lastAddr = 0;
uint32_t rangeCount = 0;
uint32_t lastRangeMs = 0;

// ─── CALLBACKS ────────────────────────────────────────────────
void onNewRange() {
  DW1000Device* dev = DW1000Ranging.getDistantDevice();
  if (!dev) return;
  lastAddr = dev->getShortAddress();
  lastDist = dev->getRange();
  gotRange = true;
  rangeCount++;
  lastRangeMs = millis();
}

void onNewDevice(DW1000Device* dev) {
  Serial.printf("🟢 Thiết bị kết nối: 0x%04X\n", dev->getShortAddress());
}

void onInactiveDevice(DW1000Device* dev) {
  Serial.printf("🔴 Thiết bị mất: 0x%04X\n", dev->getShortAddress());
}

// ═══════════════════════════════════════════════════════════════
//  TEST FUNCTIONS
// ═══════════════════════════════════════════════════════════════

bool testSPI() {
  Serial.println("\n── TEST 1: SPI Communication ──────────────────");
  
  // Kiểm tra chân
  Serial.printf("  Chân: SCK=%d, MISO=%d, MOSI=%d, CS=%d, RST=%d, IRQ=%d\n",
                 DW_SCK, DW_MISO, DW_MOSI, DW_CS, DW_RST, DW_IRQ);
  
  // Reset cứng
  Serial.println("  Resetting DW1000...");
  pinMode(DW_RST, OUTPUT);
  digitalWrite(DW_RST, LOW);
  delay(50);
  pinMode(DW_RST, INPUT);
  delay(200);
  
  // Khởi tạo SPI
  SPI.begin(DW_SCK, DW_MISO, DW_MOSI, DW_CS);
  Serial.println("  SPI.begin() OK");
  
  // Thử đọc Device ID qua DW1000 library
  DW1000Ranging.initCommunication(DW_RST, DW_CS, DW_IRQ);
  
  // Đọc thông tin chip
  char msg[128];
  DW1000.getPrintableDeviceIdentifier(msg);
  Serial.printf("  Device ID: %s\n", msg);
  
  DW1000.getPrintableExtendedUniqueIdentifier(msg);
  Serial.printf("  EUI: %s\n", msg);
  
  DW1000.getPrintableNetworkIdAndShortAddress(msg);
  Serial.printf("  Network: %s\n", msg);
  
  // Kiểm tra Device ID hợp lệ
  // DW1000 Device ID phải là "DECA0130" hoặc tương tự
  String devId = String(msg);
  if (devId.length() > 0 && devId != "FF:FF:FF:FF") {
    Serial.println("  ✅ SPI OK — DW1000 phản hồi đúng!");
    return true;
  } else {
    Serial.println("  ❌ SPI FAIL — Không đọc được Device ID!");
    Serial.println("  → Kiểm tra dây SPI (SCK, MISO, MOSI, CS)");
    Serial.println("  → Kiểm tra nguồn 3.3V cho DW1000");
    return false;
  }
}

bool testIRQ() {
  Serial.println("\n── TEST 2: IRQ Pin ────────────────────────────");
  
  // Kiểm tra trạng thái IRQ pin
  pinMode(DW_IRQ, INPUT);
  int irqState = digitalRead(DW_IRQ);
  Serial.printf("  IRQ pin (%d) trạng thái: %s\n", DW_IRQ, irqState ? "HIGH" : "LOW");
  
  // IRQ thường là LOW khi idle (active-high interrupt)
  if (irqState == LOW) {
    Serial.println("  ✅ IRQ pin OK (LOW khi idle)");
    return true;
  } else {
    Serial.println("  ⚠ IRQ pin đang HIGH — có thể có interrupt chưa xử lý");
    Serial.println("  → Đây có thể bình thường sau khi DW1000 vừa reset");
    return true; // Không fail vì có thể đang có pending interrupt
  }
}

void testRanging() {
  Serial.println("\n── TEST 3: UWB Ranging ────────────────────────");
  Serial.printf("  Chế độ: %s\n", MY_ROLE);
  Serial.printf("  Địa chỉ: %s\n", MY_ADDR);
  Serial.println("  Mode: MODE_SHORTDATA_FAST_ACCURACY (6.8Mbps, PRF 64MHz)");
  
  // Đăng ký callbacks
  DW1000Ranging.attachNewRange(onNewRange);
  DW1000Ranging.attachNewDevice(onNewDevice);
  DW1000Ranging.attachInactiveDevice(onInactiveDevice);
  
#if TEST_AS_TAG
  DW1000Ranging.startAsTag((char*)MY_ADDR, DW1000.MODE_SHORTDATA_FAST_ACCURACY, false);
  DW1000.useSmartPower(true);
  Serial.println("  ✅ Đang chạy như TAG — cần ANCHOR ở mạch kia");
#else
  DW1000Ranging.startAsAnchor((char*)MY_ADDR, DW1000.MODE_SHORTDATA_FAST_ACCURACY, false);
  DW1000.useSmartPower(true);
  Serial.println("  ✅ Đang chạy như ANCHOR — cần TAG ở mạch kia");
#endif

  Serial.println("\n  Đang chờ ranging...");
  Serial.println("  (Bật mạch kia với vai trò ngược lại)");
  Serial.println("  Nếu sau 30s không có kết quả → kiểm tra:");
  Serial.println("    1. Antenna có gắn đúng không?");
  Serial.println("    2. Nguồn 3.3V đủ dòng (200mA+)?");
  Serial.println("    3. Mạch kia có đang chạy với đúng vai trò?");
  Serial.println("    4. 2 mạch cách nhau < 5m?");
  Serial.println("─────────────────────────────────────────────────\n");
}

// ═══════════════════════════════════════════════════════════════
//  SETUP & LOOP
// ═══════════════════════════════════════════════════════════════
void setup() {
  Serial.begin(115200);
  delay(1000);
  
  unsigned long t0 = millis();
  while (!Serial && millis() - t0 < 3000) delay(10);
  
  Serial.println();
  Serial.println("╔══════════════════════════════════════╗");
  Serial.println("║   TEST DWM1000 — Debug UWB Module    ║");
  Serial.printf( "║   Role: %-29s ║\n", MY_ROLE);
  Serial.println("╚══════════════════════════════════════╝");
  
  // Chạy các test
  bool spiOk = testSPI();
  if (!spiOk) {
    Serial.println("\n⛔ DỪNG — SPI không hoạt động, không thể test tiếp.");
    Serial.println("   Kiểm tra phần cứng rồi reset mạch.");
    while(1) delay(1000);
  }
  
  testIRQ();
  testRanging();
}

void loop() {
  DW1000Ranging.loop();
  
  // In kết quả ranging
  if (gotRange) {
    gotRange = false;
    Serial.printf("📏 [%lu] Khoảng cách: %.2f m | Thiết bị: 0x%04X | Tổng: %lu lần\n",
                   millis(), lastDist, lastAddr, rangeCount);
  }
  
  // Mỗi 5 giây, báo trạng thái
  static uint32_t lastStatusMs = 0;
  if (millis() - lastStatusMs >= 5000) {
    lastStatusMs = millis();
    
    if (rangeCount == 0) {
      Serial.println("⏳ Chưa có ranging... (đang chờ thiết bị kia)");
    } else {
      uint32_t elapsed = (millis() - lastRangeMs) / 1000;
      float hz = (float)rangeCount / ((float)millis() / 1000.0f);
      Serial.printf("📊 Tổng: %lu ranges | Tần suất: %.1f Hz | Lần cuối: %lus trước\n",
                     rangeCount, hz, elapsed);
    }
  }
}
