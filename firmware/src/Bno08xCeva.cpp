#include "Bno08xCeva.h"

#include <string.h>

extern "C" {
#include <sh2_err.h>
#include <sh2_SensorValue.h>
}

namespace {

constexpr uint16_t kShtpHeaderBytes = 4;
constexpr uint32_t kResetWaitMs = 2000;

// SHTP executable-channel software reset, followed by the explicit channel-0
// advertisement request that this BNO085 firmware needs after reset.
constexpr uint8_t kSoftReset[] = {5, 0, 1, 0, 1};
constexpr uint8_t kAdvertiseAll[] = {6, 0, 0, 0, 0, 1};

}  // namespace

Bno08xCeva *Bno08xCeva::active_ = nullptr;

bool Bno08xCeva::begin(uint8_t address, TwoWire &wire) {
    // CEVA's SH-2 core is a singleton. A worker has one BNO08x, so reject a
    // second live wrapper rather than silently mixing two I2C addresses.
    if (active_ && active_ != this) return false;

    end();
    active_ = this;
    wire_ = &wire;
    address_ = address;
    clearRuntimeState();

    // Arduino-ESP32 supports a runtime-sized Wire buffer.  A BNO startup
    // advertisement is 276 bytes on this board, so the legacy 32-byte
    // SparkFun fragmentation must never be used here.
    if (wire_->setBufferSize(kWireBufferBytes) < kWireBufferBytes) {
        wire_ = nullptr;
        address_ = 0;
        active_ = nullptr;
        return false;
    }
    wire_->setTimeOut(150);

    const int status = sh2_open(&hal_, onAsyncEvent, nullptr);
    if (status != SH2_OK) {
        wire_ = nullptr;
        address_ = 0;
        active_ = nullptr;
        return false;
    }
    open_ = true;
    sh2_setSensorCallback(onSensorEvent, nullptr);

    // sh2_open() itself waits only 200 ms for reset complete. This hardware
    // needs a longer post-reset window, so do not configure reports until the
    // executable reset packet has actually been decoded.
    const uint32_t startedAt = millis();
    while (!resetPending_ && static_cast<uint32_t>(millis() - startedAt) < kResetWaitMs) {
        serviceTransport();
        delay(1);
    }
    if (!resetPending_) {
        end();
        return false;
    }

    // The reset that initialized this session is not a later runtime reset.
    // Clearing it prevents the caller from sending a duplicate feature burst
    // on the first normal sensor-service iteration.
    resetPending_ = false;
    return true;
}

void Bno08xCeva::end() {
    if (open_) {
        sh2_close();
        open_ = false;
    }
    if (active_ == this) active_ = nullptr;
    wire_ = nullptr;
    address_ = 0;
    clearRuntimeState();
}

bool Bno08xCeva::enableRotationVector(uint32_t intervalMs) {
    return setReport(SH2_ROTATION_VECTOR, intervalMs);
}

bool Bno08xCeva::enableGameRotationVector(uint32_t intervalMs) {
    return setReport(SH2_GAME_ROTATION_VECTOR, intervalMs);
}

bool Bno08xCeva::enableAccelerometer(uint32_t intervalMs) {
    return setReport(SH2_ACCELEROMETER, intervalMs);
}

bool Bno08xCeva::enableGyro(uint32_t intervalMs) {
    return setReport(SH2_GYROSCOPE_CALIBRATED, intervalMs);
}

bool Bno08xCeva::enableLinearAccelerometer(uint32_t intervalMs) {
    return setReport(SH2_LINEAR_ACCELERATION, intervalMs);
}

bool Bno08xCeva::enableStepCounter(uint32_t intervalMs) {
    return setReport(SH2_STEP_COUNTER, intervalMs);
}

bool Bno08xCeva::enableStabilityClassifier(uint32_t intervalMs) {
    return setReport(SH2_STABILITY_CLASSIFIER, intervalMs);
}

bool Bno08xCeva::getSensorEvent(Event &event) {
    if (popEvent(event)) return true;
    if (!open_) return false;

    serviceTransport();
    return popEvent(event);
}

bool Bno08xCeva::takeReset() {
    if (!resetPending_) return false;
    resetPending_ = false;
    return true;
}

int Bno08xCeva::halOpen(sh2_Hal_t *) {
    return active_ && active_->openTransport() ? SH2_OK : SH2_ERR;
}

void Bno08xCeva::halClose(sh2_Hal_t *) {
    if (!active_) return;
    active_->pendingPacketLength_ = 0;
    active_->pendingChannel_ = 0;
}

int Bno08xCeva::halRead(sh2_Hal_t *, uint8_t *out, unsigned outLength, uint32_t *timestampUs) {
    return active_ ? active_->readTransfer(out, outLength, timestampUs) : SH2_ERR;
}

int Bno08xCeva::halWrite(sh2_Hal_t *, uint8_t *packet, unsigned length) {
    return active_ ? active_->writeTransfer(packet, length) : SH2_ERR;
}

uint32_t Bno08xCeva::halGetTimeUs(sh2_Hal_t *) {
    return micros();
}

void Bno08xCeva::onAsyncEvent(void *, sh2_AsyncEvent_t *event) {
    if (active_ && event) active_->handleAsyncEvent(event);
}

void Bno08xCeva::onSensorEvent(void *, sh2_SensorEvent_t *event) {
    if (active_ && event) active_->handleSensorEvent(event);
}

bool Bno08xCeva::openTransport() {
    if (!wire_ || address_ == 0) return false;

    pendingPacketLength_ = 0;
    pendingChannel_ = 0;
    if (!writePacket(kSoftReset, sizeof(kSoftReset))) return false;
    delay(300);
    return writePacket(kAdvertiseAll, sizeof(kAdvertiseAll));
}

bool Bno08xCeva::readExact(uint8_t *dst, size_t length) {
    if (!wire_ || !dst || length == 0 || length > kWireBufferBytes) return false;

    const size_t received = wire_->requestFrom(static_cast<uint16_t>(address_), length, true);
    if (received != length) {
        while (wire_->available()) wire_->read();
        ++transportErrors_;
        return false;
    }
    for (size_t i = 0; i < length; ++i) {
        if (!wire_->available()) {
            ++transportErrors_;
            return false;
        }
        dst[i] = static_cast<uint8_t>(wire_->read());
    }
    return true;
}

bool Bno08xCeva::writePacket(const uint8_t *packet, size_t length) {
    if (!wire_ || !packet || length == 0 || length > kWireBufferBytes) return false;

    wire_->beginTransmission(address_);
    if (wire_->write(packet, length) != length || wire_->endTransmission(true) != 0) {
        ++transportErrors_;
        return false;
    }
    return true;
}

int Bno08xCeva::readTransfer(uint8_t *out, unsigned outLength, uint32_t *timestampUs) {
    if (!out || !timestampUs) return SH2_ERR_BAD_PARAM;

    if (pendingPacketLength_ != 0) {
        const uint16_t packetLength = pendingPacketLength_;
        const uint8_t packetChannel = pendingChannel_;
        const uint32_t packetTimestamp = pendingTimestampUs_;
        pendingPacketLength_ = 0;
        pendingChannel_ = 0;

        // The BNO emits a fresh header followed by the full SHTP transfer on
        // this second I2C read. Returning it as a separate SHTP fragment is
        // required: its continuation bit and sequence number are intentional.
        if (!readExact(out, packetLength)) return 0;
        const uint16_t fullLength =
            (static_cast<uint16_t>(out[0]) | (static_cast<uint16_t>(out[1]) << 8)) & 0x7FFF;
        if (fullLength != packetLength || out[2] != packetChannel) {
            ++transportErrors_;
            return 0;
        }
        *timestampUs = packetTimestamp;
        return static_cast<int>(packetLength);
    }

    uint8_t header[kShtpHeaderBytes];
    if (!readExact(header, sizeof(header))) return 0;

    const uint16_t packetLength =
        (static_cast<uint16_t>(header[0]) | (static_cast<uint16_t>(header[1]) << 8)) & 0x7FFF;
    if (packetLength == 0) return 0;  // no BNO interrupt/data pending
    if (packetLength < kShtpHeaderBytes || packetLength > outLength ||
        packetLength > kWireBufferBytes) {
        ++transportErrors_;
        return 0;
    }

    memcpy(out, header, sizeof(header));
    pendingPacketLength_ = packetLength;
    pendingChannel_ = header[2];
    pendingTimestampUs_ = micros();
    *timestampUs = pendingTimestampUs_;
    return kShtpHeaderBytes;
}

int Bno08xCeva::writeTransfer(uint8_t *packet, unsigned length) {
    if (!packet || length == 0 || length > kWireBufferBytes) return SH2_ERR_BAD_PARAM;
    return writePacket(packet, length) ? static_cast<int>(length) : SH2_ERR_IO;
}

bool Bno08xCeva::setReport(sh2_SensorId_t sensor, uint32_t intervalMs) {
    if (!open_ || intervalMs == 0 || intervalMs > UINT32_MAX / 1000UL) return false;

    sh2_SensorConfig_t config{};
    config.reportInterval_us = intervalMs * 1000UL;
    return sh2_setSensorConfig(sensor, &config) == SH2_OK;
}

void Bno08xCeva::serviceTransport() {
    if (!open_) return;

    sh2_service();
    // Complete a header/full-frame pair in the same caller turn. This keeps
    // the BNO's continuation transfer contiguous while still presenting two
    // fragments to CEVA's SHTP assembler.
    if (pendingPacketLength_ != 0) sh2_service();
}

void Bno08xCeva::handleAsyncEvent(sh2_AsyncEvent_t *event) {
    if (event->eventId == SH2_RESET) {
        resetPending_ = true;
        eventHead_ = 0;
        eventTail_ = 0;
        eventCount_ = 0;
    } else if (event->eventId == SH2_SHTP_EVENT) {
        ++shtpErrors_;
    }
}

void Bno08xCeva::handleSensorEvent(sh2_SensorEvent_t *event) {
    sh2_SensorValue_t value{};
    if (sh2_decodeSensorEvent(&value, event) != SH2_OK) return;

    Event decoded{};
    decoded.accuracy = value.status & 0x03;
    switch (value.sensorId) {
        case SH2_ROTATION_VECTOR:
            decoded.type = EventType::RotationVector;
            decoded.x = value.un.rotationVector.i;
            decoded.y = value.un.rotationVector.j;
            decoded.z = value.un.rotationVector.k;
            decoded.w = value.un.rotationVector.real;
            decoded.accuracyRadians = value.un.rotationVector.accuracy;
            break;
        case SH2_GAME_ROTATION_VECTOR:
            decoded.type = EventType::GameRotationVector;
            decoded.x = value.un.gameRotationVector.i;
            decoded.y = value.un.gameRotationVector.j;
            decoded.z = value.un.gameRotationVector.k;
            decoded.w = value.un.gameRotationVector.real;
            // No magnetometer means no absolute-heading error estimate; only
            // the SH-2 status bits (decoded.accuracy above) apply.
            break;
        case SH2_ACCELEROMETER:
            decoded.type = EventType::Accelerometer;
            decoded.x = value.un.accelerometer.x;
            decoded.y = value.un.accelerometer.y;
            decoded.z = value.un.accelerometer.z;
            break;
        case SH2_GYROSCOPE_CALIBRATED:
            decoded.type = EventType::GyroscopeCalibrated;
            decoded.x = value.un.gyroscope.x;
            decoded.y = value.un.gyroscope.y;
            decoded.z = value.un.gyroscope.z;
            break;
        case SH2_LINEAR_ACCELERATION:
            decoded.type = EventType::LinearAcceleration;
            decoded.x = value.un.linearAcceleration.x;
            decoded.y = value.un.linearAcceleration.y;
            decoded.z = value.un.linearAcceleration.z;
            break;
        case SH2_STEP_COUNTER:
            decoded.type = EventType::StepCounter;
            decoded.steps = value.un.stepCounter.steps;
            break;
        case SH2_STABILITY_CLASSIFIER:
            decoded.type = EventType::StabilityClassifier;
            decoded.stability = value.un.stabilityClassifier.classification;
            break;
        default:
            return;
    }
    pushEvent(decoded);
}

void Bno08xCeva::pushEvent(const Event &event) {
    if (eventCount_ == kEventQueueSize) {
        // Keep the newest motion state if the caller was busy with UWB/HTTPS.
        eventTail_ = (eventTail_ + 1) % kEventQueueSize;
        --eventCount_;
        ++droppedEvents_;
    }
    events_[eventHead_] = event;
    eventHead_ = (eventHead_ + 1) % kEventQueueSize;
    ++eventCount_;
}

bool Bno08xCeva::popEvent(Event &event) {
    if (eventCount_ == 0) return false;
    event = events_[eventTail_];
    eventTail_ = (eventTail_ + 1) % kEventQueueSize;
    --eventCount_;
    return true;
}

void Bno08xCeva::clearRuntimeState() {
    resetPending_ = false;
    pendingPacketLength_ = 0;
    pendingChannel_ = 0;
    pendingTimestampUs_ = 0;
    shtpErrors_ = 0;
    transportErrors_ = 0;
    droppedEvents_ = 0;
    eventHead_ = 0;
    eventTail_ = 0;
    eventCount_ = 0;
}
