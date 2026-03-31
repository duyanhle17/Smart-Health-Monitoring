/*
 * ═══════════════════════════════════════════════════════════════
 *  SafeWork – ANCHOR Node (ESP32-S3 + DW1000)
 * ═══════════════════════════════════════════════════════════════
 *  Chức năng: Trạm neo cố định, phản hồi ranging từ Worker Tag
 *  Kết nối mạng WiFi chung, chạy WebSocket Server relay data
 *
 *  PINS (giữ nguyên gốc):
 *    DW1000: CS=10, RST=9, IRQ=11, SCK=12, MOSI=13, MISO=14
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

// Cấu hình Cảm biến Môi trường
#define PIN_MQ 34
float current_ch4 = 0.5f;
float current_co = 5.0f;

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

// ─── DW1000 Pins (giống Worker) ───────────────────────────────
#define DW_SCK   12
#define DW_MISO  13
#define DW_MOSI  11
#define DW_CS    10
#define DW_RST   14
#define DW_IRQ   15

// ─── Anchor EUI ───────────────────────────────────────────────
// Phải KHÁC với Worker EUI (Worker: 87:17:5B:D5:A9:9A:E2:9E)
#define ANCHOR_ADDR "82:17:5B:D5:A9:9A:E2:9E"

// ═══════════════════════════════════════════════════════════════
//  DW1000Ranging CALLBACKS
// ═══════════════════════════════════════════════════════════════
void newRange() {
  DW1000Device* dev = DW1000Ranging.getDistantDevice();
  if (!dev) return;

  float dist = dev->getRange();
  uint16_t addr = dev->getShortAddress();
  Serial.printf("📏 [RANGE] Tag 0x%04X → %.2f m\n", addr, dist);
}

void newDevice(DW1000Device* dev) {
  Serial.printf("🟢 [UWB] Tag kết nối: 0x%04X\n", dev->getShortAddress());
}

void inactiveDevice(DW1000Device* dev) {
  Serial.printf("🔴 [UWB] Tag mất: 0x%04X\n", dev->getShortAddress());
}

// ═══════════════════════════════════════════════════════════════
//  SETUP
// ═══════════════════════════════════════════════════════════════
void setup() {
  Serial.begin(115200);

  // Chờ USB CDC sẵn sàng (ESP32-S3 cần thời gian)
  unsigned long t0 = millis();
  while (!Serial && millis() - t0 < 3000) delay(10);
  delay(1000);

  Serial.println();
  Serial.println("╔══════════════════════════════════╗");
  Serial.println("║   SafeWork ANCHOR Node v3.0      ║");
  Serial.println("╚══════════════════════════════════╝");

  // ── 1. WiFi (STA – cùng mạng Worker & PC) ────────────────
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

  // ── 1.5. SocketIO & Cảm biến ──────────────────────
  socketIO.begin(pc_ip, pc_port, "/socket.io/?EIO=4");
  socketIO.onEvent(socketIOEvent);
  socketIO.setReconnectInterval(5000);
  pinMode(PIN_MQ, INPUT);

  // ── 2. DW1000 – Khởi tạo UWB Anchor ──────────────────────
  Serial.println("[UWB]  Đang khởi tạo DW1000...");

  // Reset cứng DW1000
  pinMode(DW_RST, OUTPUT);
  digitalWrite(DW_RST, LOW);
  delay(50);          // Giữ reset lâu hơn cho ổn định
  pinMode(DW_RST, INPUT);
  delay(200);         // Chờ DW1000 boot xong

  // Khởi tạo SPI
  SPI.begin(DW_SCK, DW_MISO, DW_MOSI, DW_CS);
  Serial.println("[UWB]  SPI OK");

  // Khởi tạo DW1000Ranging
  DW1000Ranging.initCommunication(DW_RST, DW_CS, DW_IRQ);
  Serial.println("[UWB]  DW1000 communication OK");

  // Đăng ký callbacks
  DW1000Ranging.attachNewRange(newRange);
  DW1000Ranging.attachNewDevice(newDevice);
  DW1000Ranging.attachInactiveDevice(inactiveDevice);

  // Bắt đầu chế độ ANCHOR
  DW1000Ranging.startAsAnchor(ANCHOR_ADDR, DW1000.MODE_LONGDATA_RANGE_ACCURACY, false);
  Serial.println("[UWB]  ✅ ANCHOR đang chờ Tag...");

  Serial.println("════════════════════════════════════");
  Serial.println();
}

// ═══════════════════════════════════════════════════════════════
//  LOOP
// ═══════════════════════════════════════════════════════════════
void loop() {
  // UWB ranging – phải gọi liên tục
  DW1000Ranging.loop();
  
  // SocketIO
  socketIO.loop();

  // Báo cáo Môi trường định kỳ mỗi 2 giây (2000ms)
  static uint32_t lastEnvUpdateMs = 0;
  if (millis() - lastEnvUpdateMs >= 2000) {
      lastEnvUpdateMs = millis();
      
      // Đọc Gas
      int mqRaw = analogRead(PIN_MQ);
      current_ch4 = (mqRaw / 4095.0f) * 1.5f; // Random scale
      current_co = current_ch4 * 10.0f;

      if (is_socket_connected) {
          JsonDocument doc;
          doc["anchor_id"] = "ANC_STAGE";
          
          JsonObject telemetry = doc["telemetry"].to<JsonObject>();
          telemetry["ch4"] = current_ch4;
          telemetry["co"] = current_co;

          String jsonStr;
          serializeJson(doc, jsonStr);
          
          String sioMsg = "[\"anchor_telemetry\"," + jsonStr + "]";
          socketIO.sendEVENT(sioMsg);
      }
  }
}