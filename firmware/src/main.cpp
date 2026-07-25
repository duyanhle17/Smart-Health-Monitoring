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
#include <WiFiClientSecure.h>
#include <HTTPClient.h>
#include <SparkFun_BNO08x_Arduino_Library.h>
#include "HeartRate.h"
#include "BodyTemp.h"
#include "netcfg.h"
#include "wifi_portal.h"

static BNO08x         imu;
static HeartRateStats hr;
static bool     imuOK  = false;
static bool     tempOK = false;
static uint8_t  imuAddr = 0;
static float    yawDeg = 0;
static uint16_t steps  = 0;
static float    ax = 0, ay = 0, az = 0;   // g
static float    accMag = 1.0f;            // g, simple fall/impact hint
static uint32_t lastTelemetry = 0;
static uint32_t lastWifiTry   = 0;
static uint32_t wifiAssociationStartedAt = 0;
static constexpr uint32_t WIFI_PORTAL_FALLBACK_MS = 15000;
// MAX30205 can NACK briefly on the currently marginal shared bus. Preserve a
// recent verified body-temperature sample rather than publishing a false 0.0.
// `temp_fresh` and `temp_age_ms` make the fallback explicit to the backend.
static constexpr uint32_t BODY_TEMP_CACHE_MS = 10000;
static float    lastBodyTempC = 0.0f;
static uint32_t lastBodyTempAt = 0;
static bool     haveBodyTempCache = false;

// Kick off the association and return immediately - the ESP32 connects in the
// background. Blocking here would stall ranging for seconds at a time whenever
// the AP is out of reach (or the credentials are still placeholders).
static void wifiConnect() {
    if (!netcfg_has_wifi()) {
        wifiAssociationStartedAt = 0;
        wifi_portal_start();
        return;
    }
    if (!wifiAssociationStartedAt) wifiAssociationStartedAt = millis();
    WiFi.mode(wifi_portal_active() ? WIFI_AP_STA : WIFI_STA);
    WiFi.disconnect(false, false);
    WiFi.begin(netcfg().ssid.c_str(), netcfg().pass.c_str());
    lastWifiTry = millis();
    Serial.printf("{\"event\":\"wifi\",\"state\":\"connecting\",\"ssid\":\"%s\"}\n",
                  netcfg().ssid.c_str());
}

static void enableImuReports() {
    imu.enableRotationVector(50);
    imu.enableStepCounter(200);
    imu.enableAccelerometer(50);
}

// MAX30205 can also be strapped to 0x4A/0x4B, so an ACK alone at the alternate
// address does not identify a BNO08x. Use the explicit board configuration;
// this avoids poisoning the BNO library's single global SHTP transport after a
// failed handshake against a different I2C device.
static bool beginImu() {
    imuAddr = BNO08X_ADDR;
    if (!imu.begin(imuAddr, Wire)) { imuAddr = 0; return false; }
    enableImuReports();
    Serial.printf("{\"event\":\"info\",\"msg\":\"BNO08x at 0x%02X\"}\n", imuAddr);
    return true;
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

    // A BNO08x reset loses its enabled report list. Re-enable it in place;
    // this is independent of the DW3000 SPI radio.
    if (imu.wasReset()) enableImuReports();
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
    bool  haveFreshBody = tempOK && bodytemp_read(bodyC);
    uint32_t now = millis();
    if (haveFreshBody) {
        lastBodyTempC = bodyC;
        lastBodyTempAt = now;
        haveBodyTempCache = true;
    }
    uint32_t bodyAge = haveBodyTempCache ? now - lastBodyTempAt : UINT32_MAX;
    bool haveCachedBody = !haveFreshBody && bodyAge <= BODY_TEMP_CACHE_MS;
    bool haveBody = haveFreshBody || haveCachedBody;
    // The MAX30102 die reading is not body temperature. Only use it for old
    // deployments that have no MAX30205 at all, and label its source clearly.
    bool haveChipFallback = !tempOK && hr.chipTemp > 0.0f;

    String body = "{";
    body += "\"worker_id\":\"" + netcfg().workerId + "\",";
    body += "\"telemetry\":{";
    body +=   "\"hr\":"    + String(hr.bpm);
    body +=  ",\"ir\":"    + String(hr.ir);      // 0 = cam bien chet; thap = khong co ngon tay
    if (haveBody) {
        body += ",\"temp\":" + String(lastBodyTempC, 1);
        body += ",\"temp_source\":\"max30205\"";
    } else if (haveChipFallback) {
        body += ",\"temp\":" + String(hr.chipTemp, 1);
        body += ",\"temp_source\":\"max30102_chip\"";
    } else {
        // Omit `temp` rather than overwriting the dashboard with a false 0.0.
        body += ",\"temp_source\":\"unavailable\"";
    }
    body +=  ",\"temp_fresh\":" + String(haveFreshBody ? "true" : "false");
    body +=  ",\"temp_age_ms\":";
    body += haveBody ? String(bodyAge) : String(-1);
    body +=  ",\"imu_ok\":" + String(imuOK ? "true" : "false");
    if (imuAddr) body += ",\"imu_addr\":" + String(imuAddr);
    // This board has no calibrated SpO2 or gas module. Declare absence rather
    // than sending zeros, which a server could misread as an actual safe value.
    body +=  ",\"spo2_available\":false";
    body +=  ",\"gas_available\":false";
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
        if (!netcfg_has_wifi()) wifi_portal_start();
        else if (millis() - lastWifiTry >= 10000) wifiConnect();
        return;
    }

    if (!netcfg_has_backend_url()) {
        Serial.println("{\"event\":\"error\",\"msg\":\"Invalid backend URL; open Wi-Fi setup portal\"}");
        wifi_portal_start();
        return;
    }

    HTTPClient http;
    WiFiClient plainClient;
    WiFiClientSecure secureClient;
    const String &url = netcfg().url;
    bool begun = false;
    if (url.startsWith("https://")) {
        // The public endpoint is behind Cloudflare. A CA bundle is not stored
        // on this small firmware image, so use TLS encryption without CA
        // verification for provisioning/demo deployments. Prefer a LAN URL or
        // certificate pinning before using this on an untrusted network.
        secureClient.setInsecure();
        begun = http.begin(secureClient, url);
    } else {
        begun = http.begin(plainClient, url);
    }
    if (!begun) {
        Serial.println("{\"event\":\"error\",\"msg\":\"Could not open backend connection\"}");
        return;
    }
    http.setConnectTimeout(2500);
    http.setTimeout(2500);
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
    wifi_portal_begin();

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

    delay(250); // let the IMU finish booting after a shared-rail reset
    imuOK = beginImu();
    if (!imuOK) {
        Serial.println("{\"event\":\"error\",\"msg\":\"BNO08x not found\"}");
    }

    if (!uwb_begin()) Serial.println("{\"event\":\"error\",\"msg\":\"DW3000 init failed\"}");

    wifiConnect();
    Serial.printf("{\"event\":\"ready\",\"role\":\"tag\",\"anchors\":%d}\n", NUM_ANCHORS);
    Serial.println(F("go 'help' de xem lenh cau hinh WiFi/backend"));
}

void loop() {
    // During initial provisioning, the AP and its DNS/HTTP portal take
    // precedence over ranging. The old loop spent nearly all of its time
    // servicing UWB/I2C even though no telemetry could be transmitted yet;
    // browsers then waited several seconds for the configuration form.
    wifi_portal_service();
    if (netcfg_service(Serial) || wifi_portal_take_reconnect_request()) {
        // A saved form or serial Wi-Fi command begins a new association window.
        wifiAssociationStartedAt = 0;
        wifiConnect();                            // WiFi vua doi -> ket noi lai
    }
    if (WiFi.status() == WL_CONNECTED) {
        wifiAssociationStartedAt = 0;
    } else if (netcfg_has_wifi() && wifiAssociationStartedAt &&
               millis() - wifiAssociationStartedAt >= WIFI_PORTAL_FALLBACK_MS) {
        // A stored but incorrect/out-of-range SSID must not lock the operator
        // out of the configuration page after a reboot, or keep a visible AP
        // sharing the radio with a futile station reconnect.
        Serial.println("{\"event\":\"wifi_portal\",\"reason\":\"station_timeout\"}");
        wifiAssociationStartedAt = 0;
        wifi_portal_start();
    }
    // Configuration must stay responsive even during the short overlap where
    // the SoftAP is still open and the station has already associated. HTTPS
    // POST retries and UWB ranging can otherwise monopolize the loop for
    // seconds between portal requests.
    if (wifi_portal_active()) {
        delay(1);
        return;
    }

    serviceSensors();

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
