#pragma once
#include <Arduino.h>
#include <Wire.h>

struct MpuData {
    float ax, ay, az;  // Gia tốc (m/s²)
    float gx, gy, gz;  // Góc quay (rad/s)
    float temp;        // Nhiệt độ chip (°C)
};

bool mpu_begin(TwoWire &wire);
void mpu_read(MpuData &out);