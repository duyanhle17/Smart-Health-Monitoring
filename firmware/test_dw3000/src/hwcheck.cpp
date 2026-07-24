// =====================================================================
//  MACH CHECK — quet I2C + doc DWM3000 DEV_ID, in ra thiet bi nao song.
//  Build:  pio run -e hwcheck -t upload   (board USB goc, Serial qua USB)
//  I2C: SDA=GPIO8 SCL=GPIO9   |   UWB SPI (IOMUX): SCK12 MOSI11 MISO13 CS10 RST17
// =====================================================================
#include <Arduino.h>
#include <Wire.h>
#include <SPI.h>

#define I2C_SDA   8
#define I2C_SCL   9
#define PIN_SCK   12
#define PIN_MOSI  11
#define PIN_MISO  13
#define PIN_CS    10
#define PIN_RST   17

static const char* i2cName(uint8_t a) {
    switch (a) {
        case 0x57: return "MAX30102 (nhip tim/SpO2)";
        case 0x48: return "MAX30205 (nhiet do)";
        case 0x49: case 0x4C: case 0x4D:
        case 0x4E: case 0x4F: return "MAX30205 (nhiet do, addr-select)";
        case 0x4A: case 0x4B: return "BNO08x (IMU)  [hoac MAX30205 neu dat addr nay!]";
        default:   return "?";
    }
}

static uint32_t readDevId() {
    SPI.begin(PIN_SCK, PIN_MISO, PIN_MOSI, -1);
    pinMode(PIN_CS, OUTPUT); digitalWrite(PIN_CS, HIGH);
    pinMode(PIN_RST, OUTPUT); digitalWrite(PIN_RST, LOW); delay(2);
    pinMode(PIN_RST, INPUT); delay(3);
    uint8_t tx[5] = {0x00, 0, 0, 0, 0}, rx[5] = {0};   // 1-byte short header 0x00 + read 4
    SPI.beginTransaction(SPISettings(2000000, MSBFIRST, SPI_MODE0));
    digitalWrite(PIN_CS, LOW);
    for (int i = 0; i < 5; i++) rx[i] = SPI.transfer(tx[i]);
    digitalWrite(PIN_CS, HIGH);
    SPI.endTransaction();
    return rx[1] | ((uint32_t)rx[2] << 8) | ((uint32_t)rx[3] << 16) | ((uint32_t)rx[4] << 24);
}

static int scanBus(int sda, int scl) {
    Wire.end();
    Wire.begin(sda, scl, 100000);
    delay(5);
    int f = 0;
    for (uint8_t a = 1; a < 127; a++) {
        Wire.beginTransmission(a);
        if (Wire.endTransmission() == 0) { f++; Serial.printf("   0x%02X  %s\n", a, i2cName(a)); }
    }
    return f;
}

static void scanAll() {
    Serial.println("\n================ MACH CHECK ================");
    // 1) muc nghi cua SDA/SCL: co nguon + pull-up thi phai HIGH ca hai
    Wire.end();
    pinMode(I2C_SDA, INPUT); pinMode(I2C_SCL, INPUT); delay(3);
    int lsda = digitalRead(I2C_SDA), lscl = digitalRead(I2C_SCL);
    Serial.printf("-- muc nghi: SDA(8)=%s  SCL(9)=%s  %s\n",
        lsda ? "HIGH" : "LOW", lscl ? "HIGH" : "LOW",
        (lsda && lscl) ? "[OK: co nguon+pull-up]"
                       : "[!] can HIGH ca 2. LOW = chua cap 3V3 / chua noi day / thieu pull-up");

    // 2) quet dung chieu SDA=8 SCL=9
    Serial.println("-- I2C quet (SDA=8, SCL=9) --");
    int f = scanBus(I2C_SDA, I2C_SCL);
    if (f == 0) {
        Serial.println("   khong thay -> thu DAO chan (SDA=9, SCL=8)...");
        int f2 = scanBus(I2C_SCL, I2C_SDA);
        if (f2 > 0) Serial.println("   >>> THAY khi DAO! Ban dang cam NGUOC SDA<->SCL. Doi lai la xong.");
        else        Serial.println("   van 0 -> kiem tra: 3V3, GND, va SDA/SCL co dung GPIO8/GPIO9 khong");
        f = f2;
    }
    Serial.printf("   => tong %d thiet bi I2C\n", f);

    // 3) DWM3000
    uint32_t dev = readDevId();
    Serial.printf("-- DWM3000 (SPI IOMUX): DEV_ID=%08X  %s\n",
                  (unsigned)dev, dev == 0xDECA0302 ? "OK (UWB song)" : "FAIL");
    Serial.println("===========================================");
}

void setup() {
    Serial.begin(115200);
    uint32_t t0 = millis(); while (!Serial && millis() - t0 < 2000) {}
}

void loop() {
    scanAll();
    delay(3000);
}
