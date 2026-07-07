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

static void spiStart() {
    // SPI pins set by the vendored Dw3000 lib via -DDW3000_PIN_* (platformio.ini)
    spiBegin(PIN_IRQ, PIN_RST);
    spiSelect(PIN_CS);
    delay(2);   // INIT_RC -> IDLE_RC
}

// =====================================================================
#if defined(TEST_CHECK)
// ------- Is the DWM3000 alive & is the SPI wiring correct? ----------
void setup() {
    Serial.begin(115200);
    uint32_t t0 = millis(); while (!Serial && millis() - t0 < 2000);
    Serial.println("\n=== DWM3000 ALIVE CHECK ===");
    Serial.println("pins: SCK12 MOSI11 MISO13 CS10 IRQ18 RST17  (3.3V ONLY)");
    spiStart();
}

void loop() {
    bool idle = dwt_checkidlerc();
    uint32_t id = dwt_readdevid();
    Serial.printf("IDLE_RC=%s  DEV_ID=0x%08X  -> ", idle ? "ok" : "FAIL", id);

    if ((id & 0xFFFFFF00UL) == 0xDECA0300UL) {
        Serial.println("DW3000 ALIVE :)  (module + SPI + power OK)");
    } else if (id == 0xDECA0130UL) {
        Serial.println("this is a DW1000, not DW3000!");
    } else if (id == 0x00000000UL || id == 0xFFFFFFFFUL) {
        Serial.println("DEAD or SPI miswired (check CS/MISO/MOSI/SCK, 3.3V, GND)");
    } else {
        Serial.println("unexpected id (wiring/noise?)");
    }
    delay(1000);
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
#define POLL_TX_TO_RESP_RX_DLY_UUS 240
#define RESP_RX_TIMEOUT_UUS 400
#define POLL_RX_TO_RESP_TX_DLY_UUS 450

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
        dwt_write32bitreg(SYS_STATUS_ID, SYS_STATUS_ALL_RX_TO | SYS_STATUS_ALL_RX_ERR);
        Serial.println("no response (is the responder powered & in range?)");
    }
    delay(200);
}
#else   // TEST_RESPONDER
void loop() {
    dwt_setrxtimeout(0);
    dwt_rxenable(DWT_START_RX_IMMEDIATE);
    while (!((status_reg = dwt_read32bitreg(SYS_STATUS_ID)) &
             (SYS_STATUS_RXFCG_BIT_MASK | SYS_STATUS_ALL_RX_ERR))) {}

    if (status_reg & SYS_STATUS_RXFCG_BIT_MASK) {
        dwt_write32bitreg(SYS_STATUS_ID, SYS_STATUS_RXFCG_BIT_MASK);
        uint32_t len = dwt_read32bitreg(RX_FINFO_ID) & RXFLEN_MASK;
        if (len <= sizeof(rx_buffer)) {
            dwt_readrxdata(rx_buffer, len, 0);
            rx_buffer[ALL_MSG_SN_IDX] = 0;
            if (memcmp(rx_buffer, rx_poll_msg, ALL_MSG_COMMON_LEN) == 0) {
                uint64_t poll_rx_ts = get_rx_ts();
                uint32_t resp_tx_time = (poll_rx_ts + (POLL_RX_TO_RESP_TX_DLY_UUS * UUS_TO_DWT_TIME)) >> 8;
                dwt_setdelayedtrxtime(resp_tx_time);
                uint64_t resp_tx_ts = (((uint64_t)(resp_tx_time & 0xFFFFFFFEUL)) << 8) + TX_ANT_DLY;
                resp_set_ts(&tx_resp_msg[RESP_MSG_POLL_RX_TS_IDX], poll_rx_ts);
                resp_set_ts(&tx_resp_msg[RESP_MSG_RESP_TX_TS_IDX], resp_tx_ts);
                tx_resp_msg[ALL_MSG_SN_IDX] = frame_seq_nb;
                dwt_writetxdata(sizeof(tx_resp_msg), tx_resp_msg, 0);
                dwt_writetxfctrl(sizeof(tx_resp_msg), 0, 1);
                if (dwt_starttx(DWT_START_TX_DELAYED) == DWT_SUCCESS) {
                    while (!(dwt_read32bitreg(SYS_STATUS_ID) & SYS_STATUS_TXFRS_BIT_MASK)) {}
                    dwt_write32bitreg(SYS_STATUS_ID, SYS_STATUS_TXFRS_BIT_MASK);
                    frame_seq_nb++;
                    Serial.println("responded");
                }
            }
        }
    } else {
        dwt_write32bitreg(SYS_STATUS_ID, SYS_STATUS_ALL_RX_ERR);
    }
}
#endif

// =====================================================================
#else
#error "Pick a test: env:check / env:initiator / env:responder"
#endif
