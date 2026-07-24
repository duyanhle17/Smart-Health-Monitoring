#pragma once
#include <Arduino.h>
#include <Wire.h>

// MAX30205 - cam bien nhiet do co the (I2C, 0.00390625 C/LSB).
// Dia chi do chan A0/A1/A2 quyet dinh, nam dau do trong 0x48..0x4F,
// nen bodytemp_begin() tu quet dai nay (bo qua 0x4A/0x4B = BNO08x).

bool    bodytemp_begin(TwoWire &wire);   // true neu tim thay cam bien
bool    bodytemp_read(float &degC);      // true neu doc duoc
uint8_t bodytemp_address();              // 0 neu chua tim thay
