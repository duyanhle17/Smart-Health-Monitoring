#include "BodyTemp.h"

#define MAX30205_REG_TEMP  0x00

// MAX30102 uses the shared bus at 400 kHz.  The MAX30205 breakout is at the
// end of the daisy-chained wiring, so read it at standard-mode speed and then
// restore the fast clock for the pulse sensor / IMU.
static constexpr uint32_t BODYTEMP_I2C_HZ = 100000;
static constexpr uint32_t SHARED_I2C_HZ   = 400000;

static TwoWire *_wire = nullptr;
static uint8_t  _addr = 0;

// The MAX30205 itself is accurate to ±0.1 C, but the marginal shared bus can
// return a two-byte reply that passes the range check yet is still wrong (a
// flipped bit). Body temperature changes far too slowly to move between reads,
// so a median of the last three accepted samples rejects any single glitch
// while preserving the sensor's real precision. Keep the raw 1/256 C
// resolution here; the caller decides how many decimals to publish.
static float   _hist[3] = {0, 0, 0};
static uint8_t _histCount = 0;
static uint8_t _histPos = 0;

static float median3(float a, float b, float c) {
    return max(min(a, b), min(max(a, b), c));
}

static bool readResponse(float &degC) {
    if (_wire->requestFrom(_addr, (uint8_t)2, (uint8_t)true) != 2) {
        while (_wire->available()) _wire->read();
        return false;
    }

    int16_t raw = ((int16_t)_wire->read() << 8) | _wire->read();
    float value = raw / 256.0f;
    // Body core/skin temperature can never sit outside this band; anything else
    // is a corrupted reply and must not replace a previously good reading.
    if (value < 20.0f || value > 45.0f) return false;
    degC = value;
    return true;
}

// Feed one accepted raw sample through the 3-deep median filter.
static float pushMedian(float sample) {
    _hist[_histPos] = sample;
    _histPos = (_histPos + 1) % 3;
    if (_histCount < 3) _histCount++;
    if (_histCount == 1) return sample;
    if (_histCount == 2) return (_hist[0] + _hist[1]) * 0.5f;
    return median3(_hist[0], _hist[1], _hist[2]);
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
    float raw = 0.0f;
    bool ok = false;
    // Standards-compliant transaction first. Two attempts limit noisy ESP32
    // Wire logs while still recovering most short glitches.
    for (uint8_t attempt = 0; attempt < 2 && !ok; attempt++) {
        ok = readRepeatedStart(raw);
        if (!ok) delay(2);
    }

    // Do not turn an intermittent I2C NACK into a fake 0.0 C in telemetry.
    // The fallback is deliberately bounded; hardware should still be fixed.
    for (uint8_t attempt = 0; attempt < 3 && !ok; attempt++) {
        ok = readStopFallback(raw);
        if (!ok) delay(3);
    }
    _wire->setClock(SHARED_I2C_HZ);
    if (ok) degC = pushMedian(raw);   // reject a lone within-range glitch
    return ok;
}

uint8_t bodytemp_address() { return _addr; }
