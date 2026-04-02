#pragma once
#include <Arduino.h>
#include <Wire.h>

struct HeartRateStats {
    uint32_t ir;             // Raw IR (realtime)
    bool     fingerDetected; // Có ngón tay
    int      bpm;            // BPM trung bình 5s
    bool     isNewResult;    // Vừa tính xong chu kỳ 5s
    float    chipTemp;       // Nhiệt độ chip MAX30102 (°C)
};

bool heartrate_begin(TwoWire &wire);
void heartrate_update(HeartRateStats &out);