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
#include <esp_system.h>
#include <freertos/FreeRTOS.h>
#include <freertos/queue.h>
#include "Bno08xCeva.h"
#include "HeartRate.h"
#include "BodyTemp.h"
#include "netcfg.h"
#include "wifi_portal.h"

static Bno08xCeva     imu;
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
static uint8_t  linearAccelAccuracy = 0;
static uint8_t  gyroAccuracy = 0;
static uint8_t  stability = 0;            // BNO: 1=on-table, 2=stationary, 4=motion
// Game Rotation Vector: gyro+accel only, no magnetometer. Near steel/rebar the
// magnetic RotationVector rarely reaches the backend's yaw_accuracy>=2 gate;
// this heading drifts slowly instead of jumping, and its map offset can be
// learned server-side from the UWB track. Published alongside `yaw`, it never
// replaces it.
static float    yawGameDeg = 0;
static uint8_t  yawGameAccuracy = 0;
static uint32_t lastGameRotationAt = 0;
// Fall evidence between posts: |a| extremes with a hold window. Snapshotting
// only the instantaneous sample made a 50-100 ms impact invisible whenever it
// fell between two ~400 ms posts; the hold also survives the one-slot queue
// coalescing a packet away. An expired extreme is replaced by the current
// sample, so each post reports the dip/impact from the last ~2 s.
static constexpr uint32_t ACC_EXTREME_HOLD_MS = 2000;
static float    accPeakG = 0;
static float    accValleyG = 0;
static uint32_t accPeakAt = 0;            // 0 = no accepted sample yet
static uint32_t accValleyAt = 0;
// Latched fall incident, detected per accelerometer SAMPLE: a free-fall dip
// (<= FALL_EVENT_FREEFALL_G within FALL_EVENT_PAIR_MS) followed by an impact
// >= FALL_EVENT_IMPACT_G, or a hard impact alone. Unlike the rolling extremes
// above, this latch survives any uplink outage: it is cleared only after a
// successful POST carried it (fallEventAckedId, written by the telemetry
// task; aligned 32-bit stores are atomic on the S3). Without the latch a
// WiFi roam/backend outage longer than ACC_EXTREME_HOLD_MS spanning the
// impact silently lost the only fall evidence this system has.
static constexpr float FALL_EVENT_IMPACT_G = 2.8f;
static constexpr float FALL_EVENT_HARD_G = 4.5f;
static constexpr float FALL_EVENT_FREEFALL_G = 0.45f;
static constexpr uint32_t FALL_EVENT_PAIR_MS = 2000;
static float    fallEventPeakG = 0;
static float    fallEventValleyG = 0;
static uint32_t fallEventAt = 0;          // 0 = nothing latched
static uint32_t fallEventSeq = 0;         // increments once per incident
static volatile uint32_t fallEventAckedId = 0; // last id delivered with 2xx
static uint32_t lastImuAt = 0;
static uint32_t lastRotationVectorAt = 0;
static uint32_t lastLinearAccelAt = 0;
static uint32_t imuSessionStartedAt = 0;
static uint32_t imuEpoch = 1;
static uint32_t lastImuProbeAt = 0;
static uint8_t bnoProbe4A = 0xFF;
static uint8_t bnoProbe4B = 0xFF;
static constexpr uint32_t IMU_RETRY_MS = 2000;
// `imu_ok` means a recent decoded BNO event, not merely that the last I2C
// write ACKed. Give startup enough time for its reset/feature responses, then
// re-open the transport if the report stream stops.
static constexpr uint32_t IMU_STARTUP_GRACE_MS = 2500;
static constexpr uint32_t IMU_STALE_MS = 1500;
// The external MAX30205 is at the end of a daisy-chained I2C harness. Keep
// BNO08x control/report transfers at standard mode; MAX30102 still gets its
// normal 400 kHz window before/after this service function.
static constexpr uint32_t BNO_I2C_HZ = 100000;
static constexpr uint32_t SHARED_I2C_HZ = 400000;
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
// One SS-TWR result can jump because of a short multipath/NLOS fade. Collect
// five independent, sequence-verified responses for each anchor and publish
// their median as one *atomic* d1+d2 pair. This removes a single RF outlier
// before it reaches the backend smoother without turning a failed link into a
// made-up coordinate. Seven bounded attempts keep the 200 ms UWB budget intact.
//
// The anchors are polled interleaved (A1,A2,A1,A2,...) rather than in two
// back-to-back batches: both medians then share the same centre in time. With
// batches, d1's centre led d2's by 60-90 ms, so a walking tag handed the
// solver a pair of distances that never held simultaneously (~10-15 cm of
// artificial error at walking speed, plus false innovation in the EKF).
static constexpr uint8_t UWB_RANGE_VALID_SAMPLES = 5;
static constexpr uint8_t UWB_RANGE_MAX_ATTEMPTS = 7;
static constexpr double UWB_MIN_VALID_RANGE_M = 0.05;
// The floor alone let a burst of large outliers become the median (nothing
// capped a garbage 300 m sample). Anything beyond any plausible site span is
// a decode artifact, not a position.
static constexpr double UWB_MAX_VALID_RANGE_M = 50.0;

// The UWB sampler runs in the Arduino loop; only HTTPS runs in a low-priority
// task. A one-slot queue intentionally coalesces old packets while Cloudflare
// is slow: the server receives the newest *measured* d1+d2 pair, never a
// backlog of stale coordinates.
struct TelemetrySnapshot {
    char workerId[40]{};
    double d[NUM_ANCHORS]{};
    bool rangeOk[NUM_ANCHORS]{};
    bool rangeNlos[NUM_ANCHORS]{};
    uint32_t rangeSeq = 0;
    uint32_t rangeAgeMs = 0;
    uint32_t rangeEpoch = 0;
    bool rangeTrusted = false;
    int bpm = 0;
    uint32_t ir = 0;
    uint8_t hrQuality = 0;
    float hrPerfusion = 0;
    uint16_t hrIbiMs = 0;
    uint8_t hrBeats = 0;
    int spo2 = 0;
    bool spo2Valid = false;
    bool hasBodyTemp = false;
    bool bodyTempFresh = false;
    float bodyTempC = 0;
    uint32_t bodyTempAgeMs = UINT32_MAX;
    bool hasChipTemp = false;
    float chipTempC = 0;
    bool imuOk = false;
    uint8_t imuAddress = 0;
    float yaw = 0;
    float yawGame = 0;
    uint8_t yawGameAccuracy = 0;
    uint32_t yawGameAgeMs = UINT32_MAX;
    float accPeak = 0;
    float accValley = 0;
    uint32_t accPeakAgeMs = UINT32_MAX;
    uint32_t accValleyAgeMs = UINT32_MAX;
    bool fallEvent = false;
    uint32_t fallEventId = 0;
    float fallEventPeak = 0;
    float fallEventValley = 0;
    uint32_t fallEventAgeMs = UINT32_MAX;
    uint16_t stepCount = 0;
    float acceleration = 0;
    float accelX = 0, accelY = 0, accelZ = 0;
    float gyroX = 0, gyroY = 0, gyroZ = 0;
    float linearAcceleration = 0;
    float linearAccelX = 0, linearAccelY = 0, linearAccelZ = 0;
    uint8_t stability = 0;
    uint8_t yawAccuracy = 0;
    uint8_t linearAccelAccuracy = 0;
    uint8_t gyroAccuracy = 0;
    float yawAccuracyRad = 0;
    uint32_t imuAgeMs = UINT32_MAX;
    uint32_t yawAgeMs = UINT32_MAX;
    uint32_t linearAccelAgeMs = UINT32_MAX;
    uint32_t imuEpoch = 0;
    uint8_t bnoProbe4A = 0xFF;
    uint8_t bnoProbe4B = 0xFF;
};

static QueueHandle_t telemetryQueue = nullptr;
static double latestRanges[NUM_ANCHORS]{};
static bool latestRangeOk[NUM_ANCHORS]{};
static bool latestRangeNlos[NUM_ANCHORS]{};
static uint32_t latestRangeAt = 0;
static uint32_t latestRangeSeq = 0;
static uint32_t rangeEpoch = 0;
static bool haveRangeSample = false;

struct AnchorSampleSet {
    double  samples[UWB_RANGE_VALID_SAMPLES]{};
    uint8_t valid = 0;
    uint8_t attempts = 0;
    uint8_t nlosSuspect = 0;
};

// In-place insertion sort avoids dynamic allocation on the timing-sensitive
// Arduino loop. The centre value is the robust median: two multipath outliers
// cannot move the published range.
static double medianOfSamples(double *samples, uint8_t count) {
    for (uint8_t i = 1; i < count; ++i) {
        const double value = samples[i];
        uint8_t j = i;
        while (j > 0 && samples[j - 1] > value) {
            samples[j] = samples[j - 1];
            --j;
        }
        samples[j] = value;
    }
    return samples[count / 2];
}

// One bounded ranging attempt against one anchor. Consumes an attempt slot;
// returns true when a plausible sample was accepted.
static bool collectAnchorSample(uint8_t anchorId, AnchorSampleSet &set) {
    set.attempts++;
    double candidate = 0.0;
    UwbRangeQuality quality;
    if (uwb_range(anchorId, candidate, &quality) && isfinite(candidate) &&
        candidate >= UWB_MIN_VALID_RANGE_M && candidate <= UWB_MAX_VALID_RANGE_M) {
        set.samples[set.valid++] = candidate;
        if (quality.valid && quality.nlosSuspect) set.nlosSuspect++;
        return true;
    }
    // Let an addressed anchor re-arm before the bounded retry. A successful
    // range already left the radio in the correct state.
    delay(3);
    return false;
}

// Round-robin the anchors (A1,A2,A1,A2,...) until each has its five samples
// or an anchor runs out of attempts - then the whole pair is discarded, so a
// half-dead link can never publish a lopsided fix. NLOS is decided per anchor
// by majority of its accepted samples: body shadowing biases all of them the
// same way, which is exactly what the per-sample median cannot detect.
static bool collectMedianRangePair(double (&rangesOut)[NUM_ANCHORS],
                                   bool (&nlosOut)[NUM_ANCHORS]) {
    AnchorSampleSet sets[NUM_ANCHORS];
    bool pending = true;
    while (pending) {
        pending = false;
        for (int i = 0; i < NUM_ANCHORS; ++i) {
            AnchorSampleSet &set = sets[i];
            if (set.valid >= UWB_RANGE_VALID_SAMPLES) continue;
            if (set.attempts >= UWB_RANGE_MAX_ATTEMPTS) return false; // pair lost
            collectAnchorSample(static_cast<uint8_t>(i + 1), set);
            pending = true;
            // Every anchor hears every poll; the one not addressed drops it
            // and must re-arm its receiver before it can be polled itself.
            delay(UWB_INTER_ANCHOR_GUARD_MS);
        }
    }
    for (int i = 0; i < NUM_ANCHORS; ++i) {
        if (sets[i].valid != UWB_RANGE_VALID_SAMPLES) return false;
    }
    for (int i = 0; i < NUM_ANCHORS; ++i) {
        rangesOut[i] = medianOfSamples(sets[i].samples, UWB_RANGE_VALID_SAMPLES);
        nlosOut[i] = (uint8_t)(sets[i].nlosSuspect * 2) > UWB_RANGE_VALID_SAMPLES;
    }
    return true;
}

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

static bool enableImuReports() {
    // BNO08x does the fusion on-sensor. We use its gyro/linear-acceleration
    // only to assess UWB confidence and stationary periods; no raw-accel
    // double integration is used as a position source.
    return imu.enableRotationVector(25) &&
           imu.enableGameRotationVector(25) &&
           imu.enableStepCounter(100) &&
           imu.enableAccelerometer(50) &&
           imu.enableGyro(25) &&
           imu.enableLinearAccelerometer(25) &&
           imu.enableStabilityClassifier(100);
}

// MAX30205 can also be strapped to 0x4A/0x4B, so an ACK alone at the alternate
// address does not identify a BNO08x. Use the explicit board configuration;
// this avoids poisoning the BNO library's single global SHTP transport after a
// failed handshake against a different I2C device.
static bool beginImu() {
    Wire.setClock(BNO_I2C_HZ);
    imuAddr = BNO08X_ADDR;
    const bool started = imu.begin(imuAddr, Wire);
    const bool configured = started && enableImuReports();
    Wire.setClock(SHARED_I2C_HZ);
    if (!configured) {
        imu.end();
        imuAddr = 0;
        return false;
    }
    lastImuAt = 0;
    lastRotationVectorAt = 0;
    lastLinearAccelAt = 0;
    lastGameRotationAt = 0;
    imuSessionStartedAt = millis();
    Serial.printf("{\"event\":\"info\",\"msg\":\"BNO08x at 0x%02X\"}\n", imuAddr);
    return true;
}

static uint8_t probeI2cAddress(uint8_t address) {
    Wire.setClock(BNO_I2C_HZ);
    Wire.beginTransmission(address);
    const uint8_t result = Wire.endTransmission(true);
    Wire.setClock(SHARED_I2C_HZ);
    return result; // 0=ACK, 2=NACK address, 3=NACK data, 4=bus error
}

static bool retryImuIfNeeded() {
    if (imuOK) return true;
    const uint32_t now = millis();
    if (lastImuProbeAt && now - lastImuProbeAt < IMU_RETRY_MS) return false;
    lastImuProbeAt = now;
    bnoProbe4A = probeI2cAddress(0x4A);
    bnoProbe4B = probeI2cAddress(0x4B);
    // The BNO08x can still be starting while MAX30102/MAX30205 probes run on
    // the shared I2C rail. Keep retries local to its configured address; do
    // not scan 0x4A/0x4B and risk binding the BNO transport to MAX30205.
    imuOK = beginImu();
    if (imuOK) {
        imuEpoch++;
        lastImuAt = 0;
        lastRotationVectorAt = 0;
        lastLinearAccelAt = 0;
        lastGameRotationAt = 0;
    }
    return imuOK;
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

    if (!retryImuIfNeeded()) return;

    Wire.setClock(BNO_I2C_HZ);
    // A BNO08x reset loses its enabled report list. Re-enable it in place;
    // this is independent of the DW3000 SPI radio. The new epoch/ages prevent
    // the backend from combining pre-reset heading with a new accel event.
    if (imu.takeReset()) {
        imuEpoch++;
        lastImuAt = 0;
        lastRotationVectorAt = 0;
        lastLinearAccelAt = 0;
        lastGameRotationAt = 0;
        imuSessionStartedAt = millis();
        yawAccuracy = 0;
        yawGameAccuracy = 0;
        linearAccelAccuracy = 0;
        gyroAccuracy = 0;
        // accPeak/accValley survive a BNO reset on purpose: a hard impact can
        // brown-out the sensor, and the pre-reset extreme is the evidence.
        // The hold window expires it naturally.
        if (!enableImuReports()) {
            imuOK = false;
            Wire.setClock(SHARED_I2C_HZ);
            Serial.println("{\"event\":\"error\",\"msg\":\"BNO08x report reconfigure failed\"}");
            return;
        }
    }
    const uint32_t drainStartedAt = micros();
    Bno08xCeva::Event imuEvent{};
    for (int i = 0;
         i < 20 && (micros() - drainStartedAt) < 4000 && imu.getSensorEvent(imuEvent);
         i++) {   // drain queue, but never starve the UWB sampler
        const uint32_t eventAt = millis();
        lastImuAt = eventAt;
        switch (imuEvent.type) {
            case Bno08xCeva::EventType::RotationVector:
                // CEVA exposes the native SH-2 quaternion fields directly:
                // w=real, x=i, y=j, z=k. This matches the verified BNO test
                // and retains the old telemetry convention (degrees).
                yawDeg = atan2f(2.0f * (imuEvent.w * imuEvent.z + imuEvent.x * imuEvent.y),
                                1.0f - 2.0f * (imuEvent.y * imuEvent.y + imuEvent.z * imuEvent.z)) *
                         180.0f / PI;
                yawAccuracy = imuEvent.accuracy;
                yawAccuracyRad = imuEvent.accuracyRadians;
                lastRotationVectorAt = eventAt;
                break;
            case Bno08xCeva::EventType::GameRotationVector:
                // Same quaternion->yaw math as RotationVector; only the
                // reference differs (arbitrary at boot, drifts slowly, no
                // magnetometer). The backend learns its map offset later.
                yawGameDeg = atan2f(2.0f * (imuEvent.w * imuEvent.z + imuEvent.x * imuEvent.y),
                                    1.0f - 2.0f * (imuEvent.y * imuEvent.y + imuEvent.z * imuEvent.z)) *
                             180.0f / PI;
                yawGameAccuracy = imuEvent.accuracy;
                lastGameRotationAt = eventAt;
                break;
            case Bno08xCeva::EventType::StepCounter:
                steps = imuEvent.steps;
                break;
            case Bno08xCeva::EventType::Accelerometer:
                ax = imuEvent.x / 9.81f;
                ay = imuEvent.y / 9.81f;
                az = imuEvent.z / 9.81f;
                accMag = sqrtf(ax * ax + ay * ay + az * az);
                // Roll the |a| extremes forward rather than resetting per
                // snapshot; see ACC_EXTREME_HOLD_MS. >=/<= keep the timestamp
                // fresh while an extreme is being sustained.
                if (!accPeakAt || accMag >= accPeakG ||
                    eventAt - accPeakAt > ACC_EXTREME_HOLD_MS) {
                    accPeakG = accMag;
                    accPeakAt = eventAt;
                }
                if (!accValleyAt || accMag <= accValleyG ||
                    eventAt - accValleyAt > ACC_EXTREME_HOLD_MS) {
                    accValleyG = accMag;
                    accValleyAt = eventAt;
                }
                // Sample-time fall signature check: independent of the rolling
                // extremes' replacement policy, so an earlier unrelated spike
                // cannot shadow a real impact, and no cross-packet ordering is
                // needed. Qualifying bounces within FALL_EVENT_PAIR_MS merge
                // into one incident instead of burning a new id each.
                if (accMag >= FALL_EVENT_HARD_G ||
                    (accMag >= FALL_EVENT_IMPACT_G && accValleyAt &&
                     accValleyG <= FALL_EVENT_FREEFALL_G &&
                     eventAt - accValleyAt <= FALL_EVENT_PAIR_MS)) {
                    if (!fallEventAt || eventAt - fallEventAt > FALL_EVENT_PAIR_MS) {
                        fallEventSeq++;
                        fallEventPeakG = accMag;
                        fallEventValleyG = accValleyG;
                    } else if (accMag > fallEventPeakG) {
                        fallEventPeakG = accMag;
                        if (accValleyG < fallEventValleyG) fallEventValleyG = accValleyG;
                    }
                    fallEventAt = eventAt;
                }
                break;
            case Bno08xCeva::EventType::GyroscopeCalibrated:
                gx = imuEvent.x;
                gy = imuEvent.y;
                gz = imuEvent.z;
                gyroAccuracy = imuEvent.accuracy;
                break;
            case Bno08xCeva::EventType::LinearAcceleration:
                linAx = imuEvent.x;
                linAy = imuEvent.y;
                linAz = imuEvent.z;
                linAccMag = sqrtf(linAx * linAx + linAy * linAy + linAz * linAz);
                linearAccelAccuracy = imuEvent.accuracy;
                lastLinearAccelAt = eventAt;
                break;
            case Bno08xCeva::EventType::StabilityClassifier:
                stability = imuEvent.stability;
                break;
            default: break;
        }
    }

    const uint32_t now = millis();
    const bool waitingTooLongForFirstEvent =
        !lastImuAt && imuSessionStartedAt && now - imuSessionStartedAt >= IMU_STARTUP_GRACE_MS;
    const bool reportStreamStale =
        lastImuAt && now - lastImuAt >= IMU_STALE_MS;
    if (waitingTooLongForFirstEvent || reportStreamStale) {
        Serial.printf("{\"event\":\"error\",\"msg\":\"BNO08x stream stale\",\"shtp_errors\":%lu,\"transport_errors\":%lu}\n",
                      static_cast<unsigned long>(imu.shtpErrors()),
                      static_cast<unsigned long>(imu.transportErrors()));
        imu.end();
        imuOK = false;
        imuAddr = 0;
        imuSessionStartedAt = 0;
    }
    Wire.setClock(SHARED_I2C_HZ);
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
        snapshot.rangeNlos[i] = latestRangeNlos[i];
    }
    snapshot.rangeSeq = latestRangeSeq;
    snapshot.rangeAgeMs = haveRangeSample ? now - latestRangeAt : UINT32_MAX;
    snapshot.rangeEpoch = rangeEpoch;
    snapshot.rangeTrusted = haveRangeSample;
    for (int i = 0; i < NUM_ANCHORS; ++i) snapshot.rangeTrusted &= latestRangeOk[i];
    snapshot.bpm = hr.bpm;
    snapshot.ir = hr.ir;
    snapshot.hrQuality = hr.quality;
    snapshot.hrPerfusion = hr.perfusion;
    snapshot.hrIbiMs = hr.lastIbiMs;
    snapshot.hrBeats = hr.beatsInWindow;
    snapshot.spo2 = hr.spo2;
    snapshot.spo2Valid = hr.spo2Valid;
    snapshot.hasBodyTemp = haveBody;
    snapshot.bodyTempFresh = haveFreshBody;
    snapshot.bodyTempC = lastBodyTempC;
    snapshot.bodyTempAgeMs = bodyAge;
    snapshot.hasChipTemp = haveChipFallback;
    snapshot.chipTempC = hr.chipTemp;
    snapshot.imuOk = imuOK && lastImuAt && now - lastImuAt < IMU_STALE_MS;
    snapshot.imuAddress = imuAddr;
    snapshot.yaw = yawDeg;
    snapshot.yawGame = yawGameDeg;
    snapshot.yawGameAccuracy = yawGameAccuracy;
    snapshot.yawGameAgeMs = lastGameRotationAt ? now - lastGameRotationAt : UINT32_MAX;
    snapshot.accPeak = accPeakG;
    snapshot.accValley = accValleyG;
    snapshot.accPeakAgeMs = accPeakAt ? now - accPeakAt : UINT32_MAX;
    snapshot.accValleyAgeMs = accValleyAt ? now - accValleyAt : UINT32_MAX;
    // Release a delivered fall latch; a newer incident (different id) stays.
    if (fallEventAt && fallEventAckedId == fallEventSeq) fallEventAt = 0;
    snapshot.fallEvent = fallEventAt != 0;
    snapshot.fallEventId = fallEventSeq;
    snapshot.fallEventPeak = fallEventPeakG;
    snapshot.fallEventValley = fallEventValleyG;
    snapshot.fallEventAgeMs = fallEventAt ? now - fallEventAt : UINT32_MAX;
    snapshot.stepCount = steps;
    snapshot.acceleration = accMag;
    snapshot.accelX = ax; snapshot.accelY = ay; snapshot.accelZ = az;
    snapshot.gyroX = gx; snapshot.gyroY = gy; snapshot.gyroZ = gz;
    snapshot.linearAcceleration = linAccMag;
    snapshot.linearAccelX = linAx; snapshot.linearAccelY = linAy; snapshot.linearAccelZ = linAz;
    snapshot.stability = stability;
    snapshot.yawAccuracy = yawAccuracy;
    snapshot.linearAccelAccuracy = linearAccelAccuracy;
    snapshot.gyroAccuracy = gyroAccuracy;
    snapshot.yawAccuracyRad = yawAccuracyRad;
    snapshot.imuAgeMs = lastImuAt ? now - lastImuAt : UINT32_MAX;
    snapshot.yawAgeMs = lastRotationVectorAt ? now - lastRotationVectorAt : UINT32_MAX;
    snapshot.linearAccelAgeMs = lastLinearAccelAt ? now - lastLinearAccelAt : UINT32_MAX;
    snapshot.imuEpoch = imuEpoch;
    snapshot.bnoProbe4A = bnoProbe4A;
    snapshot.bnoProbe4B = bnoProbe4B;
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

// Hardware logs showed d1/d2 arriving at ~800 ms although TELEMETRY_PERIOD_MS
// was 400: when one HTTPS POST outlasts the telemetry period, the one-slot
// queue overwrites every pair measured meanwhile. This 5 s summary turns the
// uplink latency into a measured fact, deciding between "point the tag at a
// LAN backend" and "batch several pairs per packet" without guessing.
struct TelemetryNetStats {
    uint32_t posts = 0;
    uint32_t ok = 0;
    uint32_t lastMs = 0;
    uint32_t maxMs = 0;
    uint64_t totalMs = 0;
};
static TelemetryNetStats netStats;
static uint32_t lastNetLogAt = 0;

static void noteTelemetryPost(int code, uint32_t elapsedMs) {
    netStats.posts++;
    if (code >= 200 && code < 300) netStats.ok++;
    netStats.lastMs = elapsedMs;
    netStats.totalMs += elapsedMs;
    if (elapsedMs > netStats.maxMs) netStats.maxMs = elapsedMs;
    const uint32_t now = millis();
    if (now - lastNetLogAt < 5000) return;
    lastNetLogAt = now;
    if (serialLogAvailable()) {
        Serial.printf("{\"event\":\"telemetry_net\",\"posts\":%lu,\"ok\":%lu,"
                      "\"last_ms\":%lu,\"avg_ms\":%lu,\"max_ms\":%lu}\n",
                      (unsigned long)netStats.posts, (unsigned long)netStats.ok,
                      (unsigned long)netStats.lastMs,
                      (unsigned long)(netStats.totalMs / netStats.posts),
                      (unsigned long)netStats.maxMs);
    }
    netStats = TelemetryNetStats{};   // stats describe one 5 s window each
}

static bool postTelemetry(const TelemetrySnapshot &snapshot) {
    if (WiFi.status() != WL_CONNECTED || !netcfg_has_backend_url()) return false;
    const String url = netcfg().url;
    if (!ensureTelemetryTransport(url)) return false;

    String body = "{";
    body.reserve(1320);
    body += "\"worker_id\":\"" + String(snapshot.workerId) + "\",";
    body += "\"telemetry\":{";
    body +=   "\"hr\":"    + String(snapshot.bpm);
    body +=  ",\"ir\":"    + String(snapshot.ir);
    // Signal-quality context for the heart rate: lets the backend trust a
    // clean reading and discount a motion-corrupted one instead of treating
    // every BPM as equally valid. hr_ibi_ms/hr_beats also feed HRV downstream.
    body +=  ",\"hr_quality\":" + String(snapshot.hrQuality);
    body +=  ",\"hr_perfusion\":" + String(snapshot.hrPerfusion, 2);
    body +=  ",\"hr_ibi_ms\":" + String(snapshot.hrIbiMs);
    body +=  ",\"hr_beats\":" + String(snapshot.hrBeats);
    if (snapshot.hasBodyTemp) {
        // Two decimals: the MAX30205 resolves 1/256 C and is spec'd to ±0.1 C,
        // so 0.01 C is real information, not false precision.
        body += ",\"temp\":" + String(snapshot.bodyTempC, 2);
        body += ",\"temp_source\":\"max30205\"";
    } else if (snapshot.hasChipTemp) {
        body += ",\"temp\":" + String(snapshot.chipTempC, 2);
        body += ",\"temp_source\":\"max30102_chip\"";
    } else {
        // Omit `temp` rather than overwriting the dashboard with a false 0.0.
        body += ",\"temp_source\":\"unavailable\"";
    }
    body +=  ",\"temp_fresh\":" + String(snapshot.bodyTempFresh ? "true" : "false");
    body +=  ",\"temp_age_ms\":";
    body += snapshot.hasBodyTemp ? String(snapshot.bodyTempAgeMs) : String(-1);
    body +=  ",\"imu_ok\":" + String(snapshot.imuOk ? "true" : "false");
    // Report zero explicitly when BNO init failed so the backend does not keep
    // displaying an old successful I2C address as if the IMU were live.
    body += ",\"imu_addr\":" + String(snapshot.imuAddress);
    // SpO2 từ tỉ số Red/IR (ratio-of-ratios). Chỉ gửi khi tưới máu + chất lượng
    // đủ tin; hằng số hiệu chỉnh trong HeartRate.cpp CẦN so với máy đo chuẩn.
    // Không có ngón tay/quá nhiễu -> báo absent thay vì gửi số 0 gây hiểu nhầm.
    if (snapshot.spo2Valid) {
        body += ",\"spo2\":" + String(snapshot.spo2);
        body += ",\"spo2_available\":true";
    } else {
        body += ",\"spo2_available\":false";
    }
    // No gas module on this board.
    body +=  ",\"gas_available\":false";
    body +=  ",\"yaw\":"   + String(snapshot.yaw, 1);
    body +=  ",\"yaw_accuracy\":" + String(snapshot.yawAccuracy);
    body +=  ",\"yaw_accuracy_rad\":" + String(snapshot.yawAccuracyRad, 3);
    body +=  ",\"yaw_age_ms\":" + String(snapshot.yawAgeMs == UINT32_MAX ? -1 : static_cast<int32_t>(snapshot.yawAgeMs));
    // Magnetometer-free heading (Game RV). Sent alongside `yaw`, never instead
    // of it: the backend decides which reference it can trust per deployment.
    body +=  ",\"yaw_game\":" + String(snapshot.yawGame, 1);
    body +=  ",\"yaw_game_accuracy\":" + String(snapshot.yawGameAccuracy);
    body +=  ",\"yaw_game_age_ms\":" + String(snapshot.yawGameAgeMs == UINT32_MAX ? -1 : static_cast<int32_t>(snapshot.yawGameAgeMs));
    body +=  ",\"linear_accel_accuracy\":" + String(snapshot.linearAccelAccuracy);
    body +=  ",\"linear_accel_age_ms\":" + String(snapshot.linearAccelAgeMs == UINT32_MAX ? -1 : static_cast<int32_t>(snapshot.linearAccelAgeMs));
    body +=  ",\"gyro_accuracy\":" + String(snapshot.gyroAccuracy);
    body +=  ",\"steps\":" + String(snapshot.stepCount);
    body +=  ",\"acc\":"   + String(snapshot.acceleration, 2);
    // |a| extremes over the last ACC_EXTREME_HOLD_MS, tracked at the IMU event
    // rate. This is the backend fall gate's evidence: the free-fall dip
    // (valley) and the impact spike (peak) survive between posts even though
    // `acc` above is only the instant of the snapshot. Omitted while no
    // accelerometer event has ever been decoded (backend treats absent as
    // "no evidence", never as 0 g).
    if (snapshot.accPeakAgeMs != UINT32_MAX) {
        body += ",\"acc_peak\":" + String(snapshot.accPeak, 2);
        body += ",\"acc_peak_age_ms\":" + String(static_cast<int32_t>(snapshot.accPeakAgeMs));
    }
    if (snapshot.accValleyAgeMs != UINT32_MAX) {
        body += ",\"acc_valley\":" + String(snapshot.accValley, 2);
        body += ",\"acc_valley_age_ms\":" + String(static_cast<int32_t>(snapshot.accValleyAgeMs));
    }
    // Latched fall incident: repeats in every post until a 2xx acknowledges
    // delivery, so a WiFi/backend outage spanning the impact cannot lose it.
    if (snapshot.fallEvent) {
        body += ",\"fall_event\":true";
        body += ",\"fall_event_id\":" + String(snapshot.fallEventId);
        body += ",\"fall_event_peak\":" + String(snapshot.fallEventPeak, 2);
        body += ",\"fall_event_valley\":" + String(snapshot.fallEventValley, 2);
        body += ",\"fall_event_age_ms\":" + String(snapshot.fallEventAgeMs == UINT32_MAX
                                                       ? -1
                                                       : static_cast<int32_t>(snapshot.fallEventAgeMs));
    }
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
    body +=  ",\"imu_epoch\":" + String(snapshot.imuEpoch);
    body +=  ",\"bno_probe_4a\":" + String(snapshot.bnoProbe4A);
    body +=  ",\"bno_probe_4b\":" + String(snapshot.bnoProbe4B);
    body +=  ",\"range_seq\":" + String(snapshot.rangeSeq);
    body +=  ",\"range_age_ms\":" + String(snapshot.rangeAgeMs == UINT32_MAX ? -1 : static_cast<int32_t>(snapshot.rangeAgeMs));
    body +=  ",\"range_epoch\":" + String(snapshot.rangeEpoch);
    body +=  ",\"range_trusted\":" + String(snapshot.rangeTrusted ? "true" : "false");
    for (int i = 0; i < NUM_ANCHORS; i++) {
        if (!snapshot.rangeOk[i]) continue;
        // Preserve millimetre-level ToF information for the backend median;
        // quantising every sample to 1 cm made small motions look like steps.
        body += ",\"d" + String(i + 1) + "\":" + String(snapshot.d[i], 3);
        // Majority-NLOS verdict for this anchor's median window. The backend
        // widens that range's variance (EKF) instead of trusting a distance
        // the worker's own body just stretched.
        body += ",\"nlos_d" + String(i + 1) + "\":" +
                String(snapshot.rangeNlos[i] ? "true" : "false");
    }
    body += "}}";
    const uint32_t postStartedAt = millis();
    int code = telemetryHttp.POST(body);
    noteTelemetryPost(code, millis() - postStartedAt);
    if (code < 200 || code >= 300) {
        resetTelemetryTransport();
        return false;
    }
    // The 2xx is the fall latch's delivery ack (loop task compares this
    // against the current incident id before releasing the latch).
    if (snapshot.fallEvent) fallEventAckedId = snapshot.fallEventId;
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
    rangeEpoch = esp_random();
    if (!rangeEpoch) rangeEpoch = 1;
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
    lastImuProbeAt = millis();
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

    // Vitals heartbeat on serial: bring-up visibility for the two MAX sensors
    // and SpO2. Gated like the anchor heartbeat (serialLogAvailable) so it
    // never blocks the live telemetry path when no monitor is attached.
    static uint32_t lastVitalsLog = 0;
    if (serialLogAvailable() && millis() - lastVitalsLog >= 2000) {
        lastVitalsLog = millis();
        float tC = 0; bool tOk = tempOK && bodytemp_read(tC);
        const bool pairOk = latestRangeOk[0] && latestRangeOk[1];
        Serial.printf("{\"event\":\"vitals\",\"finger\":%s,\"ir\":%lu,\"hr\":%d,"
                      "\"hr_quality\":%u,\"perfusion\":%.3f,\"spo2\":%d,\"spo2_valid\":%s,"
                      "\"temp\":%.2f,\"temp_ok\":%s,\"temp_addr\":\"0x%02X\","
                      "\"beats\":%u,\"ibi\":%u,"
                      "\"d1\":%.3f,\"d2\":%.3f,\"range_ok\":%s,\"range_seq\":%lu,"
                      "\"nlos\":[%d,%d],\"acc_peak\":%.2f,\"fall_latched\":%d,"
                      "\"yaw_game\":%.1f,\"wifi\":%d}\n",
                      hr.fingerDetected ? "true" : "false",
                      (unsigned long)hr.ir, hr.bpm, hr.quality, (double)hr.perfusion,
                      hr.spo2, hr.spo2Valid ? "true" : "false",
                      (double)tC, tOk ? "true" : "false", bodytemp_address(),
                      (unsigned)hr.beatsInWindow, (unsigned)hr.lastIbiMs,
                      (double)latestRanges[0], (double)latestRanges[1],
                      pairOk ? "true" : "false", (unsigned long)latestRangeSeq,
                      (int)latestRangeNlos[0], (int)latestRangeNlos[1],
                      (double)accPeakG, (int)(fallEventAt != 0), (double)yawGameDeg,
                      (int)(WiFi.status() == WL_CONNECTED));
    }

    if (millis() - lastUwbSample >= UWB_SAMPLE_PERIOD_MS) {
        lastUwbSample = millis();
        double candidateRanges[NUM_ANCHORS]{};
        bool candidateNlos[NUM_ANCHORS]{};
        if (collectMedianRangePair(candidateRanges, candidateNlos)) {
            for (int i = 0; i < NUM_ANCHORS; ++i) {
                latestRanges[i] = candidateRanges[i];
                latestRangeOk[i] = true;
                latestRangeNlos[i] = candidateNlos[i];
            }
            latestRangeAt = millis();
            latestRangeSeq++;
            haveRangeSample = true;
        } else {
            // Never combine a new value from one anchor with an older value
            // from the other. The backend will hold the last measured fix and
            // label the loss explicitly until the next complete pair arrives.
            for (int i = 0; i < NUM_ANCHORS; ++i) latestRangeOk[i] = false;
        }
    }

    // Post every period REGARDLESS of ranging: vitals (HR/temp/IMU) must keep
    // reaching the server even when both anchors are down, so a worker never
    // vanishes from the dashboard just because UWB dropped. d1/d2 are attached
    // only when a fresh pair exists (postTelemetry omits them otherwise, and the
    // backend holds/greys the last fix); range_trusted already reflects this.
    if (millis() - lastTelemetry >= TELEMETRY_PERIOD_MS) {
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
