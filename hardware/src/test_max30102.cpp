/*
 * ═══════════════════════════════════════════════════════════════
 *  TEST MAX30102 — Đọc nhịp tim (BPM) + nhiệt độ (°C)
 * ═══════════════════════════════════════════════════════════════
 *  Board: ESP32-S3
 *  Chân I2C: SDA=47, SCL=48 (giống main.cpp)
 *
 *  Cách dùng:
 *    1. Trong platformio.ini, tạm thời đổi build_src_filter:
 *       build_src_filter = +<test_max30102.cpp>
 *    2. Nạp firmware: pio run -e worker -t upload
 *    3. Mở Serial Monitor (115200 baud)
 *    4. Đặt ngón tay lên cảm biến → xem BPM + nhiệt độ
 * ═══════════════════════════════════════════════════════════════
 */

#include <Arduino.h>
#include <Wire.h>
#include "MAX30105.h"
#include "heartRate.h"

// ── CHÂN I2C (giống project chính) ──
#define I2C_SDA 47
#define I2C_SCL 48

MAX30105 sensor;

// ── BIẾN TOÀN CỤC ──
float g_bpm = 0.0f;
bool g_haveBeat = false;
uint32_t g_lastBeatMs = 0;
int beatCount = 0;

// Buffer trung bình BPM (moving average 4 mẫu)
#define BPM_AVG_SIZE 4
float bpmBuffer[BPM_AVG_SIZE] = {0};
int bpmIndex = 0;

float getAvgBpm() {
  float sum = 0;
  int count = 0;
  for (int i = 0; i < BPM_AVG_SIZE; i++) {
    if (bpmBuffer[i] > 0) { sum += bpmBuffer[i]; count++; }
  }
  return count > 0 ? sum / count : 0;
}

void setup() {
  Serial.begin(115200);
  delay(1000);

  Serial.println();
  Serial.println("╔══════════════════════════════════╗");
  Serial.println("║   TEST MAX30102 — HR + Temp      ║");
  Serial.println("╚══════════════════════════════════╝");
  Serial.println();

  // Khởi tạo I2C
  Wire.begin(I2C_SDA, I2C_SCL);
  Wire.setClock(400000);
  Serial.printf("[I2C] SDA=%d, SCL=%d, 400kHz\n", I2C_SDA, I2C_SCL);

  // Khởi tạo MAX30102
  if (!sensor.begin(Wire, I2C_SPEED_FAST)) {
    Serial.println("[MAX30102] ❌ KHÔNG TÌM THẤY CẢM BIẾN!");
    Serial.println("[MAX30102] Kiểm tra lại dây nối SDA/SCL và nguồn 3.3V");
    while (1) {
      delay(1000);
      Serial.println("... đang chờ cảm biến ...");
    }
  }

  Serial.println("[MAX30102] ✅ Cảm biến đã kết nối!");

  // Cấu hình cảm biến
  // Tham số: ledBrightness, sampleAverage, ledMode, sampleRate, pulseWidth, adcRange
  sensor.setup(
    0x1F,   // ledBrightness (0x00-0xFF) — 0x1F = vừa phải, tiết kiệm điện
    4,      // sampleAverage (1, 2, 4, 8, 16, 32)
    2,      // ledMode (1=Red only, 2=Red+IR, 3=Red+IR+Green)
    200,    // sampleRate (50, 100, 200, 400, 800, 1000, 1600, 3200)
    411,    // pulseWidth (69, 118, 215, 411) — 411 = độ phân giải cao nhất
    4096    // adcRange (2048, 4096, 8192, 16384)
  );

  // Đặt cường độ LED
  sensor.setPulseAmplitudeRed(0x1F);
  sensor.setPulseAmplitudeIR(0x1F);

  Serial.println("[MAX30102] Cấu hình hoàn tất");
  Serial.println();
  Serial.println("════════════════════════════════════════════════════");
  Serial.println("  Đặt ngón tay lên cảm biến để đo nhịp tim");
  Serial.println("  IR > 50000 = có ngón tay | IR < 50000 = không có");
  Serial.println("════════════════════════════════════════════════════");
  Serial.println();

  // Header cho Serial Plotter
  Serial.println("IR\tBPM\tAvgBPM\tTemp(C)\tBeat");
}

void loop() {
  // Đọc mẫu từ FIFO
  sensor.check();

  while (sensor.available()) {
    uint32_t irValue = sensor.getFIFOIR();
    uint32_t redValue = sensor.getFIFORed();

    // ── PHÁT HIỆN NHỊP TIM ──
    bool beatDetected = false;

    if (irValue > 50000) {
      // Có ngón tay trên cảm biến
      if (checkForBeat(irValue)) {
        uint32_t now = millis();
        if (g_lastBeatMs > 0) {
          float dt = (now - g_lastBeatMs) / 1000.0f;
          if (dt > 0.25f && dt < 2.0f) {  // 30-240 BPM range
            float instantBpm = 60.0f / dt;
            if (instantBpm >= 40.0f && instantBpm <= 180.0f) {
              // Lọc EMA
              g_bpm = g_haveBeat ? (0.8f * g_bpm + 0.2f * instantBpm) : instantBpm;
              g_haveBeat = true;
              beatDetected = true;
              beatCount++;

              // Cập nhật moving average
              bpmBuffer[bpmIndex] = g_bpm;
              bpmIndex = (bpmIndex + 1) % BPM_AVG_SIZE;
            }
          }
        }
        g_lastBeatMs = now;
      }
    } else {
      // Không có ngón tay
      g_bpm = 0;
      g_haveBeat = false;
    }

    sensor.nextSample();

    // ── IN DỮ LIỆU (mỗi 200ms) ──
    static uint32_t lastPrintMs = 0;
    uint32_t now = millis();
    if (now - lastPrintMs >= 200) {
      lastPrintMs = now;

      float avgBpm = getAvgBpm();

      if (irValue > 50000) {
        // Có ngón tay — hiển thị đầy đủ
        Serial.printf("  IR: %6lu | Red: %6lu | BPM: %5.1f | Avg: %5.1f | Beats: %d",
                      irValue, redValue, g_bpm, avgBpm, beatCount);
        if (beatDetected) Serial.print(" ♥");
        Serial.println();
      } else {
        // Không có ngón tay
        Serial.printf("  IR: %6lu | ⚠ Đặt ngón tay lên cảm biến!\n", irValue);
      }
    }
  }

  // ── ĐỌC NHIỆT ĐỘ (mỗi 2 giây) ──
  static uint32_t lastTempMs = 0;
  if (millis() - lastTempMs >= 2000) {
    lastTempMs = millis();
    float tempC = sensor.readTemperature();
    // MAX30102 đo nhiệt độ die, cần +2°C offset gần đúng cho cơ thể
    float bodyTempEst = tempC + 2.0f;

    Serial.println("  ─────────────────────────────────────────────");
    Serial.printf("  🌡️  Die Temp: %.1f°C | Body Est: %.1f°C\n", tempC, bodyTempEst);
    Serial.println("  ─────────────────────────────────────────────");
  }
}
