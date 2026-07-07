// =====================================================================
//  SafeWork firmware - entry point
//  Role chosen at compile time (see platformio.ini):
//     env:tag      -> ROLE_TAG      (worker helmet)
//     env:anchorN  -> ROLE_ANCHOR + ANCHOR_ID=N
// =====================================================================
#include <Arduino.h>
#include "config.h"
#include "uwb.h"

// =====================================================================
#if defined(ROLE_TAG)
// ---------------------------------------------------------------------
//  WORKER / TAG : range all anchors + read vitals + POST telemetry
// ---------------------------------------------------------------------
#include <Wire.h>
#include <WiFi.h>
#include <HTTPClient.h>
#include <SparkFun_BNO08x_Arduino_Library.h>
#include "HeartRate.h"

static BNO08x         imu;
static HeartRateStats hr;
static float    yawDeg  = 0;
static uint16_t steps   = 0;
static float    accMag  = 1.0f;         // g, simple fall/impact hint
static uint32_t lastTelemetry = 0;

// anchor id (1..N) -> backend anchor key
static const char* ANCHOR_KEYS[NUM_ANCHORS] = { "ANC_STAGE", "ANC_LEFT", "ANC_RIGHT" };

static void wifiConnect() {
    WiFi.mode(WIFI_STA);
    WiFi.begin(WIFI_SSID, WIFI_PASS);
    uint32_t t0 = millis();
    while (WiFi.status() != WL_CONNECTED && millis() - t0 < 15000) delay(200);
}

static void serviceSensors() {
    heartrate_update(hr);                       // keep BPM DSP fed

    if (imu.getSensorEvent()) {                 // BNO08x fused reports
        uint8_t id = imu.getSensorEventID();
        if (id == SENSOR_REPORTID_ROTATION_VECTOR) {
            yawDeg = imu.getYaw() * 180.0f / PI;
        } else if (id == SENSOR_REPORTID_STEP_COUNTER) {
            steps = imu.getStepCount();
        } else if (id == SENSOR_REPORTID_ACCELEROMETER) {
            float ax = imu.getAccelX(), ay = imu.getAccelY(), az = imu.getAccelZ();
            accMag = sqrtf(ax * ax + ay * ay + az * az) / 9.81f;
        }
    }
}

static void postTelemetry(double d[NUM_ANCHORS], bool ok[NUM_ANCHORS]) {
    if (WiFi.status() != WL_CONNECTED) { wifiConnect(); return; }

    String body = "{";
    body += "\"worker_id\":\"" WORKER_ID "\",";
    body += "\"telemetry\":{";
    body +=   "\"hr\":"    + String(hr.bpm);
    body +=  ",\"temp\":"  + String(hr.chipTemp, 1);   // NOTE: chip temp (no body-temp sensor yet)
    body +=  ",\"spo2\":0";
    body +=  ",\"ch4\":0,\"co\":0";                      // NOTE: no gas sensor on this build
    body +=  ",\"yaw\":"   + String(yawDeg, 1);
    body +=  ",\"steps\":" + String(steps);
    body +=  ",\"acc\":"   + String(accMag, 2);
    body += "},\"distances\":{";
    bool first = true;
    for (int i = 0; i < NUM_ANCHORS; i++) {
        if (!ok[i]) continue;
        if (!first) body += ",";
        body += "\"" + String(ANCHOR_KEYS[i]) + "\":" + String(d[i], 2);
        first = false;
    }
    body += "}}";

    HTTPClient http;
    http.begin(BACKEND_URL);
    http.addHeader("Content-Type", "application/json");
    int code = http.POST(body);
    Serial.printf("[tx] %d %s\n", code, body.c_str());
    http.end();
}

void setup() {
    Serial.begin(115200);
    uint32_t t0 = millis(); while (!Serial && millis() - t0 < 2000);

    Wire.begin(I2C_SDA, I2C_SCL);
    Wire.setClock(400000);

    if (!heartrate_begin(Wire)) Serial.println("{\"event\":\"error\",\"msg\":\"MAX30102 not found\"}");
    if (!imu.begin(BNO08X_ADDR, Wire)) {
        Serial.println("{\"event\":\"error\",\"msg\":\"BNO08x not found\"}");
    } else {
        imu.enableRotationVector(50);
        imu.enableStepCounter(200);
        imu.enableAccelerometer(50);
    }
    if (!uwb_begin()) Serial.println("{\"event\":\"error\",\"msg\":\"DW3000 init failed\"}");

    wifiConnect();
    Serial.println("{\"event\":\"ready\",\"role\":\"tag\"}");
}

void loop() {
    serviceSensors();

    if (millis() - lastTelemetry >= TELEMETRY_PERIOD_MS) {
        lastTelemetry = millis();
        double d[NUM_ANCHORS]; bool ok[NUM_ANCHORS];
        for (int i = 0; i < NUM_ANCHORS; i++) {
            ok[i] = uwb_range(i + 1, d[i]);     // anchor ids 1..N
            delay(2);
        }
        postTelemetry(d, ok);
    }
}

// =====================================================================
#elif defined(ROLE_ANCHOR)
// ---------------------------------------------------------------------
//  ANCHOR : pure UWB responder for its own ANCHOR_ID
// ---------------------------------------------------------------------
#ifndef ANCHOR_ID
#error "Define ANCHOR_ID (1,2,3...) via build_flags for the anchor build"
#endif

void setup() {
    Serial.begin(115200);
    uint32_t t0 = millis(); while (!Serial && millis() - t0 < 2000);
    if (!uwb_begin()) Serial.println("{\"event\":\"error\",\"msg\":\"DW3000 init failed\"}");
    Serial.printf("{\"event\":\"ready\",\"role\":\"anchor\",\"id\":%d}\n", ANCHOR_ID);
}

void loop() {
    uwb_responder_tick();
}

// =====================================================================
#else
#error "No role selected. Build with env:tag or env:anchorN (see platformio.ini)."
#endif
