// =====================================================================
//  TEST DWM3000 (UWB / SPI) + BNO08x (IMU / I2C) CUNG LUC  — cho TAG
//
//  Build:  pio run -e uwbimu  -t upload      (board USB goc / native-USB)
//          pio run -e uwbimuu -t upload      (board dung CH343)
//
//  UWB (SPI IOMUX): SCK=12  MOSI=11  MISO=13  CS=10  RST=17
//  IMU (I2C)      : SDA=8   SCL=9    addr 0x4A (ADD->GND; PS0,PS1->GND; CS->3V3)
//
//  UWB doc bang raw SPI (khong can thu vien Dw3000) nen khong xung dot gi
//  voi thu vien BNO08x. Muc dich: xac nhan CA HAI song va chay chung duoc.
// =====================================================================
#include <Arduino.h>
#include <Wire.h>
#include <SPI.h>
#include <SparkFun_BNO08x_Arduino_Library.h>

// ---- pins ----
#define I2C_SDA   8
#define I2C_SCL   9
#define PIN_SCK   12
#define PIN_MOSI  11
#define PIN_MISO  13
#define PIN_CS    10
#define PIN_RST   17

#define DEV_ID_EXPECT 0xDECA0302UL

static BNO08x  imu;
static bool    imuOK   = false;
static uint8_t imuAddr = 0;

// =============== DWM3000 raw SPI helpers ===============
static void dwSpiBegin() {
    SPI.begin(PIN_SCK, PIN_MISO, PIN_MOSI, -1);      // manual CS
    pinMode(PIN_CS, OUTPUT); digitalWrite(PIN_CS, HIGH);
}
static void dwReset() {
    pinMode(PIN_RST, OUTPUT); digitalWrite(PIN_RST, LOW); delay(2);
    pinMode(PIN_RST, INPUT);  delay(5);              // open-drain: tha noi
}
// short read: 1-byte header + 4 data
static uint32_t dwReadShort(uint8_t hdr) {
    uint8_t b[5] = {hdr, 0, 0, 0, 0};
    SPI.beginTransaction(SPISettings(2000000, MSBFIRST, SPI_MODE0));
    digitalWrite(PIN_CS, LOW);
    SPI.transfer(b, sizeof(b));                      // in-place full-duplex
    digitalWrite(PIN_CS, HIGH);
    SPI.endTransaction();
    return b[1] | ((uint32_t)b[2] << 8) | ((uint32_t)b[3] << 16) | ((uint32_t)b[4] << 24);
}
// extended read: 2-byte header + 4 data
static uint32_t dwReadExt(uint8_t h0, uint8_t h1) {
    uint8_t b[6] = {h0, h1, 0, 0, 0, 0};
    SPI.beginTransaction(SPISettings(2000000, MSBFIRST, SPI_MODE0));
    digitalWrite(PIN_CS, LOW);
    SPI.transfer(b, sizeof(b));
    digitalWrite(PIN_CS, HIGH);
    SPI.endTransaction();
    return b[2] | ((uint32_t)b[3] << 8) | ((uint32_t)b[4] << 16) | ((uint32_t)b[5] << 24);
}
// extended write 32-bit
static void dwWriteExt(uint8_t h0, uint8_t h1, uint32_t v) {
    uint8_t b[6] = {h0, h1, (uint8_t)v, (uint8_t)(v >> 8), (uint8_t)(v >> 16), (uint8_t)(v >> 24)};
    SPI.beginTransaction(SPISettings(2000000, MSBFIRST, SPI_MODE0));
    digitalWrite(PIN_CS, LOW);
    SPI.transfer(b, sizeof(b));
    digitalWrite(PIN_CS, HIGH);
    SPI.endTransaction();
}

// =============== setup ===============
void setup() {
    Serial.begin(115200);
    uint32_t t0 = millis(); while (!Serial && millis() - t0 < 2000) {}
    Serial.println("\n========= TEST DWM3000 + BNO08x =========");

    // ---------- UWB ----------
    dwSpiBegin();
    dwReset();
    uint32_t dev = dwReadShort(0x00);                    // DEV_ID
    Serial.printf("[UWB] DEV_ID        = %08lX   %s\n", (unsigned long)dev,
                  dev == DEV_ID_EXPECT ? "OK" : "FAIL (kiem tra SPI/nguon/han module)");
    dwWriteExt(0xC6, 0x00, 0x1234ABCD);                  // write PANADR (file3,off0)
    uint32_t pan = dwReadExt(0x46, 0x00);                // read back
    Serial.printf("[UWB] PANADR wr/rd  = %08lX   %s\n", (unsigned long)pan,
                  pan == 0x1234ABCD ? "OK (write chay)" : "FAIL");

    // ---------- IMU ----------
    Wire.begin(I2C_SDA, I2C_SCL, 400000);
    delay(50);
    if (imu.begin(0x4A, Wire))      { imuOK = true; imuAddr = 0x4A; }
    else if (imu.begin(0x4B, Wire)) { imuOK = true; imuAddr = 0x4B; }

    if (imuOK) {
        Serial.printf("[IMU] BNO08x OK tai 0x%02X\n", imuAddr);
        imu.enableRotationVector(50);     // 50 ms
        imu.enableAccelerometer(50);
        imu.enableStepCounter(200);
        Serial.println("[IMU] da bat: RotationVector + Accel + StepCounter");
    } else {
        Serial.println("[IMU] KHONG THAY BNO08x!");
        Serial.println("      -> SDA=GPIO8, SCL=GPIO9, VCC=3V3, GND=GND");
        Serial.println("      -> ADD + PS0 + PS1 phai xuong GND, CS len 3V3");
    }
    Serial.println("=========================================\n");
}

// =============== loop ===============
void loop() {
    static float yaw = 0, pitch = 0, roll = 0, ax = 0, ay = 0, az = 0;
    static uint32_t steps = 0;

    // UWB con song?
    uint32_t dev = dwReadShort(0x00);

    // IMU: xu ly toi da 12 su kien moi vong
    if (imuOK) {
        for (int i = 0; i < 12 && imu.getSensorEvent(); i++) {
            switch (imu.getSensorEventID()) {
                case SENSOR_REPORTID_ROTATION_VECTOR:
                    yaw   = imu.getYaw()   * 180.0f / PI;
                    pitch = imu.getPitch() * 180.0f / PI;
                    roll  = imu.getRoll()  * 180.0f / PI;
                    break;
                case SENSOR_REPORTID_ACCELEROMETER:
                    ax = imu.getAccelX(); ay = imu.getAccelY(); az = imu.getAccelZ();
                    break;
                case SENSOR_REPORTID_STEP_COUNTER:
                    steps = imu.getStepCount();
                    break;
                default: break;
            }
        }
    }

    Serial.printf("UWB[%s]  IMU yaw=%7.1f pitch=%7.1f roll=%7.1f | acc %6.2f %6.2f %6.2f | steps=%lu\n",
                  dev == DEV_ID_EXPECT ? "OK  " : "FAIL",
                  yaw, pitch, roll, ax, ay, az, (unsigned long)steps);
    delay(300);
}
