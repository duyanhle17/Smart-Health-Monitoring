#include "BodyTemp.h"

#define MAX30205_REG_TEMP  0x00

static TwoWire *_wire = nullptr;
static uint8_t  _addr = 0;

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
    _wire->beginTransmission(_addr);
    _wire->write(MAX30205_REG_TEMP);
    if (_wire->endTransmission(false) != 0)          return false;
    if (_wire->requestFrom(_addr, (uint8_t)2) != 2)  return false;
    int16_t raw = ((int16_t)_wire->read() << 8) | _wire->read();
    degC = raw / 256.0f;
    return true;
}

uint8_t bodytemp_address() { return _addr; }
