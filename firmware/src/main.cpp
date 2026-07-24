// =====================================================================
//  SafeWork firmware - entry point
//  Role chosen at compile time (see platformio.ini):
//     env:tag      -> ROLE_TAG      (worker helmet)
//     env:anchorN  -> ROLE_ANCHOR + ANCHOR_ID=N
// =====================================================================
#include <Arduino.h>
#include "config.h"
#include "uwb.h"

// ---------------------------------------------------------------------
//  Serial bring-up, shared by both roles.
//  On the ESP32-S3 native USB (ARDUINO_USB_CDC_ON_BOOT=1) a Serial write
//  BLOCKS until a host drains it - 100 ms per call by default. With no monitor
//  attached the node therefore crawls or looks dead, and only "starts" once you
//  press RESET with the terminal already open. setTxTimeoutMs(0) makes writes
//  drop instead of block, so it behaves the same on USB and on battery.
// ---------------------------------------------------------------------
static void serialStart() {
    Serial.begin(115200);
#if ARDUINO_USB_CDC_ON_BOOT
    Serial.setTxTimeoutMs(0);
#endif
    uint32_t t0 = millis();
    while (!Serial && millis() - t0 < 1500) delay(10);
}

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
#include "BodyTemp.h"
#include "netcfg.h"

static BNO08x         imu;
static HeartRateStats hr;
static bool     imuOK  = false;
static bool     tempOK = false;
static float    yawDeg = 0;
static uint16_t steps  = 0;
static float    ax = 0, ay = 0, az = 0;   // g
static float    accMag = 1.0f;            // g, simple fall/impact hint
static uint32_t lastTelemetry = 0;
static uint32_t lastWifiTry   = 0;

// Kick off the association and return immediately - the ESP32 connects in the
// background. Blocking here would stall ranging for seconds at a time whenever
// the AP is out of reach (or the credentials are still placeholders).
static void wifiConnect() {
    WiFi.mode(WIFI_STA);
    WiFi.disconnect();
    WiFi.begin(netcfg().ssid.c_str(), netcfg().pass.c_str());
}

static void serviceSensors() {
    heartrate_update(hr);                       // keep BPM DSP fed

    // MAX30102 re-probes itself; report the transitions so a flaky joint is
    // visible in the log instead of silently reading as "no finger".
    static bool hrWas = true;
    bool hrNow = heartrate_present();
    if (hrNow != hrWas) {
        hrWas = hrNow;
        Serial.printf("{\"event\":\"info\",\"msg\":\"MAX30102 %s\"}\n", hrNow ? "online" : "lost");
    }

    if (!imuOK) return;
    for (int i = 0; i < 12 && imu.getSensorEvent(); i++) {   // drain the report queue
        switch (imu.getSensorEventID()) {
            case SENSOR_REPORTID_ROTATION_VECTOR:
                yawDeg = imu.getYaw() * 180.0f / PI;
                break;
            case SENSOR_REPORTID_STEP_COUNTER:
                steps = imu.getStepCount();
                break;
            case SENSOR_REPORTID_ACCELEROMETER:
                ax = imu.getAccelX() / 9.81f;
                ay = imu.getAccelY() / 9.81f;
                az = imu.getAccelZ() / 9.81f;
                accMag = sqrtf(ax * ax + ay * ay + az * az);
                break;
            default: break;
        }
    }
}

// Backend /api/device_telemetry reads the ranges as flat "d1".."dN" keys INSIDE
// the telemetry object (backend/app.py) - d1 = anchor 1, d2 = anchor 2. A range
// that failed this cycle is omitted so the backend keeps the last known fix
// instead of snapping the worker onto the anchor.
static void postTelemetry(double d[NUM_ANCHORS], bool ok[NUM_ANCHORS]) {
    float bodyC = 0;
    bool  haveBody = tempOK && bodytemp_read(bodyC);

    String body = "{";
    body += "\"worker_id\":\"" + netcfg().workerId + "\",";
    body += "\"telemetry\":{";
    body +=   "\"hr\":"    + String(hr.bpm);
    body +=  ",\"ir\":"    + String(hr.ir);      // 0 = cam bien chet; thap = khong co ngon tay
    body +=  ",\"temp\":"  + String(haveBody ? bodyC : hr.chipTemp, 1);
    body +=  ",\"spo2\":0";
    body +=  ",\"ch4\":0,\"co\":0";                      // NOTE: no gas sensor on this build
    body +=  ",\"yaw\":"   + String(yawDeg, 1);
    body +=  ",\"steps\":" + String(steps);
    body +=  ",\"acc\":"   + String(accMag, 2);
    body +=  ",\"ax\":"    + String(ax, 2);
    body +=  ",\"ay\":"    + String(ay, 2);
    body +=  ",\"az\":"    + String(az, 2);
    for (int i = 0; i < NUM_ANCHORS; i++) {
        if (!ok[i]) continue;
        body += ",\"d" + String(i + 1) + "\":" + String(d[i], 2);
    }
    body += "}}";

    // Always echo to serial: bring-up and antenna-delay calibration happen on the
    // monitor, long before there is a backend to talk to.
    Serial.println(body);

    if (WiFi.status() != WL_CONNECTED) {        // retry, but don't stall the loop
        if (millis() - lastWifiTry >= 10000) { lastWifiTry = millis(); wifiConnect(); }
        return;
    }

    HTTPClient http;
    http.begin(netcfg().url);
    http.addHeader("Content-Type", "application/json");
    int code = http.POST(body);
    Serial.printf("[tx] %d\n", code);
    http.end();
}

// Reset giua mot giao dich I2C (nap firmware, bam RESET) co the de slave dang
// giu SDA muc thap -> lenh dau tien sau khi boot bi NACK. Danh toi 9 xung SCL
// cho no doc not byte dang do va nha bus, roi phat STOP.
static void i2cRecover(int sda, int scl) {
    pinMode(sda, INPUT_PULLUP);
    pinMode(scl, OUTPUT_OPEN_DRAIN);
    digitalWrite(scl, HIGH);
    delayMicroseconds(5);
    for (int i = 0; i < 9 && digitalRead(sda) == LOW; i++) {
        digitalWrite(scl, LOW);  delayMicroseconds(5);
        digitalWrite(scl, HIGH); delayMicroseconds(5);
    }
    pinMode(sda, OUTPUT_OPEN_DRAIN);            // STOP: SDA len trong khi SCL cao
    digitalWrite(sda, LOW);  delayMicroseconds(5);
    digitalWrite(scl, HIGH); delayMicroseconds(5);
    digitalWrite(sda, HIGH); delayMicroseconds(5);
    pinMode(sda, INPUT); pinMode(scl, INPUT);
}

void setup() {
    serialStart();
    netcfg_begin();

    i2cRecover(I2C_SDA, I2C_SCL);
    Wire.begin(I2C_SDA, I2C_SCL);
    Wire.setClock(400000);

    if (heartrate_begin(Wire))
        Serial.printf("{\"event\":\"info\",\"msg\":\"MAX30102 ok\",\"attempts\":%d}\n", heartrate_attempts());
    else
        Serial.println("{\"event\":\"error\",\"msg\":\"MAX30102 not found - will keep retrying\"}");

    tempOK = bodytemp_begin(Wire);
    if (tempOK) Serial.printf("{\"event\":\"info\",\"msg\":\"MAX30205 at 0x%02X\"}\n", bodytemp_address());
    else        Serial.println("{\"event\":\"error\",\"msg\":\"MAX30205 not found - using chip temp\"}");

    imuOK = imu.begin(BNO08X_ADDR, Wire);
    if (!imuOK) {
        Serial.println("{\"event\":\"error\",\"msg\":\"BNO08x not found\"}");
    } else {
        imu.enableRotationVector(50);
        imu.enableStepCounter(200);
        imu.enableAccelerometer(50);
    }

    if (!uwb_begin()) Serial.println("{\"event\":\"error\",\"msg\":\"DW3000 init failed\"}");

    wifiConnect();
    Serial.printf("{\"event\":\"ready\",\"role\":\"tag\",\"anchors\":%d}\n", NUM_ANCHORS);
    Serial.println(F("go 'help' de xem lenh cau hinh WiFi/backend"));
}

void loop() {
    serviceSensors();

    if (netcfg_service(Serial)) wifiConnect();   // WiFi vua doi -> ket noi lai

    if (millis() - lastTelemetry >= TELEMETRY_PERIOD_MS) {
        lastTelemetry = millis();
        double d[NUM_ANCHORS]; bool ok[NUM_ANCHORS];
        for (int i = 0; i < NUM_ANCHORS; i++) {
            ok[i] = uwb_range(i + 1, d[i]);     // anchor ids 1..N
            // Every anchor hears every poll; the ones not addressed drop it and
            // must re-arm their receiver. Give them time before polling the next.
            delay(20);
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
    serialStart();
    if (!uwb_begin()) Serial.println("{\"event\":\"error\",\"msg\":\"DW3000 init failed\"}");
    Serial.printf("{\"event\":\"ready\",\"role\":\"anchor\",\"id\":%d}\n", ANCHOR_ID);
}

void loop() {
    static uint32_t answered = 0, lastLog = 0;

    if (uwb_responder_tick()) answered++;

    // heartbeat: an anchor has no other way to tell you it is alive and hearing
    if (millis() - lastLog >= 2000) {
        lastLog = millis();
        Serial.printf("{\"event\":\"anchor\",\"id\":%d,\"answered\":%lu}\n",
                      ANCHOR_ID, (unsigned long)answered);
    }
}

// =====================================================================
#else
#error "No role selected. Build with env:tag or env:anchorN (see platformio.ini)."
#endif
