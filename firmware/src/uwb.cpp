// =====================================================================
//  SafeWork UWB module - DW3000 Single-Sided Two-Way Ranging (SS-TWR)
//  Faithful to the official Makerfabs / Qorvo examples
//  (ex_06a_ss_twr_initiator, ex_06b_ss_twr_responder), extended to
//  address multiple anchors: the poll frame carries a target anchor ID
//  and each anchor only answers polls addressed to it.
//
//  The bring-up sequence below is the one verified on hardware in
//  test_dw3000/ (env:initu / env:responderu) - do not "simplify" it back
//  to the library's spiBegin()/spiSelect(), see spiStart() for why.
// =====================================================================
#include <Arduino.h>
#include <SPI.h>
#include "dw3000.h"          // vendored Makerfabs Dw3000 library (firmware/lib/)
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
extern uint8_t        _ss;                // library chip-select global, used by readfromspi/writetospi

// ---- timing (UWB microseconds) ----
// Widened from the stock 240/400/450. The vendored driver clocks SPI at 2 MHz
// (lib/Dw3000/src/dw3000_port.cpp), so the responder cannot read the poll and
// prepare a reply within 450 UUS -> dwt_starttx(DELAYED) fails. 3 ms turnaround
// with a 5 ms RX window is what actually ranges on this hardware.
#define POLL_TX_TO_RESP_RX_DLY_UUS  500
#define RESP_RX_TIMEOUT_UUS         5000
#define POLL_RX_TO_RESP_TX_DLY_UUS  3000
// A CRC-valid response from an earlier/other exchange is not a range for the
// current poll.  Keep a small absolute guard around the hardware RX window so
// a rejected frame cannot make the tag wait forever when it re-arms RX.
#define RESP_RX_GUARD_UUS           2000
// Anchor listen window (~102 ms) so uwb_responder_tick() always returns and
// loop() stays alive even when no tag is transmitting.
#define RESP_LISTEN_TIMEOUT_UUS     100000
// Hardware timeout events should normally end these waits.  The independent
// host-side deadlines are a last line of defence against a radio left in an
// unexpected state: one stuck anchor must not stop answering forever.
#define RESP_LISTEN_GUARD_US         10000
#define RESP_TX_COMPLETE_TIMEOUT_US  10000

// ---- frame layout ----
#define ALL_MSG_COMMON_LEN      10
#define ALL_MSG_SN_IDX          2
#define TARGET_ID_IDX           10        // poll frame: which anchor should answer
#define RESP_MSG_POLL_RX_TS_IDX 10
#define RESP_MSG_RESP_TX_TS_IDX 14
#define RESP_ANCHOR_ID_IDX      18        // response frame: anchor that answered
// RESP_MSG_TS_LEN and the get_rx_timestamp_u64 / resp_msg_{get,set}_ts helpers
// come from the library (dw3000_shared_defines.h / dw3000_shared_functions.h).

// The DW3000 appends a 2-byte FCS over the last two bytes of every frame, and
// dwt_writetxfctrl() is given the length INCLUDING that FCS. So payload must
// stop two bytes early: the poll is 13 bytes = 10 header + 1 target id + 2 FCS.
// (The stock 12-byte poll leaves no room for the id - writing it at index 10
// only to have the hardware CRC overwrite it was the old multi-anchor bug.)
// resp = 21 bytes = 10 header + 4 poll_rx_ts + 4 resp_tx_ts + 1 anchor id + 2 FCS.
// Returning the ID is essential: a tag must never assign a late/wrong-anchor
// response to d1 or d2 just because the common header happens to match.
#if defined(ROLE_TAG)
static uint8_t tx_poll_msg[] = {0x41,0x88,0,0xCA,0xDE,'W','A','V','E',0xE0,0,0,0};
static uint8_t rx_resp_msg[] = {0x41,0x88,0,0xCA,0xDE,'V','E','W','A',0xE1,0,0,0,0,0,0,0,0,0,0,0};
#else
static uint8_t rx_poll_msg[] = {0x41,0x88,0,0xCA,0xDE,'W','A','V','E',0xE0,0,0,0};
static uint8_t tx_resp_msg[] = {0x41,0x88,0,0xCA,0xDE,'V','E','W','A',0xE1,0,0,0,0,0,0,0,0,0,0,0};
#endif

#define RX_BUF_LEN 21
static uint8_t  rx_buffer[RX_BUF_LEN];
static uint32_t status_reg = 0;
static uint8_t  frame_seq_nb = 0;

static bool timeExpired(uint32_t deadline_us) {
    return static_cast<int32_t>(micros() - deadline_us) >= 0;
}

static void clearRadioEvents() {
    dwt_write32bitreg(SYS_STATUS_ID, SYS_STATUS_ALL_TX |
                       SYS_STATUS_ALL_RX_GOOD |
                       SYS_STATUS_ALL_RX_TO |
                       SYS_STATUS_ALL_RX_ERR);
}

// The DW3000 fast command returns the transceiver to IDLE even when an RX/TX
// operation ended abnormally.  Clearing all latched events afterwards keeps a
// stale completion bit from being interpreted as the next exchange's result.
static void recoverRadio() {
    dwt_forcetrxoff();
    clearRadioEvents();
}

// ---------------------------------------------------------------------
//  SPI bring-up. Three details here were each paid for in debugging time
//  (see problem.md and test_dw3000/):
//   1. The pins MUST be the FSPI IOMUX set (SCK12/MOSI11/MISO13/CS10).
//      Through the GPIO matrix, extended reads come back bit-shifted and
//      every register write fails - while a 1-byte DEV_ID read still looks
//      fine, so the fault only surfaces later as a PLL LOCK error.
//   2. We init the Arduino SPI bus ourselves with ss=-1 and hand the library
//      the CS pin via _ss. Its own spiSelect() writes DW1000-legacy registers
//      that corrupt a DW3000.
//   3. RSTn is open-drain: pull it LOW, then release to float. Never drive HIGH.
// ---------------------------------------------------------------------
static void spiStart() {
    SPI.begin(DW_PIN_SCK, DW_PIN_MISO, DW_PIN_MOSI, -1);   // hardware SPI, manual CS
    pinMode(DW_PIN_CS, OUTPUT); digitalWrite(DW_PIN_CS, HIGH);
    _ss = DW_PIN_CS;                                       // CS pin the library drives
    pinMode(DW_PIN_IRQ, INPUT);
    pinMode(DW_PIN_RST, OUTPUT); digitalWrite(DW_PIN_RST, LOW); delay(2);
    pinMode(DW_PIN_RST, INPUT); delay(2);                  // INIT_RC -> IDLE_RC
}

// =====================================================================
bool uwb_begin() {
    spiStart();

    if (!dwt_checkidlerc())                       return false;
    if (dwt_initialise(DWT_DW_INIT) == DWT_ERROR) return false;
    if (dwt_configure(&config))                   return false;

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
#if defined(ROLE_TAG)
bool uwb_range(uint8_t anchor_id, double &dist_m) {
    // The responder echoes this sequence in its response.  Along with the
    // anchor ID it prevents a valid but late response from an earlier poll
    // being credited to the current ranging cycle.
    const uint8_t poll_sequence = frame_seq_nb;
    tx_poll_msg[ALL_MSG_SN_IDX] = poll_sequence;
    tx_poll_msg[TARGET_ID_IDX]  = anchor_id;

    // Clear every completion/error bit which could have been left by a prior
    // exchange.  In particular, a stale RX timeout must not satisfy the wait
    // below before this poll has even left the antenna.
    recoverRadio();
    // A previous mismatched frame may have shortened this timeout while RX
    // was re-armed.  Restore the normal W4R window for every fresh poll.
    dwt_setrxtimeout(RESP_RX_TIMEOUT_UUS);
    dwt_writetxdata(sizeof(tx_poll_msg), tx_poll_msg, 0);
    dwt_writetxfctrl(sizeof(tx_poll_msg), 0, 1);
    if (dwt_starttx(DWT_START_TX_IMMEDIATE | DWT_RESPONSE_EXPECTED) != DWT_SUCCESS) {
        recoverRadio();
        return false;
    }
    frame_seq_nb++;

    // dwt_starttx(W4R) opens the first RX window automatically.  A late frame
    // from a previous retry can still be CRC-valid; reject it by ID+sequence
    // and re-arm RX instead of turning this whole current range into a miss.
    const uint32_t rx_deadline = micros() + POLL_TX_TO_RESP_RX_DLY_UUS +
                                 RESP_RX_TIMEOUT_UUS + RESP_RX_GUARD_UUS;
    while (true) {
        while (!((status_reg = dwt_read32bitreg(SYS_STATUS_ID)) &
                 (SYS_STATUS_RXFCG_BIT_MASK | SYS_STATUS_ALL_RX_TO | SYS_STATUS_ALL_RX_ERR))) {
            if (static_cast<int32_t>(micros() - rx_deadline) >= 0) {
                recoverRadio();
                return false;
            }
        }

        if (!(status_reg & SYS_STATUS_RXFCG_BIT_MASK)) {
            recoverRadio();
            return false;
        }

        dwt_write32bitreg(SYS_STATUS_ID, SYS_STATUS_RXFCG_BIT_MASK);
        uint32_t frame_len = dwt_read32bitreg(RX_FINFO_ID) & RXFLEN_MASK;
        if (frame_len == sizeof(rx_resp_msg) && frame_len <= sizeof(rx_buffer)) {
            dwt_readrxdata(rx_buffer, frame_len, 0);
            const uint8_t response_sequence = rx_buffer[ALL_MSG_SN_IDX];
            rx_buffer[ALL_MSG_SN_IDX] = 0;
            if (memcmp(rx_buffer, rx_resp_msg, ALL_MSG_COMMON_LEN) == 0 &&
                response_sequence == poll_sequence &&
                rx_buffer[RESP_ANCHOR_ID_IDX] == anchor_id) {
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

        // A good-but-unrelated frame stops DW3000 RX.  Clear its remaining
        // good-frame bits, then re-enable RX only for the remaining absolute
        // wait time.  This prevents an old reply from poisoning a retry.
        // A correct frame ends RX.  Explicitly return to IDLE before asking
        // for another receive window, otherwise a recovery after a bad/late
        // response can leave this tag's next poll in a stale RX state.
        recoverRadio();
        const int32_t remaining_uus = static_cast<int32_t>(rx_deadline - micros());
        if (remaining_uus <= 0) return false;
        dwt_setrxtimeout(static_cast<uint32_t>(remaining_uus));
        if (dwt_rxenable(DWT_START_RX_IMMEDIATE) != DWT_SUCCESS) {
            recoverRadio();
            return false;
        }
    }
}
#endif  // ROLE_TAG

// ------------------------------------------------------------- ANCHOR
#if defined(ROLE_ANCHOR)
static UwbResponderStats responderStats;

const UwbResponderStats &uwb_responder_stats() {
    return responderStats;
}

static void recoverResponderRadio() {
    recoverRadio();
    responderStats.recoveries++;
}

bool uwb_responder_tick() {
    // Start every listen cycle from a known IDLE state.  A receiver can be
    // left active after an error/timeout and a delayed responder TX can be
    // cancelled by hardware; both used to make one anchor silently stop
    // answering while the other one continued.
    recoverRadio();
    dwt_setrxtimeout(RESP_LISTEN_TIMEOUT_UUS);
    if (dwt_rxenable(DWT_START_RX_IMMEDIATE) != DWT_SUCCESS) {
        responderStats.rx_error++;
        recoverResponderRadio();
        return false;
    }

    const uint32_t listenDeadline = micros() + RESP_LISTEN_TIMEOUT_UUS + RESP_LISTEN_GUARD_US;
    while (!((status_reg = dwt_read32bitreg(SYS_STATUS_ID)) &
             (SYS_STATUS_RXFCG_BIT_MASK | SYS_STATUS_ALL_RX_TO | SYS_STATUS_ALL_RX_ERR))) {
        if (timeExpired(listenDeadline)) {
            responderStats.rx_watchdog++;
            recoverResponderRadio();
            return false;
        }
    }

    if (!(status_reg & SYS_STATUS_RXFCG_BIT_MASK)) {   // silence or a corrupt frame
        if (status_reg & SYS_STATUS_ALL_RX_TO) responderStats.rx_timeout++;
        else                                   responderStats.rx_error++;
        recoverResponderRadio();
        return false;
    }

    responderStats.rx_good++;
    dwt_write32bitreg(SYS_STATUS_ID, SYS_STATUS_ALL_RX_GOOD);
    uint32_t frame_len = dwt_read32bitreg(RX_FINFO_ID) & RXFLEN_MASK;
    if (frame_len > sizeof(rx_buffer) || frame_len <= TARGET_ID_IDX) {
        responderStats.ignored++;
        recoverResponderRadio();
        return false;
    }

    dwt_readrxdata(rx_buffer, frame_len, 0);
    const uint8_t poll_sequence = rx_buffer[ALL_MSG_SN_IDX];
    uint8_t target = rx_buffer[TARGET_ID_IDX];
    rx_buffer[ALL_MSG_SN_IDX] = 0;

    // answer only polls with our common header AND our anchor id
    if (memcmp(rx_buffer, rx_poll_msg, ALL_MSG_COMMON_LEN) != 0 || target != ANCHOR_ID) {
        responderStats.ignored++;
        recoverResponderRadio();
        return false;
    }
    responderStats.addressed++;

    uint64_t poll_rx_ts   = get_rx_timestamp_u64();
    uint32_t resp_tx_time = (poll_rx_ts + (POLL_RX_TO_RESP_TX_DLY_UUS * UUS_TO_DWT_TIME)) >> 8;
    dwt_setdelayedtrxtime(resp_tx_time);
    uint64_t resp_tx_ts = (((uint64_t)(resp_tx_time & 0xFFFFFFFEUL)) << 8) + UWB_ANT_DLY;

    resp_msg_set_ts(&tx_resp_msg[RESP_MSG_POLL_RX_TS_IDX], poll_rx_ts);
    resp_msg_set_ts(&tx_resp_msg[RESP_MSG_RESP_TX_TS_IDX], resp_tx_ts);
    tx_resp_msg[RESP_ANCHOR_ID_IDX] = ANCHOR_ID;
    tx_resp_msg[ALL_MSG_SN_IDX] = poll_sequence;

    dwt_writetxdata(sizeof(tx_resp_msg), tx_resp_msg, 0);
    dwt_writetxfctrl(sizeof(tx_resp_msg), 0, 1);
    dwt_write32bitreg(SYS_STATUS_ID, SYS_STATUS_ALL_TX);
    if (dwt_starttx(DWT_START_TX_DELAYED) != DWT_SUCCESS) {               // turnaround missed
        responderStats.tx_start_error++;
        recoverResponderRadio();
        return false;
    }

    const uint32_t txDeadline = micros() + RESP_TX_COMPLETE_TIMEOUT_US;
    while (!(dwt_read32bitreg(SYS_STATUS_ID) & SYS_STATUS_TXFRS_BIT_MASK)) {
        if (timeExpired(txDeadline)) {
            responderStats.tx_watchdog++;
            recoverResponderRadio();
            return false;
        }
    }
    dwt_write32bitreg(SYS_STATUS_ID, SYS_STATUS_ALL_TX);
    frame_seq_nb++;
    return true;
}
#endif  // ROLE_ANCHOR
