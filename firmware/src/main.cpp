#include <Arduino.h>
#include <Wire.h>
#include "HeartRate.h"
#include "Mpu.h"

#define I2C_SDA 6
#define I2C_SCL 5

static uint32_t _lastMpu = 0;
static uint32_t _lastHr  = 0;

void setup() {
    Serial.begin(115200);
    uint32_t t0 = millis();
    while (!Serial && millis() - t0 < 3000);

    Wire.begin(I2C_SDA, I2C_SCL);
    Wire.setClock(400000);

    if (!heartrate_begin(Wire)) {
        Serial.println("{\"event\":\"error\",\"msg\":\"MAX30102 not found\"}");
        while (1) delay(100);
    }
    if (!mpu_begin(Wire)) {
        Serial.println("{\"event\":\"error\",\"msg\":\"MPU6050 not found\"}");
        while (1) delay(100);
    }

    Serial.println("{\"event\":\"ready\"}");
}

void loop() {
    uint32_t now = millis();

    // ── HeartRate @ 100Hz ───────────────────────────────────
    if (now - _lastHr >= 10) {
        _lastHr = now;
        HeartRateStats hr;
        heartrate_update(hr);

        if (hr.fingerDetected && hr.isNewResult) {
            Serial.print("{\"type\":\"hr\"");
            Serial.print(",\"bpm\":");  Serial.print(hr.bpm);
            Serial.print(",\"temp\":"); Serial.print(hr.chipTemp, 2);
            Serial.print(",\"ir\":");   Serial.print(hr.ir);
            Serial.println("}");
        }
    }

    // ── IMU @ 10Hz ──────────────────────────────────────────
    if (now - _lastMpu >= 100) {
        _lastMpu = now;
        MpuData mpu;
        mpu_read(mpu);

        Serial.print("{\"type\":\"imu\"");
        Serial.print(",\"ax\":"); Serial.print(mpu.ax, 3);
        Serial.print(",\"ay\":"); Serial.print(mpu.ay, 3);
        Serial.print(",\"az\":"); Serial.print(mpu.az, 3);
        Serial.print(",\"gx\":"); Serial.print(mpu.gx, 3);
        Serial.print(",\"gy\":"); Serial.print(mpu.gy, 3);
        Serial.print(",\"gz\":"); Serial.print(mpu.gz, 3);
        Serial.print(",\"temp\":"); Serial.print(mpu.temp, 1);
        Serial.println("}");
    }
}
