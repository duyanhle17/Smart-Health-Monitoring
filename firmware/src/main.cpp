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
//  press RESET with the terminal already open. Do not use a zero timeout here:
//  the ESP32-S3 HWCDC core decrements a zero retry counter after a terminal
//  closes, wrapping it and waiting forever. A 1 ms timeout drops the
//  diagnostic write promptly and marks the stale CDC connection disconnected.
// ---------------------------------------------------------------------
static void serialStart() {
    Serial.begin(115200);
#if ARDUINO_USB_CDC_ON_BOOT
    Serial.setTxTimeoutMs(1);
#endif
    uint32_t t0 = millis();
    while (!Serial && millis() - t0 < 1500) delay(10);
}

// Native USB CDC can remain logically connected while the host is no longer
// draining its endpoint. Never let diagnostic output participate in the live
// telemetry path: real packets must continue to the backend with no monitor
// attached. UART builds keep their normal serial logging behaviour.
static bool serialLogAvailable() {
#if ARDUINO_USB_CDC_ON_BOOT
    return static_cast<bool>(Serial);
#else
    return true;
#endif
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
#include <freertos/FreeRTOS.h>
#include <freertos/queue.h>
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
static float    gx = 0, gy = 0, gz = 0;   // rad/s, calibrated BNO08x gyro
static float    linAx = 0, linAy = 0, linAz = 0; // m/s², gravity removed
static float    linAccMag = 0;
static float    yawAccuracyRad = 0;
static uint8_t  yawAccuracy = 0;
static uint8_t  gyroAccuracy = 0;
static uint8_t  stability = 0;            // BNO: 1=on-table, 2=stationary, 4=motion
static uint32_t lastImuAt = 0;
static uint32_t lastTelemetry = 0;
static uint32_t lastUwbSample = 0;
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
// A valid response can be lost to a short RF collision/NLOS fade. The UWB
// frame now verifies anchor ID + poll sequence, so retrying is safe and avoids
// turning one missed 5ms receive window into a missing d1/d2 telemetry packet.
static constexpr uint8_t UWB_RANGE_ATTEMPTS = 3;

// The UWB sampler runs in the Arduino loop; only HTTPS runs in a low-priority
// task. A one-slot queue intentionally coalesces old packets while Cloudflare
// is slow: the server receives the newest *measured* d1+d2 pair, never a
// backlog of stale coordinates.
struct TelemetrySnapshot {
    char workerId[40]{};
    double d[NUM_ANCHORS]{};
    bool rangeOk[NUM_ANCHORS]{};
    uint32_t rangeSeq = 0;
    uint32_t rangeAgeMs = 0;
    int bpm = 0;
    uint32_t ir = 0;
    bool hasBodyTemp = false;
    bool bodyTempFresh = false;
    float bodyTempC = 0;
    uint32_t bodyTempAgeMs = UINT32_MAX;
    bool hasChipTemp = false;
    float chipTempC = 0;
    bool imuOk = false;
    uint8_t imuAddress = 0;
    float yaw = 0;
    uint16_t stepCount = 0;
    float acceleration = 0;
    float accelX = 0, accelY = 0, accelZ = 0;
    float gyroX = 0, gyroY = 0, gyroZ = 0;
    float linearAcceleration = 0;
    float linearAccelX = 0, linearAccelY = 0, linearAccelZ = 0;
    uint8_t stability = 0;
    uint8_t yawAccuracy = 0;
    uint8_t gyroAccuracy = 0;
    float yawAccuracyRad = 0;
    uint32_t imuAgeMs = UINT32_MAX;
};

static QueueHandle_t telemetryQueue = nullptr;
static double latestRanges[NUM_ANCHORS]{};
static bool latestRangeOk[NUM_ANCHORS]{};
static uint32_t latestRangeAt = 0;
static uint32_t latestRangeSeq = 0;
static bool haveRangeSample = false;

// Keep the TCP/TLS session open across telemetry posts. Recreating a secure
// client for every packet was the main cause of the observed 1.2 s cadence.
static HTTPClient telemetryHttp;
static WiFiClient telemetryPlainClient;
static WiFiClientSecure telemetrySecureClient;
static String telemetryHttpUrl;
static bool telemetryHttpReady = false;
static bool telemetryHttpSecure = false;

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
    if (serialLogAvailable()) {
        Serial.printf("{\"event\":\"wifi\",\"state\":\"connecting\",\"ssid\":\"%s\"}\n",
                      netcfg().ssid.c_str());
    }
}

static void enableImuReports() {
    // BNO08x does the fusion on-sensor. We use its gyro/linear-acceleration
    // only to assess UWB confidence and stationary periods; no raw-accel
    // double integration is used as a position source.
    imu.enableRotationVector(25);
    imu.enableStepCounter(100);
    imu.enableAccelerometer(50);
    imu.enableGyro(25);
    imu.enableLinearAccelerometer(25);
    imu.enableStabilityClassifier(100);
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
    const uint32_t drainStartedAt = micros();
    for (int i = 0;
         i < 20 && (micros() - drainStartedAt) < 4000 && imu.getSensorEvent();
         i++) {   // drain queue, but never starve the UWB sampler
        lastImuAt = millis();
        switch (imu.getSensorEventID()) {
            case SENSOR_REPORTID_ROTATION_VECTOR:
                yawDeg = imu.getYaw() * 180.0f / PI;
                // SparkFun 1.0.6 exposes the current decoded SH2 report
                // publicly. Its legacy get*Accuracy fields are not updated
                // for every report, so take the documented low two status
                // bits directly (0=unreliable … 3=high confidence).
                yawAccuracy = imu.sensorValue.status & 0x03;
                yawAccuracyRad = imu.getQuatRadianAccuracy();
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
            case SENSOR_REPORTID_GYROSCOPE_CALIBRATED:
                gx = imu.getGyroX();
                gy = imu.getGyroY();
                gz = imu.getGyroZ();
                gyroAccuracy = imu.sensorValue.status & 0x03;
                break;
            case SENSOR_REPORTID_LINEAR_ACCELERATION:
                linAx = imu.getLinAccelX();
                linAy = imu.getLinAccelY();
                linAz = imu.getLinAccelZ();
                linAccMag = sqrtf(linAx * linAx + linAy * linAy + linAz * linAz);
                break;
            case SENSOR_REPORTID_STABILITY_CLASSIFIER:
                stability = imu.getStabilityClassifier();
                break;
            default: break;
        }
    }
}

// Backend /api/device_telemetry reads the ranges as flat "d1".."dN" keys INSIDE
// the telemetry object (backend/app.py). Snapshot I2C/BNO data on the Arduino
// loop, then let the network task construct/send JSON. This keeps Wire and the
// DW3000 SPI transaction in one deterministic task.
static bool postTelemetry(const TelemetrySnapshot &snapshot);

static void queueTelemetrySnapshot() {
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

    TelemetrySnapshot snapshot{};
    netcfg().workerId.toCharArray(snapshot.workerId, sizeof(snapshot.workerId));
    for (int i = 0; i < NUM_ANCHORS; ++i) {
        snapshot.d[i] = latestRanges[i];
        snapshot.rangeOk[i] = latestRangeOk[i];
    }
    snapshot.rangeSeq = latestRangeSeq;
    snapshot.rangeAgeMs = haveRangeSample ? now - latestRangeAt : UINT32_MAX;
    snapshot.bpm = hr.bpm;
    snapshot.ir = hr.ir;
    snapshot.hasBodyTemp = haveBody;
    snapshot.bodyTempFresh = haveFreshBody;
    snapshot.bodyTempC = lastBodyTempC;
    snapshot.bodyTempAgeMs = bodyAge;
    snapshot.hasChipTemp = haveChipFallback;
    snapshot.chipTempC = hr.chipTemp;
    snapshot.imuOk = imuOK;
    snapshot.imuAddress = imuAddr;
    snapshot.yaw = yawDeg;
    snapshot.stepCount = steps;
    snapshot.acceleration = accMag;
    snapshot.accelX = ax; snapshot.accelY = ay; snapshot.accelZ = az;
    snapshot.gyroX = gx; snapshot.gyroY = gy; snapshot.gyroZ = gz;
    snapshot.linearAcceleration = linAccMag;
    snapshot.linearAccelX = linAx; snapshot.linearAccelY = linAy; snapshot.linearAccelZ = linAz;
    snapshot.stability = stability;
    snapshot.yawAccuracy = yawAccuracy;
    snapshot.gyroAccuracy = gyroAccuracy;
    snapshot.yawAccuracyRad = yawAccuracyRad;
    snapshot.imuAgeMs = lastImuAt ? now - lastImuAt : UINT32_MAX;
    if (telemetryQueue) xQueueOverwrite(telemetryQueue, &snapshot);
    else postTelemetry(snapshot); // safe fallback if FreeRTOS allocation failed
}

static void resetTelemetryTransport() {
    telemetryHttp.end();
    telemetryPlainClient.stop();
    telemetrySecureClient.stop();
    telemetryHttpUrl = "";
    telemetryHttpReady = false;
    telemetryHttpSecure = false;
}

static bool ensureTelemetryTransport(const String &url) {
    const bool useTls = url.startsWith("https://");
    if (telemetryHttpReady && telemetryHttpUrl == url && telemetryHttpSecure == useTls) return true;

    resetTelemetryTransport();
    bool begun = false;
    if (useTls) {
        // The public endpoint is behind Cloudflare. A CA bundle is not stored
        // on this image, so transport encryption is used without CA validation.
        telemetrySecureClient.setInsecure();
        begun = telemetryHttp.begin(telemetrySecureClient, url);
    } else {
        begun = telemetryHttp.begin(telemetryPlainClient, url);
    }
    if (!begun) return false;
    telemetryHttp.setReuse(true);
    telemetryHttp.setConnectTimeout(1200);
    telemetryHttp.setTimeout(1200);
    telemetryHttp.addHeader("Content-Type", "application/json");
    telemetryHttpUrl = url;
    telemetryHttpSecure = useTls;
    telemetryHttpReady = true;
    return true;
}

static bool postTelemetry(const TelemetrySnapshot &snapshot) {
    if (WiFi.status() != WL_CONNECTED || !netcfg_has_backend_url()) return false;
    const String url = netcfg().url;
    if (!ensureTelemetryTransport(url)) return false;

    String body = "{";
    body.reserve(720);
    body += "\"worker_id\":\"" + String(snapshot.workerId) + "\",";
    body += "\"telemetry\":{";
    body +=   "\"hr\":"    + String(snapshot.bpm);
    body +=  ",\"ir\":"    + String(snapshot.ir);
    if (snapshot.hasBodyTemp) {
        body += ",\"temp\":" + String(snapshot.bodyTempC, 1);
        body += ",\"temp_source\":\"max30205\"";
    } else if (snapshot.hasChipTemp) {
        body += ",\"temp\":" + String(snapshot.chipTempC, 1);
        body += ",\"temp_source\":\"max30102_chip\"";
    } else {
        // Omit `temp` rather than overwriting the dashboard with a false 0.0.
        body += ",\"temp_source\":\"unavailable\"";
    }
    body +=  ",\"temp_fresh\":" + String(snapshot.bodyTempFresh ? "true" : "false");
    body +=  ",\"temp_age_ms\":";
    body += snapshot.hasBodyTemp ? String(snapshot.bodyTempAgeMs) : String(-1);
    body +=  ",\"imu_ok\":" + String(snapshot.imuOk ? "true" : "false");
    if (snapshot.imuAddress) body += ",\"imu_addr\":" + String(snapshot.imuAddress);
    // This board has no calibrated SpO2 or gas module. Declare absence rather
    // than sending zeros, which a server could misread as an actual safe value.
    body +=  ",\"spo2_available\":false";
    body +=  ",\"gas_available\":false";
    body +=  ",\"yaw\":"   + String(snapshot.yaw, 1);
    body +=  ",\"yaw_accuracy\":" + String(snapshot.yawAccuracy);
    body +=  ",\"yaw_accuracy_rad\":" + String(snapshot.yawAccuracyRad, 3);
    body +=  ",\"gyro_accuracy\":" + String(snapshot.gyroAccuracy);
    body +=  ",\"steps\":" + String(snapshot.stepCount);
    body +=  ",\"acc\":"   + String(snapshot.acceleration, 2);
    body +=  ",\"ax\":"    + String(snapshot.accelX, 2);
    body +=  ",\"ay\":"    + String(snapshot.accelY, 2);
    body +=  ",\"az\":"    + String(snapshot.accelZ, 2);
    body +=  ",\"gx\":"    + String(snapshot.gyroX, 3);
    body +=  ",\"gy\":"    + String(snapshot.gyroY, 3);
    body +=  ",\"gz\":"    + String(snapshot.gyroZ, 3);
    body +=  ",\"lin_acc\":" + String(snapshot.linearAcceleration, 3);
    body +=  ",\"lin_ax\":" + String(snapshot.linearAccelX, 3);
    body +=  ",\"lin_ay\":" + String(snapshot.linearAccelY, 3);
    body +=  ",\"lin_az\":" + String(snapshot.linearAccelZ, 3);
    body +=  ",\"imu_stability\":" + String(snapshot.stability);
    body +=  ",\"imu_age_ms\":" + String(snapshot.imuAgeMs == UINT32_MAX ? -1 : static_cast<int32_t>(snapshot.imuAgeMs));
    body +=  ",\"range_seq\":" + String(snapshot.rangeSeq);
    body +=  ",\"range_age_ms\":" + String(snapshot.rangeAgeMs == UINT32_MAX ? -1 : static_cast<int32_t>(snapshot.rangeAgeMs));
    for (int i = 0; i < NUM_ANCHORS; i++) {
        if (!snapshot.rangeOk[i]) continue;
        // Preserve millimetre-level ToF information for the backend median;
        // quantising every sample to 1 cm made small motions look like steps.
        body += ",\"d" + String(i + 1) + "\":" + String(snapshot.d[i], 3);
    }
    body += "}}";
    int code = telemetryHttp.POST(body);
    if (code < 200 || code >= 300) {
        resetTelemetryTransport();
        return false;
    }
    return true;
}

static void telemetryTask(void *) {
    TelemetrySnapshot snapshot{};
    while (true) {
        if (!telemetryQueue || WiFi.status() != WL_CONNECTED || !netcfg_has_backend_url()) {
            vTaskDelay(pdMS_TO_TICKS(40));
            continue;
        }
        if (xQueueReceive(telemetryQueue, &snapshot, pdMS_TO_TICKS(80)) == pdTRUE) {
            postTelemetry(snapshot);
        }
    }
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

    telemetryQueue = xQueueCreate(1, sizeof(TelemetrySnapshot));
    if (telemetryQueue) {
        BaseType_t started = xTaskCreatePinnedToCore(
            telemetryTask, "safework_tx", 8192, nullptr, 1, nullptr, 0);
        if (started != pdPASS) {
            vQueueDelete(telemetryQueue);
            telemetryQueue = nullptr;
            Serial.println("{\"event\":\"error\",\"msg\":\"telemetry task unavailable; using loop fallback\"}");
        }
    } else {
        Serial.println("{\"event\":\"error\",\"msg\":\"telemetry queue unavailable; using loop fallback\"}");
    }

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

    if (millis() - lastUwbSample >= UWB_SAMPLE_PERIOD_MS) {
        lastUwbSample = millis();
        for (int i = 0; i < NUM_ANCHORS; i++) {
            latestRangeOk[i] = false;
            for (uint8_t attempt = 0; attempt < UWB_RANGE_ATTEMPTS && !latestRangeOk[i]; attempt++) {
                latestRangeOk[i] = uwb_range(i + 1, latestRanges[i]); // anchor ids 1..N
                if (!latestRangeOk[i]) delay(5);
            }
            // Every anchor hears every poll; the ones not addressed drop it and
            // must re-arm their receiver. Recovery is now bounded in uwb.cpp,
            // so 8 ms is sufficient and avoids wasting 40 ms per pair.
            delay(UWB_INTER_ANCHOR_GUARD_MS);
        }
        latestRangeAt = millis();
        latestRangeSeq++;
        haveRangeSample = true;
    }

    if (haveRangeSample && millis() - lastTelemetry >= TELEMETRY_PERIOD_MS) {
        lastTelemetry = millis();
        queueTelemetrySnapshot();
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
        // Native USB CDC may remain electrically attached after a terminal
        // closes while no host drains its endpoint.  Never let the optional
        // heartbeat block the responder's radio loop in that state.
        if (serialLogAvailable()) {
            const UwbResponderStats &s = uwb_responder_stats();
            Serial.printf("{\"event\":\"anchor\",\"id\":%d,\"answered\":%lu,"
                          "\"rx_good\":%lu,\"addressed\":%lu,\"ignored\":%lu,"
                          "\"rx_timeout\":%lu,\"rx_error\":%lu,\"rx_watchdog\":%lu,"
                          "\"tx_start_error\":%lu,\"tx_watchdog\":%lu,\"recoveries\":%lu}\n",
                          ANCHOR_ID, (unsigned long)answered,
                          (unsigned long)s.rx_good, (unsigned long)s.addressed,
                          (unsigned long)s.ignored, (unsigned long)s.rx_timeout,
                          (unsigned long)s.rx_error, (unsigned long)s.rx_watchdog,
                          (unsigned long)s.tx_start_error, (unsigned long)s.tx_watchdog,
                          (unsigned long)s.recoveries);
        }
    }
}

// =====================================================================
#else
#error "No role selected. Build with env:tag or env:anchorN (see platformio.ini)."
#endif
