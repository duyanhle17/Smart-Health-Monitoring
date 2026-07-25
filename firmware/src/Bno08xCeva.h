#pragma once

// BNO08x production transport built on CEVA's maintained SH-2 core.
//
// The BNO08x I2C implementation repeats an SHTP header when a host begins a
// fresh I2C read.  The legacy SparkFun transport used 32-byte fragments, which
// corrupts that framing on this ESP32-S3 board.  This wrapper uses a 384-byte
// Wire buffer and exposes the header and repeated full transfer as the two
// SHTP fragments expected by the CEVA reference HAL.

#include <Arduino.h>
#include <Wire.h>

extern "C" {
#include <sh2.h>
}

class Bno08xCeva {
public:
    static constexpr size_t kWireBufferBytes = 384;

    enum class EventType : uint8_t {
        RotationVector,
        Accelerometer,
        GyroscopeCalibrated,
        LinearAcceleration,
        StepCounter,
        StabilityClassifier,
    };

    struct Event {
        EventType type = EventType::Accelerometer;
        uint8_t accuracy = 0;          // SH-2 status bits: 0=unreliable .. 3=high
        float x = 0.0f;
        float y = 0.0f;
        float z = 0.0f;
        float w = 1.0f;                // quaternion real component for RotationVector
        float accuracyRadians = 0.0f;  // rotation-vector accuracy estimate
        uint16_t steps = 0;
        uint8_t stability = 0;
    };

    // The caller owns Wire.begin() and selects the BNO's standard-mode clock
    // before calling begin/service.  This lets MAX30102/MAX30205 retain their
    // existing shared-bus clock policy.
    bool begin(uint8_t address, TwoWire &wire);
    void end();

    bool enableRotationVector(uint32_t intervalMs);
    bool enableAccelerometer(uint32_t intervalMs);
    bool enableGyro(uint32_t intervalMs);
    bool enableLinearAccelerometer(uint32_t intervalMs);
    bool enableStepCounter(uint32_t intervalMs);
    bool enableStabilityClassifier(uint32_t intervalMs);

    // Service at most one complete SHTP transfer and return one decoded event.
    // A single SHTP input packet can contain several reports; remaining ones
    // stay in the small FIFO for the following calls.
    bool getSensorEvent(Event &event);

    // True once for each asynchronous BNO reset after begin() completes.
    bool takeReset();
    bool ready() const { return open_; }
    uint8_t address() const { return address_; }
    uint32_t shtpErrors() const { return shtpErrors_; }
    uint32_t transportErrors() const { return transportErrors_; }
    uint32_t droppedEvents() const { return droppedEvents_; }

private:
    static constexpr size_t kEventQueueSize = 32;

    static Bno08xCeva *active_;

    static int halOpen(sh2_Hal_t *);
    static void halClose(sh2_Hal_t *);
    static int halRead(sh2_Hal_t *, uint8_t *out, unsigned outLength, uint32_t *timestampUs);
    static int halWrite(sh2_Hal_t *, uint8_t *packet, unsigned length);
    static uint32_t halGetTimeUs(sh2_Hal_t *);
    static void onAsyncEvent(void *, sh2_AsyncEvent_t *event);
    static void onSensorEvent(void *, sh2_SensorEvent_t *event);

    bool openTransport();
    bool readExact(uint8_t *dst, size_t length);
    bool writePacket(const uint8_t *packet, size_t length);
    int readTransfer(uint8_t *out, unsigned outLength, uint32_t *timestampUs);
    int writeTransfer(uint8_t *packet, unsigned length);
    bool setReport(sh2_SensorId_t sensor, uint32_t intervalMs);
    void serviceTransport();
    void handleAsyncEvent(sh2_AsyncEvent_t *event);
    void handleSensorEvent(sh2_SensorEvent_t *event);
    void pushEvent(const Event &event);
    bool popEvent(Event &event);
    void clearRuntimeState();

    TwoWire *wire_ = nullptr;
    uint8_t address_ = 0;
    bool open_ = false;
    bool resetPending_ = false;
    uint16_t pendingPacketLength_ = 0;
    uint8_t pendingChannel_ = 0;
    uint32_t pendingTimestampUs_ = 0;
    uint32_t shtpErrors_ = 0;
    uint32_t transportErrors_ = 0;
    uint32_t droppedEvents_ = 0;
    Event events_[kEventQueueSize]{};
    size_t eventHead_ = 0;
    size_t eventTail_ = 0;
    size_t eventCount_ = 0;

    sh2_Hal_t hal_ = {
        halOpen,
        halClose,
        halRead,
        halWrite,
        halGetTimeUs,
    };
};
