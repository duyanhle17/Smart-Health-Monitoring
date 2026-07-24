// =====================================================================
//  DWM3000 <-> ESP32-S3 test sketch  (SafeWork)
//  Pick a mode via PlatformIO build flag (see platformio.ini):
//     env:check      -D TEST_CHECK       read DEV_ID -> is the module ALIVE?
//     env:initiator  -D TEST_INITIATOR   SS-TWR tag, prints distance
//     env:responder  -D TEST_RESPONDER   SS-TWR anchor (pair with initiator)
//
//  Wiring (matches ../src/config.h). ONLY 3.3V to the module!
//     SCK=12  MOSI=11  MISO=13  CS=10  IRQ=18  RST=17
//     VDD3V3->3V3   GND->GND
//  NOTE: copy the Makerfabs "Dw3000" library into this folder's lib/
//        (or share the one in ../lib/). Keep its pin defines in sync.
// =====================================================================
#include <Arduino.h>
#include <SPI.h>
#include "dw3000.h"

#define PIN_SCK  12
#define PIN_MOSI 11
#define PIN_MISO 13
#define PIN_CS   10
#define PIN_IRQ  18
#define PIN_RST  17

// Shared radio config (identical for initiator & responder)
static dwt_config_t config = {
    5, DWT_PLEN_128, DWT_PAC8, 9, 9, 1, DWT_BR_6M8,
    DWT_PHRMODE_STD, DWT_PHRRATE_STD, (129 + 8 - 8),
    DWT_STS_MODE_OFF, DWT_STS_LEN_64, DWT_PDOA_M0
};

extern uint8_t _ss;   // Dw3000 lib chip-select global (used by readfromspi/writetospi)

// Clean DW3000 bring-up on the FSPI IOMUX pins (SCK=12 MOSI=11 MISO=13 CS=10).
// Hardware SPI works cleanly on IOMUX pins (extended reads + writes verified), so we
// init the Arduino SPI bus here and let the library's readfromspi/writetospi (SPI.transfer)
// use it. Manual CS (ss=-1) — the library toggles _ss = PIN_CS itself. No library
// spiSelect() (its DW1000-legacy register writes corrupt the DW3000).
static void spiStart() {
    SPI.begin(PIN_SCK, PIN_MISO, PIN_MOSI, -1);   // hardware SPI on IOMUX pins, manual CS
    pinMode(PIN_CS, OUTPUT); digitalWrite(PIN_CS, HIGH);
    _ss = PIN_CS;                                 // CS pin the library drives
    pinMode(PIN_IRQ, INPUT);
    // hardware reset (RST open-drain active-low: pull low, then release to float)
    pinMode(PIN_RST, OUTPUT); digitalWrite(PIN_RST, LOW); delay(2);
    pinMode(PIN_RST, INPUT); delay(2);            // INIT_RC -> IDLE_RC
}

// =====================================================================
#if defined(TEST_CHECK)
// ------- DWM3000 MOSI diagnostic: is the master->chip data line working? -------
// Raw 2 MHz read with a CONFIGURABLE first (header) byte. DEV_ID (header 0x00) reads
// fine even if MOSI is disconnected (chip sees all-zero = "read reg 0"). Sending a
// NON-ZERO header proves whether MOSI actually reaches the chip.
// Raw register write/read (each self-contained SPI.end()+begin(), 2 MHz, MODE0).
static void rawWriteReg(uint8_t h0, uint8_t h1, uint32_t val) {
    SPI.end(); SPI.begin(12, 13, 11, -1);
    pinMode(10, OUTPUT); digitalWrite(10, HIGH); delayMicroseconds(5);
    SPI.beginTransaction(SPISettings(2000000, MSBFIRST, SPI_MODE0));
    digitalWrite(10, LOW);
    SPI.transfer(h0); SPI.transfer(h1);
    SPI.transfer(val & 0xFF); SPI.transfer((val>>8)&0xFF);
    SPI.transfer((val>>16)&0xFF); SPI.transfer((val>>24)&0xFF);
    digitalWrite(10, HIGH);
    SPI.endTransaction();
}
static uint32_t rawReadReg(uint8_t h0, uint8_t h1) {
    SPI.end(); SPI.begin(12, 13, 11, -1);
    pinMode(10, OUTPUT); digitalWrite(10, HIGH); delayMicroseconds(5);
    SPI.beginTransaction(SPISettings(2000000, MSBFIRST, SPI_MODE0));
    digitalWrite(10, LOW);
    SPI.transfer(h0); SPI.transfer(h1);
    uint8_t b0=SPI.transfer(0), b1=SPI.transfer(0), b2=SPI.transfer(0), b3=SPI.transfer(0);
    digitalWrite(10, HIGH);
    SPI.endTransaction();
    return b0 | ((uint32_t)b1<<8) | ((uint32_t)b2<<16) | ((uint32_t)b3<<24);
}

// BULK: whole transaction in ONE SPI.transferBytes() (continuous clocking, no
// inter-byte gap) — tests whether byte-by-byte SPI.transfer() desyncs the DW3000.
static uint32_t rawReadRegBulk(uint8_t h0, uint8_t h1) {
    SPI.end(); SPI.begin(12, 13, 11, -1);
    pinMode(10, OUTPUT); digitalWrite(10, HIGH); delayMicroseconds(5);
    uint8_t buf[6] = {h0, h1, 0, 0, 0, 0};
    SPI.beginTransaction(SPISettings(2000000, MSBFIRST, SPI_MODE0));
    digitalWrite(10, LOW);
    SPI.transferBytes(buf, buf, 6);
    digitalWrite(10, HIGH);
    SPI.endTransaction();
    return buf[2] | ((uint32_t)buf[3]<<8) | ((uint32_t)buf[4]<<16) | ((uint32_t)buf[5]<<24);
}
static void rawWriteRegBulk(uint8_t h0, uint8_t h1, uint32_t val) {
    SPI.end(); SPI.begin(12, 13, 11, -1);
    pinMode(10, OUTPUT); digitalWrite(10, HIGH); delayMicroseconds(5);
    uint8_t buf[6] = {h0, h1, (uint8_t)val, (uint8_t)(val>>8), (uint8_t)(val>>16), (uint8_t)(val>>24)};
    SPI.beginTransaction(SPISettings(2000000, MSBFIRST, SPI_MODE0));
    digitalWrite(10, LOW);
    SPI.transferBytes(buf, buf, 6);
    digitalWrite(10, HIGH);
    SPI.endTransaction();
}

// DEV_ID via 1-byte header 0x00 (reads work even without MOSI).
static uint32_t rawDev() {
    SPI.end(); SPI.begin(12, 13, 11, -1);
    pinMode(10, OUTPUT); digitalWrite(10, HIGH); delayMicroseconds(5);
    SPI.beginTransaction(SPISettings(2000000, MSBFIRST, SPI_MODE0));
    digitalWrite(10, LOW);
    SPI.transfer(0x00);
    uint8_t b0=SPI.transfer(0), b1=SPI.transfer(0), b2=SPI.transfer(0), b3=SPI.transfer(0);
    digitalWrite(10, HIGH);
    SPI.endTransaction();
    return b0 | ((uint32_t)b1<<8) | ((uint32_t)b2<<16) | ((uint32_t)b3<<24);
}

// 1-byte (short) read with arbitrary header — tests MOSI bit fidelity across patterns.
static uint32_t rawShort(uint8_t h) {
    SPI.end(); SPI.begin(12, 13, 11, -1);
    pinMode(10, OUTPUT); digitalWrite(10, HIGH); delayMicroseconds(5);
    SPI.beginTransaction(SPISettings(2000000, MSBFIRST, SPI_MODE0));
    digitalWrite(10, LOW);
    SPI.transfer(h);
    uint8_t b0=SPI.transfer(0), b1=SPI.transfer(0), b2=SPI.transfer(0), b3=SPI.transfer(0);
    digitalWrite(10, HIGH);
    SPI.endTransaction();
    return b0 | ((uint32_t)b1<<8) | ((uint32_t)b2<<16) | ((uint32_t)b3<<24);
}

// Extended (2-byte header) read, then extract the 32-bit value at BIT OFFSET 10
// (the DW3000 returns the data 6 bits early vs a byte-aligned read on this setup).
static uint32_t extRead(uint8_t h0, uint8_t h1) {
    SPI.end(); SPI.begin(12, 13, 11, -1);
    pinMode(10, OUTPUT); digitalWrite(10, HIGH); delayMicroseconds(5);
    uint8_t buf[8]; buf[0]=h0; buf[1]=h1; for (int i=2;i<8;i++) buf[i]=0;
    SPI.beginTransaction(SPISettings(2000000, MSBFIRST, SPI_MODE0));
    digitalWrite(10, LOW);
    SPI.transferBytes(buf, buf, 8);
    digitalWrite(10, HIGH);
    SPI.endTransaction();
    uint8_t db[4] = {0,0,0,0};
    for (int i = 0; i < 32; i++) { int bp = 10 + i; db[i/8] |= ((buf[bp/8]>>(7-(bp%8)))&1) << (7-(i%8)); }
    return db[0] | ((uint32_t)db[1]<<8) | ((uint32_t)db[2]<<16) | ((uint32_t)db[3]<<24);
}

// 2-byte (extended) read of DEV_ID at a configurable SPI clock — tests if slowing the
// clock fixes multi-byte transfers (GPIO-matrix / timing hypothesis).
static uint32_t rawReadSpd(uint8_t h0, uint8_t h1, uint32_t hz) {
    SPI.end(); SPI.begin(12, 13, 11, -1);
    pinMode(10, OUTPUT); digitalWrite(10, HIGH); delayMicroseconds(5);
    uint8_t buf[6] = {h0, h1, 0, 0, 0, 0};
    SPI.beginTransaction(SPISettings(hz, MSBFIRST, SPI_MODE0));
    digitalWrite(10, LOW);
    SPI.transferBytes(buf, buf, 6);
    digitalWrite(10, HIGH);
    SPI.endTransaction();
    return buf[2] | ((uint32_t)buf[3]<<8) | ((uint32_t)buf[4]<<16) | ((uint32_t)buf[5]<<24);
}

// BIT-BANG SPI (pure GPIO, MODE0, ~100kHz) — bypasses the ESP32 SPI peripheral entirely.
// If a 2-byte-header read fails HERE too (provably-correct clocking, header verified vs
// the DW3000 manual), the fault is 100% in the DW3000 chip, not the ESP32 SPI.
static inline uint8_t bb(uint8_t out) {
    uint8_t in = 0;
    for (int b = 7; b >= 0; b--) {
        digitalWrite(11, (out>>b)&1);         // MOSI=11
        delayMicroseconds(3);
        digitalWrite(12, HIGH);               // SCK=12 rising: sample
        delayMicroseconds(3);
        in = (in<<1) | (digitalRead(13)&1);   // MISO=13
        digitalWrite(12, LOW);
        delayMicroseconds(3);
    }
    return in;
}
static void bbSetup() {
    SPI.end();
    pinMode(12, OUTPUT); digitalWrite(12, LOW);   // SCK=12 idle low
    pinMode(11, OUTPUT); digitalWrite(11, LOW);   // MOSI=11
    pinMode(13, INPUT);                           // MISO=13
    pinMode(10, OUTPUT); digitalWrite(10, HIGH);  // CS=10 idle high
}
static uint32_t bbRead(const uint8_t* hdr, int hlen) {
    digitalWrite(10, LOW);
    for (int i = 0; i < hlen; i++) bb(hdr[i]);
    uint8_t b0=bb(0), b1=bb(0), b2=bb(0), b3=bb(0);
    digitalWrite(10, HIGH);
    return b0 | ((uint32_t)b1<<8) | ((uint32_t)b2<<16) | ((uint32_t)b3<<24);
}

void setup() {
    Serial.begin(115200);
    uint32_t t0 = millis(); while (!Serial && millis() - t0 < 2000);
    Serial.println("\n=== DWM3000 DIAGNOSTIC (HW reset + 30ms settle) ===");
    // Test the 'chip not ready after wake-up' hypothesis: proper RST + generous wait.
    SPI.begin(12, 13, 11, -1);
    pinMode(10, OUTPUT); digitalWrite(10, HIGH);
    pinMode(17, OUTPUT); digitalWrite(17, LOW); delay(5);   // RST low
    pinMode(17, INPUT); delay(30);                          // release RST + 30 ms settle
}

void loop() {
    // MISO line health (GPIO13): short/no-power vs module-not-responding.
    SPI.end();
    pinMode(PIN_MISO, INPUT_PULLUP); delayMicroseconds(40); int miso_pu = digitalRead(PIN_MISO);
    pinMode(PIN_MISO, INPUT);        delayMicroseconds(40); int miso_fl = digitalRead(PIN_MISO);

    uint32_t dev_s = rawShort(0x00);              // DEV_ID via SHORT 1-byte header
    uint32_t dev_e = rawReadRegBulk(0x40, 0x00);  // DEV_ID via EXTENDED 2-byte header
    rawWriteRegBulk(0xC0, 0x30, 0x1234ABCD);      // write PANADR
    uint32_t pana  = rawReadRegBulk(0x40, 0x30);  // read PANADR back
    bool ext_ok = (dev_e == 0xDECA0302), wr_ok = (pana == 0x1234ABCD);

    const char *diag;
    if (ext_ok && wr_ok)   diag = "OK: read+write work!";
    else if (miso_pu == 0) diag = "!! MISO keo-len van LOW -> chap GND / mat nguon 3V3";
    else if (dev_s == 0 && dev_e == 0)
                           diag = "!! MISO troi, module KHONG dap -> han lai MISO/VCC/GND module (moi han nguoi)";
    else                   diag = "co data nhung khong phai DEV_ID";
    Serial.printf("DEV short=%08X ext=%08X PANADR=%08X | MISO pull=%d float=%d => %s\n",
        dev_s, dev_e, pana, miso_pu, miso_fl, diag);
    delay(1500);
}

// =====================================================================
#elif defined(TEST_INITIATOR) || defined(TEST_RESPONDER)
// ------------------- SS-TWR ranging (one pair) ----------------------
extern dwt_txconfig_t txconfig_options;

#define TX_ANT_DLY 16385
#define RX_ANT_DLY 16385
#define ALL_MSG_COMMON_LEN 10
#define ALL_MSG_SN_IDX 2
#define RESP_MSG_POLL_RX_TS_IDX 10
#define RESP_MSG_RESP_TX_TS_IDX 14
#define RESP_MSG_TS_LEN 4
// Turnaround widened for ESP32 + 2 MHz SPI (default 450 UUS is too short to
// prepare the response in time -> dwt_starttx(DELAYED) fails). Responder now
// has ~3 ms; initiator opens a wide RX window that covers the later reply.
#define POLL_TX_TO_RESP_RX_DLY_UUS 500
#define RESP_RX_TIMEOUT_UUS 5000
#define POLL_RX_TO_RESP_TX_DLY_UUS 3000

static uint8_t tx_poll_msg[] = {0x41,0x88,0,0xCA,0xDE,'W','A','V','E',0xE0,0,0};
static uint8_t rx_resp_msg[] = {0x41,0x88,0,0xCA,0xDE,'V','E','W','A',0xE1,0,0,0,0,0,0,0,0,0,0};
static uint8_t rx_poll_msg[] = {0x41,0x88,0,0xCA,0xDE,'W','A','V','E',0xE0,0,0};
static uint8_t tx_resp_msg[] = {0x41,0x88,0,0xCA,0xDE,'V','E','W','A',0xE1,0,0,0,0,0,0,0,0,0,0};
static uint8_t rx_buffer[20];
static uint32_t status_reg = 0;
static uint8_t frame_seq_nb = 0;

static uint64_t get_rx_ts() { uint8_t t[5]; uint64_t v=0; dwt_readrxtimestamp(t); for(int i=4;i>=0;i--){v<<=8;v|=t[i];} return v; }
static void resp_get_ts(uint8_t *f, uint32_t *ts){ *ts=0; for(int i=0;i<RESP_MSG_TS_LEN;i++) *ts += ((uint32_t)f[i])<<(i*8); }
static void resp_set_ts(uint8_t *f, uint64_t ts){ for(int i=0;i<RESP_MSG_TS_LEN;i++){ f[i]=(uint8_t)ts; ts>>=8; } }

void setup() {
    Serial.begin(115200);
    uint32_t t0 = millis(); while (!Serial && millis() - t0 < 2000);
#if defined(TEST_INITIATOR)
    Serial.println("\n=== SS-TWR INITIATOR (tag) ===");
#else
    Serial.println("\n=== SS-TWR RESPONDER (anchor) ===");
#endif
    spiStart();
    if (!dwt_checkidlerc()) { Serial.println("IDLE_RC FAIL - power/wiring"); while(1); }
    if (dwt_initialise(DWT_DW_INIT) == DWT_ERROR) { Serial.println("INIT FAIL"); while(1); }
    if (dwt_configure(&config)) { Serial.println("CONFIG FAIL"); while(1); }
    dwt_configuretxrf(&txconfig_options);
    dwt_setrxantennadelay(RX_ANT_DLY);
    dwt_settxantennadelay(TX_ANT_DLY);
#if defined(TEST_INITIATOR)
    dwt_setrxaftertxdelay(POLL_TX_TO_RESP_RX_DLY_UUS);
    dwt_setrxtimeout(RESP_RX_TIMEOUT_UUS);
#endif
    Serial.println("ready");
}

#if defined(TEST_INITIATOR)
void loop() {
    tx_poll_msg[ALL_MSG_SN_IDX] = frame_seq_nb;
    dwt_write32bitreg(SYS_STATUS_ID, SYS_STATUS_TXFRS_BIT_MASK);
    dwt_writetxdata(sizeof(tx_poll_msg), tx_poll_msg, 0);
    dwt_writetxfctrl(sizeof(tx_poll_msg), 0, 1);
    dwt_starttx(DWT_START_TX_IMMEDIATE | DWT_RESPONSE_EXPECTED);

    while (!((status_reg = dwt_read32bitreg(SYS_STATUS_ID)) &
             (SYS_STATUS_RXFCG_BIT_MASK | SYS_STATUS_ALL_RX_TO | SYS_STATUS_ALL_RX_ERR))) {}
    frame_seq_nb++;

    if (status_reg & SYS_STATUS_RXFCG_BIT_MASK) {
        dwt_write32bitreg(SYS_STATUS_ID, SYS_STATUS_RXFCG_BIT_MASK);
        uint32_t len = dwt_read32bitreg(RX_FINFO_ID) & RXFLEN_MASK;
        if (len <= sizeof(rx_buffer)) {
            dwt_readrxdata(rx_buffer, len, 0);
            rx_buffer[ALL_MSG_SN_IDX] = 0;
            if (memcmp(rx_buffer, rx_resp_msg, ALL_MSG_COMMON_LEN) == 0) {
                uint32_t poll_tx_ts = dwt_readtxtimestamplo32();
                uint32_t resp_rx_ts = dwt_readrxtimestamplo32();
                float clkOff = ((float)dwt_readclockoffset()) / (uint32_t)(1 << 26);
                uint32_t poll_rx_ts, resp_tx_ts;
                resp_get_ts(&rx_buffer[RESP_MSG_POLL_RX_TS_IDX], &poll_rx_ts);
                resp_get_ts(&rx_buffer[RESP_MSG_RESP_TX_TS_IDX], &resp_tx_ts);
                int32_t rtd_init = resp_rx_ts - poll_tx_ts;
                int32_t rtd_resp = resp_tx_ts - poll_rx_ts;
                double tof = ((rtd_init - rtd_resp * (1.0f - clkOff)) / 2.0) * DWT_TIME_UNITS;
                double dist = tof * SPEED_OF_LIGHT;
                Serial.printf("dist = %.2f m\n", dist);
            }
        }
    } else {
        bool to = status_reg & SYS_STATUS_ALL_RX_TO;
        dwt_write32bitreg(SYS_STATUS_ID, SYS_STATUS_ALL_RX_TO | SYS_STATUS_ALL_RX_ERR);
        Serial.printf("[init] no resp | SYS_STATUS=%08lX %s\n", (unsigned long)status_reg,
                      to ? "(RX_TIMEOUT = heard nothing back)" : "(RX_ERROR = heard a corrupt reply)");
    }
    delay(200);
}
#else   // TEST_RESPONDER
void loop() {
    static uint32_t good = 0, err = 0, nto = 0;
    dwt_setrxtimeout(100000);   // ~102 ms window -> heartbeat if nothing arrives
    dwt_rxenable(DWT_START_RX_IMMEDIATE);
    while (!((status_reg = dwt_read32bitreg(SYS_STATUS_ID)) &
             (SYS_STATUS_RXFCG_BIT_MASK | SYS_STATUS_ALL_RX_TO | SYS_STATUS_ALL_RX_ERR))) {}

    if (status_reg & SYS_STATUS_ALL_RX_TO) {
        nto++;
        dwt_write32bitreg(SYS_STATUS_ID, SYS_STATUS_ALL_RX_TO);
        Serial.printf("[resp] listening... nothing (to=%lu err=%lu good=%lu)\n",
                      (unsigned long)nto, (unsigned long)err, (unsigned long)good);
    } else if (!(status_reg & SYS_STATUS_RXFCG_BIT_MASK)) {
        err++;
        dwt_write32bitreg(SYS_STATUS_ID, SYS_STATUS_ALL_RX_ERR);
        Serial.printf("[resp] RX ERROR SYS_STATUS=%08lX (signal present but corrupt) err=%lu\n",
                      (unsigned long)status_reg, (unsigned long)err);
    } else {
        good++;
        dwt_write32bitreg(SYS_STATUS_ID, SYS_STATUS_RXFCG_BIT_MASK);
        uint32_t len = dwt_read32bitreg(RX_FINFO_ID) & RXFLEN_MASK;
        Serial.printf("[resp] GOT FRAME len=%lu good=%lu\n", (unsigned long)len, (unsigned long)good);
        if (len <= sizeof(rx_buffer)) {
            dwt_readrxdata(rx_buffer, len, 0);
            rx_buffer[ALL_MSG_SN_IDX] = 0;
            if (memcmp(rx_buffer, rx_poll_msg, ALL_MSG_COMMON_LEN) != 0) {
                Serial.printf("[resp] NOT poll: rx=%02X %02X %02X %02X %02X %02X %02X %02X %02X %02X\n",
                    rx_buffer[0],rx_buffer[1],rx_buffer[2],rx_buffer[3],rx_buffer[4],
                    rx_buffer[5],rx_buffer[6],rx_buffer[7],rx_buffer[8],rx_buffer[9]);
            } else {
                uint64_t poll_rx_ts = get_rx_ts();
                uint32_t resp_tx_time = (poll_rx_ts + (POLL_RX_TO_RESP_TX_DLY_UUS * UUS_TO_DWT_TIME)) >> 8;
                dwt_setdelayedtrxtime(resp_tx_time);
                uint64_t resp_tx_ts = (((uint64_t)(resp_tx_time & 0xFFFFFFFEUL)) << 8) + TX_ANT_DLY;
                resp_set_ts(&tx_resp_msg[RESP_MSG_POLL_RX_TS_IDX], poll_rx_ts);
                resp_set_ts(&tx_resp_msg[RESP_MSG_RESP_TX_TS_IDX], resp_tx_ts);
                tx_resp_msg[ALL_MSG_SN_IDX] = frame_seq_nb;
                dwt_writetxdata(sizeof(tx_resp_msg), tx_resp_msg, 0);
                dwt_writetxfctrl(sizeof(tx_resp_msg), 0, 1);
                int txr = dwt_starttx(DWT_START_TX_DELAYED);
                if (txr == DWT_SUCCESS) {
                    while (!(dwt_read32bitreg(SYS_STATUS_ID) & SYS_STATUS_TXFRS_BIT_MASK)) {}
                    dwt_write32bitreg(SYS_STATUS_ID, SYS_STATUS_TXFRS_BIT_MASK);
                    frame_seq_nb++;
                    Serial.println("[resp] responded");
                } else {
                    Serial.println("[resp] poll matched BUT starttx(DELAYED) FAILED (turnaround too slow)");
                }
            }
        }
    }
}
#endif

// =====================================================================
#else
#error "Pick a test: env:check / env:initiator / env:responder"
#endif
