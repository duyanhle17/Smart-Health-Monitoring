#include <Arduino.h>
#include <SPI.h>
#include <WiFi.h>
#include <Wire.h>
#include <math.h>
#include <vector>

#include <HTTPClient.h>
#include <ArduinoJson.h>

#include "DW1000.h"
#include "DW1000Ranging.h"
#include "MAX30105.h"
#include "heartRate.h"
#include <Adafruit_MPU6050.h>
#include <Adafruit_Sensor.h>

// ── CẤU HÌNH WIFI & WEBSOCKET ──
#include "config.h"
const char *pc_ip = BACKEND_IP;
const uint16_t pc_port = BACKEND_PORT;

// SocketIO replaced by HTTPClient

// ── CẤU HÌNH CHÂN ──
#define DWM_PIN_RST 14
#define DWM_PIN_CS 10
#define DWM_PIN_IRQ 15
#define DWM_PIN_SCK 12
#define DWM_PIN_MISO 13
#define DWM_PIN_MOSI 11
#define I2C_SDA 47
#define I2C_SCL 48



// ── CẤU HÌNH UWB ──
static constexpr const char *WORKER_EUI = "87:17:5B:D5:A9:9A:E2:9E";
static constexpr uint16_t ANCHOR_SHORT_ADDR = 0x0081;
static constexpr uint16_t RANGING_RESET_PERIOD_MS = 6000;
static constexpr uint32_t ANCHOR_TIMEOUT_MS = 10000;
static constexpr float RANGE_MAX_M = 30.0f;
static constexpr float RANGE_FILTER_ALPHA = 0.20f;

MAX30105 particleSensor;
Adafruit_MPU6050 mpu;

// ── BIẾN TOÀN CỤC ──
volatile bool g_hasNewRange = false;
volatile float g_lastRangeValue = 0.0f;
volatile uint16_t g_lastRangeAddr = 0;

static float g_filteredDistance = 0.0f;
static uint32_t g_lastDistanceMs = 0;
static float g_uwb_offset = 0.0f;

static float g_bpm = 0.0f;
static bool g_haveBeat = false;
static float g_ax = 0.0f, g_ay = 0.0f, g_az = 0.0f;
static float g_gx = 0.0f, g_gy = 0.0f, g_gz = 0.0f;
static float g_accelTotal = 0.0f;
static String g_fallFlag = "SAFE";
static uint32_t g_ir = 0;
static float g_tempC = 0.0f;  
static uint32_t g_lastImuMs = 0;
static float g_yaw = 0.0f;      // Yaw (Độ)

String worker_id = "WK_UNKNOWN";
// Queue Buffer cho offline data
std::vector<String> telemetryQueue;
const size_t MAX_QUEUE_SIZE = 50;

// ==========================================
// HÀM SENSOR (UWB, MPU, MAX)
// ==========================================
static void onNewRange() {
  DW1000Device *dev = DW1000Ranging.getDistantDevice();
  if (!dev) return;
  g_lastRangeAddr = dev->getShortAddress();
  g_lastRangeValue = dev->getRange();
  g_hasNewRange = true;
}

static void updateUwb() {
  DW1000Ranging.loop();
  if (!g_hasNewRange) return;

  const uint16_t addr = g_lastRangeAddr;
  const float d = g_lastRangeValue;
  g_hasNewRange = false;

  if (isnan(d) || isinf(d) || d > RANGE_MAX_M || d < 0.0f) return;
  
  g_lastDistanceMs = millis();
  g_filteredDistance = (g_filteredDistance <= 0.0f) ? d : (RANGE_FILTER_ALPHA * d + (1.0f - RANGE_FILTER_ALPHA) * g_filteredDistance);
}

static float getCurrentDistance() {
  if (g_filteredDistance <= 0.0f || (millis() - g_lastDistanceMs > ANCHOR_TIMEOUT_MS)) return -1.0f;
  return g_filteredDistance;
}

static void updateMpu() {
  sensors_event_t a, g, temp;
  if (!mpu.getEvent(&a, &g, &temp)) return;

  g_ax = a.acceleration.x;
  g_ay = a.acceleration.y;
  g_az = a.acceleration.z;
  g_gx = g.gyro.x;
  g_gy = g.gyro.y;
  g_gz = g.gyro.z;

  g_accelTotal = sqrtf(g_ax * g_ax + g_ay * g_ay + g_az * g_az);
  if(g_accelTotal > 20.0f) g_fallFlag = "DANGER";
  else if(g_accelTotal < 3.0f) g_fallFlag = "WARNING";
  else g_fallFlag = "SAFE";

  // Tích phân Gyro Z -> Góc Yaw (độ)
  uint32_t now = millis();
  if (g_lastImuMs > 0) {
    float dt = (now - g_lastImuMs) / 1000.0f;
    g_yaw += g_gz * dt * (180.0f / PI);
  }
  g_lastImuMs = now;
}

static void updateHeartRate(uint32_t irValue) {
  if (irValue > 50000 && checkForBeat(irValue)) {
    static uint32_t lastBeatMs = 0;
    uint32_t now = millis();
    if (lastBeatMs > 0) {
      float dt = (now - lastBeatMs) / 1000.0f;
      if (dt > 0.25f && dt < 2.0f) {
        float instantBpm = 60.0f / dt;
        if (instantBpm >= 40.0f && instantBpm <= 180.0f) {
          g_bpm = g_haveBeat ? (0.8f * g_bpm + 0.2f * instantBpm) : instantBpm;
          g_haveBeat = true;
        }
      }
    }
    lastBeatMs = now;
  } else if (irValue < 50000) {
    g_bpm = 0;
    g_haveBeat = false;
  }
}

// ==========================================
// SETUP & LOOP
// ==========================================
void setup() {
  Serial.begin(115200);
  delay(1000);

  // 1. KẾT NỐI WIFI
  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
  Serial.print("\n[WIFI] Đang kết nối");
  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");
  }
  Serial.println("\n[WIFI] ✅ Đã kết nối!");

  // Lấy MAC biến thành Worker ID
  String mac = WiFi.macAddress();
  worker_id = "WK_" + mac.substring(mac.length() - 2); 
  if (mac.endsWith("18")) worker_id = "WK_102"; // Board thực tế: B8:F8:62:F5:CB:18 → Trung Nam
  Serial.printf("[INIT] Worker ID đã map: %s (MAC: %s)\n", worker_id.c_str(), mac.c_str());

  // Tương lai mở rộng: cấu hình NTP, OTA ở đây

  // 3. KHỞI TẠO CẢM BIẾN

  Wire.begin(I2C_SDA, I2C_SCL);
  Wire.setClock(400000);

  if (particleSensor.begin(Wire, I2C_SPEED_FAST)) {
    particleSensor.setup(0x1F, 4, 2, 200, 411, 4096);
    particleSensor.setPulseAmplitudeRed(0x1F);
    particleSensor.setPulseAmplitudeIR(0x1F);
  }
  if (mpu.begin()) {
    mpu.setAccelerometerRange(MPU6050_RANGE_8_G);
    mpu.setGyroRange(MPU6050_RANGE_500_DEG);
    mpu.setFilterBandwidth(MPU6050_BAND_21_HZ);
    g_lastImuMs = millis();
  }

  // 4. KHỞI TẠO UWB
  pinMode(DWM_PIN_RST, OUTPUT);
  digitalWrite(DWM_PIN_RST, LOW);
  delay(10);
  pinMode(DWM_PIN_RST, INPUT);
  delay(80);
  SPI.begin(DWM_PIN_SCK, DWM_PIN_MISO, DWM_PIN_MOSI, DWM_PIN_CS);
  DW1000Ranging.initCommunication(DWM_PIN_RST, DWM_PIN_CS, DWM_PIN_IRQ);
  DW1000Ranging.attachNewRange(onNewRange);
  DW1000Ranging.setResetPeriod(RANGING_RESET_PERIOD_MS);
  DW1000Ranging.useRangeFilter(false);
  DW1000Ranging.startAsTag((char *)WORKER_EUI, DW1000.MODE_LONGDATA_RANGE_ACCURACY, false);
  DW1000.useSmartPower(false);

  // 5. CALIBRATE 0CM
  Serial.println("\n>>> Đặt Worker sát Anchor để Calibrate 0cm trong 5s <<<");
  for (int i = 5; i > 0; i--) {
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
  Serial.printf("✅ Đã chốt mốc 0cm: %.2f m\n", g_uwb_offset);
}

void loop() {
  updateUwb();


  uint32_t now = millis();
  static uint32_t lastFastTaskMs = 0;
  static uint32_t lastTempMs = 0;
  static uint32_t lastWsSendMs = 0;

  // ĐỌC CẢM BIẾN (50Hz)
  if (now - lastFastTaskMs >= 20) {
    lastFastTaskMs = now;
    updateMpu();

    particleSensor.check();
    while (particleSensor.available()) {
      g_ir = particleSensor.getFIFOIR();
      updateHeartRate(g_ir);
      particleSensor.nextSample();
    }
  }

  // Đọc nhiệt độ (0.5Hz)
  if (now - lastTempMs >= 2000) {
    lastTempMs = now;
    float rawTemp = particleSensor.readTemperature();
    if (rawTemp > 20.0f && rawTemp < 45.0f) g_tempC = rawTemp + 2.0f; 
  }

  // BẮN DATA LÊN SERVER QUA HTTP POST (Mỗi 50ms = 20Hz)
  if (now - lastWsSendMs >= 50) {
    lastWsSendMs = now;

    float raw_d = getCurrentDistance();
    float display_dist = 0.0f;
    if (raw_d > 0.0f) {
      display_dist = raw_d - g_uwb_offset;
      if (display_dist < 0.0f) display_dist = 0.0f;
    }

    // Tự Serialize JSON bằng ArduinoJson
    JsonDocument doc;
    doc["worker_id"] = worker_id;
    
    JsonObject telemetry = doc["telemetry"].to<JsonObject>();
    telemetry["hr"] = g_bpm;
    telemetry["temp"] = g_tempC;
    telemetry["gas"] = 0.0;
    telemetry["o2"] = 20.9;
    
    // UWB Distances
    telemetry["d1"] = display_dist;
    telemetry["d2"] = 0.0;
    telemetry["d3"] = 0.0;

    // IMU Data
    telemetry["yaw"] = g_yaw;
    telemetry["ax"] = g_ax;
    telemetry["ay"] = g_ay;
    telemetry["az"] = g_az;
    telemetry["gx"] = g_gx;
    telemetry["gy"] = g_gy;
    telemetry["gz"] = g_gz;
    telemetry["fall_alert"] = g_fallFlag;

    String jsonStr;
    serializeJson(doc, jsonStr);

    // Gửi data tới backend qua HTTP POST
    if (WiFi.status() == WL_CONNECTED) {
      // 1. Nếu có queue, gửi trước (chỉ thử gửi 1-2 tin nhắn để tránh treo loop)
      if (!telemetryQueue.empty()) {
          HTTPClient httpQueue;
          String url = String("http://") + pc_ip + ":" + pc_port + "/api/device_telemetry";
          httpQueue.begin(url);
          httpQueue.addHeader("Content-Type", "application/json");
          httpQueue.setTimeout(3000);
          int queueRes = httpQueue.POST(telemetryQueue.front());
          httpQueue.end();
          
          if (queueRes > 0) {
              telemetryQueue.erase(telemetryQueue.begin());
              delay(10);
          }
      }

      // 2. Gửi data hiện tại
      HTTPClient http;
      String url = String("http://") + pc_ip + ":" + pc_port + "/api/device_telemetry";
      http.begin(url);
      http.addHeader("Content-Type", "application/json");
      http.setTimeout(3000); // Giới hạn timeout 3s để tránh kẹt nếu backend chết

      int httpResponseCode = http.POST(jsonStr);
      if (httpResponseCode > 0) {
        // Gửi thành công
      } else {
        Serial.printf("[HTTP] Error sending telemetry: %s\n", http.errorToString(httpResponseCode).c_str());
        // Lỗi, lưu vào queue
        if (telemetryQueue.size() >= MAX_QUEUE_SIZE) telemetryQueue.erase(telemetryQueue.begin());
        telemetryQueue.push_back(jsonStr);
      }
      http.end();
    } else {
      // Mất WiFi, lưu queue
      if (telemetryQueue.size() >= MAX_QUEUE_SIZE) telemetryQueue.erase(telemetryQueue.begin());
      telemetryQueue.push_back(jsonStr);
    }
  }
}

