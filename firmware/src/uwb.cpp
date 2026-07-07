// =====================================================================
//  SafeWork UWB module - DW3000 Single-Sided Two-Way Ranging (SS-TWR)
//  Faithful to the official Makerfabs / Qorvo examples
//  (ex_06a_ss_twr_initiator, ex_06b_ss_twr_responder), extended to
//  address multiple anchors: the poll frame carries a target anchor ID
//  and each anchor only answers polls addressed to it.
// =====================================================================
#include <Arduino.h>
#include <SPI.h>
#include "dw3000.h"          // Makerfabs Dw3000 library (copy into firmware/lib/)
#include "config.h"
#include "uwb.h"

// ---- DW3000 radio configuration (identical on tag and all anchors) ----
static dwt_config_t config = {
    UWB_CHANNEL,      /* Channel number (5 or 9). */
    DWT_PLEN_128,     /* Preamble length. */
    DWT_PAC8,         /* Preamble acquisition chunk size. */
    9,                /* TX preamble code. */
    9,                /* RX preamble code. */
    1,                /* 0=std 8, 1=non-std 8 symbol SFD. */
    DWT_BR_6M8,       /* Data rate 6.8 Mbps. */
    DWT_PHRMODE_STD,  /* PHY header mode. */
    DWT_PHRRATE_STD,  /* PHY header rate. */
    (129 + 8 - 8),    /* SFD timeout. */
    DWT_STS_MODE_OFF, /* STS off. */
    DWT_STS_LEN_64,
    DWT_PDOA_M0       /* PDoA off. */
};

extern dwt_txconfig_t txconfig_options;   // provided by the library

// ---- timing (UWB microseconds) ----
#define POLL_TX_TO_RESP_RX_DLY_UUS  240
#define RESP_RX_TIMEOUT_UUS         400
#define POLL_RX_TO_RESP_TX_DLY_UUS  450

// ---- frame layout ----
#define ALL_MSG_COMMON_LEN      10
#define ALL_MSG_SN_IDX          2
#define TARGET_ID_IDX           10        // poll frame: which anchor should answer
#define RESP_MSG_POLL_RX_TS_IDX 10
#define RESP_MSG_RESP_TX_TS_IDX 14
#define RESP_MSG_TS_LEN         4

// poll = 12 bytes, resp = 20 bytes
static uint8_t tx_poll_msg[] = {0x41,0x88,0,0xCA,0xDE,'W','A','V','E',0xE0,0,0};
static uint8_t rx_resp_msg[] = {0x41,0x88,0,0xCA,0xDE,'V','E','W','A',0xE1,0,0,0,0,0,0,0,0,0,0};
static uint8_t rx_poll_msg[] = {0x41,0x88,0,0xCA,0xDE,'W','A','V','E',0xE0,0,0};
static uint8_t tx_resp_msg[] = {0x41,0x88,0,0xCA,0xDE,'V','E','W','A',0xE1,0,0,0,0,0,0,0,0,0,0};

#define RX_BUF_LEN 20
static uint8_t  rx_buffer[RX_BUF_LEN];
static uint32_t status_reg = 0;
static uint8_t  frame_seq_nb = 0;

// ---- timestamp helpers (from the reference examples) ----
static uint64_t get_tx_timestamp_u64() {
    uint8_t ts_tab[5]; uint64_t ts = 0;
    dwt_readtxtimestamp(ts_tab);
    for (int i = 4; i >= 0; i--) { ts <<= 8; ts |= ts_tab[i]; }
    return ts;
}
static uint64_t get_rx_timestamp_u64() {
    uint8_t ts_tab[5]; uint64_t ts = 0;
    dwt_readrxtimestamp(ts_tab);
    for (int i = 4; i >= 0; i--) { ts <<= 8; ts |= ts_tab[i]; }
    return ts;
}
static void resp_msg_get_ts(uint8_t *ts_field, uint32_t *ts) {
    *ts = 0;
    for (int i = 0; i < RESP_MSG_TS_LEN; i++) *ts += ((uint32_t)ts_field[i]) << (i * 8);
}
static void resp_msg_set_ts(uint8_t *ts_field, uint64_t ts) {
    for (int i = 0; i < RESP_MSG_TS_LEN; i++) { ts_field[i] = (uint8_t)ts; ts >>= 8; }
}

// =====================================================================
bool uwb_begin() {
    // Custom SPI pins for the ESP32-S3 (see config.h). NOTE: the Makerfabs
    // library also keeps its own pin defines - keep them in sync.
    SPI.begin(DW_PIN_SCK, DW_PIN_MISO, DW_PIN_MOSI, DW_PIN_CS);
    spiBegin(DW_PIN_IRQ, DW_PIN_RST);
    spiSelect(DW_PIN_CS);
    delay(2);   // INIT_RC -> IDLE_RC

    if (!dwt_checkidlerc())              return false;
    if (dwt_initialise(DWT_DW_INIT) == DWT_ERROR) return false;
    if (dwt_configure(&config))          return false;

    dwt_configuretxrf(&txconfig_options);
    dwt_setrxantennadelay(UWB_ANT_DLY);
    dwt_settxantennadelay(UWB_ANT_DLY);

#ifdef ROLE_TAG
    dwt_setrxaftertxdelay(POLL_TX_TO_RESP_RX_DLY_UUS);
    dwt_setrxtimeout(RESP_RX_TIMEOUT_UUS);
#endif
    return true;
}

// ---------------------------------------------------------------- TAG
bool uwb_range(uint8_t anchor_id, double &dist_m) {
    tx_poll_msg[ALL_MSG_SN_IDX] = frame_seq_nb;
    tx_poll_msg[TARGET_ID_IDX]  = anchor_id;

    dwt_write32bitreg(SYS_STATUS_ID, SYS_STATUS_TXFRS_BIT_MASK);
    dwt_writetxdata(sizeof(tx_poll_msg), tx_poll_msg, 0);
    dwt_writetxfctrl(sizeof(tx_poll_msg), 0, 1);
    dwt_starttx(DWT_START_TX_IMMEDIATE | DWT_RESPONSE_EXPECTED);

    while (!((status_reg = dwt_read32bitreg(SYS_STATUS_ID)) &
             (SYS_STATUS_RXFCG_BIT_MASK | SYS_STATUS_ALL_RX_TO | SYS_STATUS_ALL_RX_ERR))) {}
    frame_seq_nb++;

    if (status_reg & SYS_STATUS_RXFCG_BIT_MASK) {
        dwt_write32bitreg(SYS_STATUS_ID, SYS_STATUS_RXFCG_BIT_MASK);
        uint32_t frame_len = dwt_read32bitreg(RX_FINFO_ID) & RXFLEN_MASK;
        if (frame_len <= sizeof(rx_buffer)) {
            dwt_readrxdata(rx_buffer, frame_len, 0);
            rx_buffer[ALL_MSG_SN_IDX] = 0;
            if (memcmp(rx_buffer, rx_resp_msg, ALL_MSG_COMMON_LEN) == 0) {
                uint32_t poll_tx_ts, resp_rx_ts, poll_rx_ts, resp_tx_ts;
                poll_tx_ts = dwt_readtxtimestamplo32();
                resp_rx_ts = dwt_readrxtimestamplo32();
                float clockOffsetRatio = ((float)dwt_readclockoffset()) / (uint32_t)(1 << 26);
                resp_msg_get_ts(&rx_buffer[RESP_MSG_POLL_RX_TS_IDX], &poll_rx_ts);
                resp_msg_get_ts(&rx_buffer[RESP_MSG_RESP_TX_TS_IDX], &resp_tx_ts);

                int32_t rtd_init = resp_rx_ts - poll_tx_ts;
                int32_t rtd_resp = resp_tx_ts - poll_rx_ts;
                double tof = ((rtd_init - rtd_resp * (1.0f - clockOffsetRatio)) / 2.0) * DWT_TIME_UNITS;
                dist_m = tof * SPEED_OF_LIGHT;
                return true;
            }
        }
    } else {
        dwt_write32bitreg(SYS_STATUS_ID, SYS_STATUS_ALL_RX_TO | SYS_STATUS_ALL_RX_ERR);
    }
    return false;
}

// ------------------------------------------------------------- ANCHOR
void uwb_responder_tick() {
    dwt_setrxtimeout(0);
    dwt_rxenable(DWT_START_RX_IMMEDIATE);

    while (!((status_reg = dwt_read32bitreg(SYS_STATUS_ID)) &
             (SYS_STATUS_RXFCG_BIT_MASK | SYS_STATUS_ALL_RX_ERR))) {}

    if (status_reg & SYS_STATUS_RXFCG_BIT_MASK) {
        dwt_write32bitreg(SYS_STATUS_ID, SYS_STATUS_RXFCG_BIT_MASK);
        uint32_t frame_len = dwt_read32bitreg(RX_FINFO_ID) & RXFLEN_MASK;
        if (frame_len <= sizeof(rx_buffer)) {
            dwt_readrxdata(rx_buffer, frame_len, 0);
            uint8_t target = rx_buffer[TARGET_ID_IDX];
            rx_buffer[ALL_MSG_SN_IDX] = 0;

            // only answer polls with our common header AND our anchor id
            if (memcmp(rx_buffer, rx_poll_msg, ALL_MSG_COMMON_LEN) == 0 && target == ANCHOR_ID) {
                uint64_t poll_rx_ts = get_rx_timestamp_u64();
                uint32_t resp_tx_time = (poll_rx_ts + (POLL_RX_TO_RESP_TX_DLY_UUS * UUS_TO_DWT_TIME)) >> 8;
                dwt_setdelayedtrxtime(resp_tx_time);
                uint64_t resp_tx_ts = (((uint64_t)(resp_tx_time & 0xFFFFFFFEUL)) << 8) + UWB_ANT_DLY;

                resp_msg_set_ts(&tx_resp_msg[RESP_MSG_POLL_RX_TS_IDX], poll_rx_ts);
                resp_msg_set_ts(&tx_resp_msg[RESP_MSG_RESP_TX_TS_IDX], resp_tx_ts);
                tx_resp_msg[ALL_MSG_SN_IDX] = frame_seq_nb;

                dwt_writetxdata(sizeof(tx_resp_msg), tx_resp_msg, 0);
                dwt_writetxfctrl(sizeof(tx_resp_msg), 0, 1);
                if (dwt_starttx(DWT_START_TX_DELAYED) == DWT_SUCCESS) {
                    while (!(dwt_read32bitreg(SYS_STATUS_ID) & SYS_STATUS_TXFRS_BIT_MASK)) {}
                    dwt_write32bitreg(SYS_STATUS_ID, SYS_STATUS_TXFRS_BIT_MASK);
                    frame_seq_nb++;
                }
            }
        }
    } else {
        dwt_write32bitreg(SYS_STATUS_ID, SYS_STATUS_ALL_RX_ERR);
    }
}
