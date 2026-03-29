#include "Mpu.h"
#include <Adafruit_MPU6050.h>
#include <Adafruit_Sensor.h>

static Adafruit_MPU6050 _mpu;

bool mpu_begin(TwoWire &wire) {
    if (!_mpu.begin(0x68, &wire)) return false;
    _mpu.setAccelerometerRange(MPU6050_RANGE_8_G);
    _mpu.setGyroRange(MPU6050_RANGE_500_DEG);
    _mpu.setFilterBandwidth(MPU6050_BAND_21_HZ);
    return true;
}

void mpu_read(MpuData &out) {
    sensors_event_t a, g, t;
    _mpu.getEvent(&a, &g, &t);
    out.ax   = a.acceleration.x;
    out.ay   = a.acceleration.y;
    out.az   = a.acceleration.z;
    out.gx   = g.gyro.x;
    out.gy   = g.gyro.y;
    out.gz   = g.gyro.z;
    out.temp = t.temperature;
}