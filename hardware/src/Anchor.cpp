/*
 * ═══════════════════════════════════════════════════════════════
 *  SafeWork – ANCHOR Node v4.0 (ESP32-S3 + DW1000)
 * ═══════════════════════════════════════════════════════════════
 *  Nhiệm vụ:
 *    1. Đo khoảng cách UWB đến Worker (Tag)
 *    2. Calibrate 0cm khi khởi động (5 giây)
 *    3. Gửi khoảng cách (d1) lên Backend qua WebSocket
 *    4. In khoảng cách ra Serial Monitor
 *    5. Gửi dữ liệu môi trường (CH4, CO) định kỳ
 *
 *  PINS:
 *    DW1000: CS=10, RST=14, IRQ=15, SCK=12, MOSI=11, MISO=13
 * ═══════════════════════════════════════════════════════════════
 */

#include <Arduino.h>
#include <SPI.h>
#include <WiFi.h>
#include "DW1000.h"
#include "DW1000Ranging.h"

// ─── WiFi & SocketIO ──────────────────────────────────────────
#include "config.h"
#include <SocketIOclient.h>
#include <ArduinoJson.h>

const char *pc_ip = BACKEND_IP;
const uint16_t pc_port = BACKEND_PORT;
SocketIOclient socketIO;
bool is_socket_connected = false;

void socketIOEvent(socketIOmessageType_t type, uint8_t * payload, size_t length) {
    switch(type) {
        case sIOtype_DISCONNECT:
            Serial.printf("[SIO] Disconnected!\n");
            is_socket_connected = false;
            break;
        case sIOtype_CONNECT:
            Serial.printf("[SIO] Connected to url: %s\n", payload);
            is_socket_connected = true;
            socketIO.send(sIOtype_CONNECT, "/");
            break;
        case sIOtype_EVENT:
            break;
        default: break;
    }
}

// ─── DW1000 Pins ──────────────────────────────────────────────
#define DW_SCK   12
#define DW_MISO  13
#define DW_MOSI  11
#define DW_CS    10
#define DW_RST   14
#define DW_IRQ   15

// ─── Anchor EUI ───────────────────────────────────────────────
// Đuôi BẮT BUỘC KHÁC với E2:9E của Worker để tránh lỗi gộp mạng
#define ANCHOR_ADDR "82:17:5B:D5:A9:9A:11:11"

// ─── Cấu hình UWB ────────────────────────────────────────────
static constexpr float RANGE_MAX_M = 30.0f;
static constexpr float RANGE_FILTER_ALPHA = 0.20f;
static constexpr uint32_t ANCHOR_TIMEOUT_MS = 10000;

// ─── Biến tracking khoảng cách ────────────────────────────────
volatile bool g_hasNewRange = false;
volatile float g_lastRangeValue = 0.0f;
volatile uint16_t g_lastRangeAddr = 0;

static float g_filteredDistance = 0.0f;
static uint32_t g_lastDistanceMs = 0;
static float g_uwb_offset = 0.0f;

// ═══════════════════════════════════════════════════════════════
//  DW1000Ranging CALLBACKS
// ═══════════════════════════════════════════════════════════════
void newRange() {
  DW1000Device* dev = DW1000Ranging.getDistantDevice();
  if (!dev) return;
  g_lastRangeAddr = dev->getShortAddress();
  g_lastRangeValue = dev->getRange();
  g_hasNewRange = true;

  // Print raw value to serial immediately to verify connection
  Serial.printf("📏 [RAW] T 0x%04X → %.2f m\n", g_lastRangeAddr, g_lastRangeValue);
}

void newDevice(DW1000Device* dev) {
  Serial.printf("🟢 [UWB] Tag kết nối: 0x%04X\n", dev->getShortAddress());
}

void inactiveDevice(DW1000Device* dev) {
  Serial.printf("🔴 [UWB] Tag mất: 0x%04X\n", dev->getShortAddress());
}

// ─── UWB Helper Functions ─────────────────────────────────────
static void updateUwb() {
  DW1000Ranging.loop();
  if (!g_hasNewRange) return;

  const float d = g_lastRangeValue;
  g_hasNewRange = false;

  if (isnan(d) || isinf(d) || d > RANGE_MAX_M) return;

  g_lastDistanceMs = millis();
  g_filteredDistance = (g_lastDistanceMs == 0)
    ? d
    : (RANGE_FILTER_ALPHA * d + (1.0f - RANGE_FILTER_ALPHA) * g_filteredDistance);
}

static float getCurrentDistance() {
  // Returns NO_LINK (-1.0f) if timeout, else returns filtered distance
  if (g_lastDistanceMs == 0 || (millis() - g_lastDistanceMs > ANCHOR_TIMEOUT_MS)) return -1.0f;
  return g_filteredDistance;
}

// ═══════════════════════════════════════════════════════════════
//  SETUP
// ═══════════════════════════════════════════════════════════════
void setup() {
  Serial.begin(115200);

  unsigned long t0 = millis();
  while (!Serial && millis() - t0 < 3000) delay(10);
  delay(1000);

  Serial.println();
  Serial.println("╔══════════════════════════════════╗");
  Serial.println("║   SafeWork ANCHOR Node v4.0      ║");
  Serial.println("║   + UWB Distance → Backend       ║");
  Serial.println("╚══════════════════════════════════╝");

  // ── 1. WiFi ────────────────────────────────────────────────
  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
  Serial.print("[WiFi] Đang kết nối " WIFI_SSID);
  t0 = millis();
  while (WiFi.status() != WL_CONNECTED && millis() - t0 < 15000) {
    delay(500);
    Serial.print(".");
  }
  if (WiFi.status() == WL_CONNECTED) {
    Serial.printf("\n[WiFi] ✅ IP: %s\n", WiFi.localIP().toString().c_str());
  } else {
    Serial.println("\n[WiFi] ⚠ Không kết nối được WiFi!");
  }

  // ── 2. SocketIO ────────────────────────────────────────────
  socketIO.begin(pc_ip, pc_port, "/socket.io/?EIO=4");
  socketIO.onEvent(socketIOEvent);
  socketIO.setReconnectInterval(5000);

  // ── 3. DW1000 – Khởi tạo UWB Anchor ───────────────────────
  Serial.println("[UWB]  Đang khởi tạo DW1000...");

  pinMode(DW_RST, OUTPUT);
  digitalWrite(DW_RST, LOW);
  delay(50);
  pinMode(DW_RST, INPUT);
  delay(200);

  SPI.begin(DW_SCK, DW_MISO, DW_MOSI, DW_CS);
  Serial.println("[UWB]  SPI OK");

  DW1000Ranging.initCommunication(DW_RST, DW_CS, DW_IRQ);
  Serial.println("[UWB]  DW1000 communication OK");

  DW1000Ranging.attachNewRange(newRange);
  DW1000Ranging.attachNewDevice(newDevice);
  DW1000Ranging.attachInactiveDevice(inactiveDevice);

  DW1000Ranging.startAsAnchor(ANCHOR_ADDR, DW1000.MODE_LONGDATA_RANGE_ACCURACY, false);
  DW1000.useSmartPower(false);
  Serial.println("[UWB]  ✅ ANCHOR đang chờ Tag...");

  // ── 4. CHỜ WORKER KẾT NỐI TRƯỚC KHI CALIBRATE ─────────────
  Serial.println("\n>>> Đang chờ Worker (Tag) kết nối...");
  Serial.println(">>> Bật Worker rồi đặt sát Anchor <<<");
  while (true) {
    updateUwb();
    if (getCurrentDistance() > 0.0f) {
      Serial.println("[UWB] ✅ Phát hiện Worker! Bắt đầu calibrate...");
      break;
    }
    // In dấu chấm mỗi giây để biết đang chờ
    static uint32_t lastDotMs = 0;
    if (millis() - lastDotMs >= 1000) {
      lastDotMs = millis();
      Serial.print(".");
    }
  }

  // ── 5. CALIBRATE 0CM ──────────────────────────────────────
  Serial.println("\n>>> Calibrate 0cm trong 5s (giữ Worker sát Anchor) <<<");
  for (int i = 5; i > 0; i--) {
    Serial.printf("  %ds...\n", i);
    uint32_t t = millis();
    while (millis() - t < 1000) updateUwb();
  }
  float sum_dist = 0;
  int sc = 0;
  for (int i = 0; i < 40; i++) {
    uint32_t t = millis();
    while (millis() - t < 50) updateUwb();
    float d = getCurrentDistance();
    if (d > 0.0f) { sum_dist += d; sc++; }
  }
  g_uwb_offset = (sc > 0) ? (sum_dist / sc) : 0.0f;
  Serial.printf("✅ Đã chốt mốc 0cm: %.2f m (%d samples)\n", g_uwb_offset, sc);

  Serial.println("════════════════════════════════════");
  Serial.println();
}

// ═══════════════════════════════════════════════════════════════
//  LOOP
// ═══════════════════════════════════════════════════════════════
void loop() {
  updateUwb();
  socketIO.loop();

  uint32_t now = millis();
  static uint32_t lastSendMs = 0;
  static uint32_t lastPrintMs = 0;
  static uint32_t lastEnvMs = 0;

  // ── IN KHOẢNG CÁCH RA SERIAL (5Hz = 200ms) ────────────────
  if (now - lastPrintMs >= 200) {
    lastPrintMs = now;
    float raw_d = getCurrentDistance();
    if (raw_d > 0.0f) {
      float calibrated = raw_d - g_uwb_offset;
      if (calibrated < 0.0f) calibrated = 0.0f;
      Serial.printf("📏 Tag 0x%04X → %.2f m (raw: %.2f, offset: %.2f)\n",
                     g_lastRangeAddr, calibrated, raw_d, g_uwb_offset);
    }
  }

  // ── GỬI KHOẢNG CÁCH LÊN BACKEND (10Hz = 100ms) ───────────
  if (now - lastSendMs >= 100) {
    lastSendMs = now;

    float raw_d = getCurrentDistance();
    float display_dist = 0.0f;
    if (raw_d > 0.0f) {
      display_dist = raw_d - g_uwb_offset;
      if (display_dist < 0.0f) display_dist = 0.0f;
    }

    if (is_socket_connected && raw_d > 0.0f) {
      JsonDocument doc;
      doc["worker_id"] = "WK_102";  // Map Worker ID (mở rộng nếu có nhiều Worker)

      JsonObject telemetry = doc["telemetry"].to<JsonObject>();
      telemetry["d1"] = display_dist;
      telemetry["d2"] = 0.0;
      telemetry["d3"] = 0.0;

      String jsonStr;
      serializeJson(doc, jsonStr);

      String sioMsg = "[\"anchor_distance\"," + jsonStr + "]";
      socketIO.sendEVENT(sioMsg);
    }
  }

  // ── GỬI MÔI TRƯỜNG (0.5Hz = 2 giây) ──────────────────────
  if (now - lastEnvMs >= 2000) {
    lastEnvMs = now;

    if (is_socket_connected) {
      JsonDocument envDoc;
      envDoc["anchor_id"] = "ANC_STAGE";

      JsonObject telem = envDoc["telemetry"].to<JsonObject>();
      telem["ch4"] = 0.0;
      telem["co"] = 0.0;

      String envStr;
      serializeJson(envDoc, envStr);

      String sioMsg = "[\"anchor_telemetry\"," + envStr + "]";
      socketIO.sendEVENT(sioMsg);
    }
  }
}