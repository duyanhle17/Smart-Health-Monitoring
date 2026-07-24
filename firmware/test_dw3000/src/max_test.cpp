// =====================================================================
//  TEST MAX30102 (nhip tim/SpO2) + MAX30205 (nhiet do) tren bus I2C
//
//  Build:  pio run -e maxtest  -t upload     (board USB goc)
//          pio run -e maxtestu -t upload     (board CH343)
//
//  I2C: SDA=GPIO8  SCL=GPIO9   |  VCC=3V3  GND=GND (noi chung ca 2 con)
//  Dia chi: MAX30205 = 0x48 (A0/A1/A2 -> GND)   MAX30102 = 0x57
// =====================================================================
#include <Arduino.h>
#include <Wire.h>
#include "MAX30105.h"          // thu vien SparkFun MAX3010x (dung duoc cho MAX30102)

#define I2C_SDA   8
#define I2C_SCL   9
#define ADDR_30205 0x48
#define ADDR_30102 0x57

static MAX30105 pox;
static bool ok30102 = false, ok30205 = false;
static uint8_t addr30205 = 0;     // tu do: MAX30205 nam dau do trong 0x48..0x4F

// tim MAX30205 trong dai 0x48..0x4F (bo qua 0x4A/0x4B = BNO08x)
static uint8_t find30205() {
    for (uint8_t a = 0x48; a <= 0x4F; a++) {
        if (a == 0x4A || a == 0x4B) continue;      // BNO08x
        Wire.beginTransmission(a);
        if (Wire.endTransmission() == 0) return a;
    }
    return 0;
}

// ---------- I2C scan ----------
static void i2cScan() {
    Serial.println("-- quet I2C (SDA=8, SCL=9) --");
    int n = 0;
    for (uint8_t a = 1; a < 127; a++) {
        Wire.beginTransmission(a);
        if (Wire.endTransmission() == 0) {
            n++;
            const char *name = (a == 0x48) ? "MAX30205 (nhiet do)" :
                               (a == 0x57) ? "MAX30102 (nhip tim)" :
                               (a == 0x4A || a == 0x4B) ? "BNO08x (IMU)" :
                               (a >= 0x48 && a <= 0x4F) ? "MAX30205 (nhiet do, addr-select)" : "?";
            Serial.printf("   0x%02X  %s\n", a, name);
        }
    }
    if (!n) Serial.println("   (!) khong thay gi -> kiem tra SDA/SCL/3V3/GND");
    Serial.printf("   => %d thiet bi\n", n);
}

// ---------- MAX30205: doc thanh ghi nhiet do 0x00 (16-bit, 1/256 do C) ----------
static bool readTemp30205(float &outC) {
    if (!addr30205) return false;
    Wire.beginTransmission(addr30205);
    Wire.write(0x00);                                  // temperature register
    if (Wire.endTransmission(false) != 0) return false;
    if (Wire.requestFrom(addr30205, (uint8_t)2) != 2) return false;
    int16_t raw = ((int16_t)Wire.read() << 8) | Wire.read();
    outC = raw / 256.0f;                               // 0.00390625 C / LSB
    return true;
}

void setup() {
    Serial.begin(115200);
    uint32_t t0 = millis(); while (!Serial && millis() - t0 < 2000) {}
    Serial.println("\n===== TEST MAX30102 + MAX30205 =====");

    Wire.begin(I2C_SDA, I2C_SCL, 400000);
    delay(50);
    i2cScan();

    // --- MAX30102 ---
    if (pox.begin(Wire, I2C_SPEED_FAST, ADDR_30102)) {
        ok30102 = true;
        //      ledBrightness, sampleAvg, ledMode(2=Red+IR), sampleRate, pulseWidth, adcRange
        pox.setup(60, 4, 2, 100, 411, 4096);
        Serial.println("[MAX30102] OK - da cau hinh (Red + IR)");
    } else {
        Serial.println("[MAX30102] KHONG THAY (0x57) -> kiem tra VIN/GND/SDA/SCL");
    }

    // --- MAX30205 (tu do dia chi 0x48..0x4F) ---
    addr30205 = find30205();
    float t;
    ok30205 = readTemp30205(t);
    if (ok30205) Serial.printf("[MAX30205] OK tai 0x%02X - nhiet do ban dau %.2f C\n", addr30205, t);
    else if (addr30205) Serial.printf("[MAX30205] thay 0x%02X nhung doc loi\n", addr30205);
    else Serial.println("[MAX30205] KHONG THAY trong 0x48..0x4F -> kiem tra VCC/GND/SDA/SCL");

    Serial.println("====================================");
    Serial.println("Dat NGON TAY len MAX30102 de thay IR tang vot\n");
}

void loop() {
    uint32_t ir = 0, red = 0;
    if (ok30102) { ir = pox.getIR(); red = pox.getRed(); }

    float tempC = NAN;
    bool tOK = ok30205 && readTemp30205(tempC);

    // IR > ~50000 thuong la co ngon tay dat len
    const char *finger = (!ok30102) ? "--" : (ir > 50000 ? "CO NGON TAY" : "khong");

    Serial.printf("IR=%7lu  RED=%7lu  [%s]   |  Nhiet do = %s\n",
                  (unsigned long)ir, (unsigned long)red, finger,
                  tOK ? String(tempC, 2).c_str() : "loi");
    delay(300);
}
