#include "BodyTemp.h"

#define MAX30205_REG_TEMP  0x00

// MAX30102 uses the shared bus at 400 kHz.  The MAX30205 breakout is at the
// end of the daisy-chained wiring, so read it at standard-mode speed and then
// restore the fast clock for the pulse sensor / IMU.
static constexpr uint32_t BODYTEMP_I2C_HZ = 100000;
static constexpr uint32_t SHARED_I2C_HZ   = 400000;

static TwoWire *_wire = nullptr;
static uint8_t  _addr = 0;

static bool readResponse(float &degC) {
    if (_wire->requestFrom(_addr, (uint8_t)2, (uint8_t)true) != 2) {
        while (_wire->available()) _wire->read();
        return false;
    }

    int16_t raw = ((int16_t)_wire->read() << 8) | _wire->read();
    float value = raw / 256.0f;
    // A corrupted two-byte reply must not replace a previously good reading.
    if (value < -40.0f || value > 125.0f) return false;
    degC = value;
    return true;
}

static bool readRepeatedStart(float &degC) {
    _wire->beginTransmission(_addr);
    _wire->write(MAX30205_REG_TEMP);
    if (_wire->endTransmission(false) != 0) return false;
    return readResponse(degC);
}

static bool readStopFallback(float &degC) {
    // The MAX30205 nominal protocol is repeated-START (above). A few clone
    // breakouts on a marginal shared bus NACK ESP32's combined command but
    // answer a split transaction; use this only as recovery, never as the
    // normal path.
    _wire->beginTransmission(_addr);
    _wire->write(MAX30205_REG_TEMP);
    if (_wire->endTransmission(true) != 0) return false;
    delayMicroseconds(300);
    return readResponse(degC);
}

bool bodytemp_begin(TwoWire &wire) {
    _wire = &wire;
    _addr = 0;
    for (uint8_t a = 0x48; a <= 0x4F; a++) {
        if (a == 0x4A || a == 0x4B) continue;      // BNO08x lives here
        _wire->beginTransmission(a);
        if (_wire->endTransmission() == 0) { _addr = a; return true; }
    }
    return false;
}

bool bodytemp_read(float &degC) {
    if (!_addr) return false;

    // MAX30205 requires a repeated START between selecting the register and
    // reading it. Keep this transaction at standard-mode speed because this
    // module is at the end of a daisy-chained shared I2C bus.
    _wire->setClock(BODYTEMP_I2C_HZ);
    bool ok = false;
    // Standards-compliant transaction first. Two attempts limit noisy ESP32
    // Wire logs while still recovering most short glitches.
    for (uint8_t attempt = 0; attempt < 2 && !ok; attempt++) {
        ok = readRepeatedStart(degC);
        if (!ok) delay(2);
    }

    // Do not turn an intermittent I2C NACK into a fake 0.0 C in telemetry.
    // The fallback is deliberately bounded; hardware should still be fixed.
    for (uint8_t attempt = 0; attempt < 3 && !ok; attempt++) {
        ok = readStopFallback(degC);
        if (!ok) delay(3);
    }
    _wire->setClock(SHARED_I2C_HZ);
    return ok;
}

uint8_t bodytemp_address() { return _addr; }
