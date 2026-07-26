#pragma once
#include <stdint.h>

// Only the function matching the build's role (ROLE_TAG / ROLE_ANCHOR) is
// compiled - the anchor half needs ANCHOR_ID, which a tag build does not have.

// Initialise the DW3000 for the current role. Returns false on failure.
bool uwb_begin();

// Per-sample link quality from the DW3000 CIA diagnostics of the accepted
// response frame. deltaDb = receive level minus first-path level: small when
// the direct path dominates (LOS), large when most energy arrived via
// reflections because the direct path is obstructed - exactly the case where
// an SS-TWR range reads long and no amount of median filtering can tell.
struct UwbRangeQuality {
    float deltaDb = 0.0f;
    bool  valid = false;        // diagnostics were readable for this frame
    bool  nlosSuspect = false;  // deltaDb > UWB_NLOS_DELTA_DB
};

// TAG: single-sided two-way ranging against one anchor (by ID, 1..NUM_ANCHORS).
// On success sets dist_m (and quality, when given) and returns true;
// false on timeout/error.
bool uwb_range(uint8_t anchor_id, double &dist_m, UwbRangeQuality *quality = nullptr);

// ANCHOR: run one responder cycle (blocks up to ~102 ms waiting for a poll).
// Returns true when it answered a poll addressed to this anchor.
bool uwb_responder_tick();

// Cumulative responder diagnostics.  They distinguish an RF miss from a
// recoverable radio-state failure (for example a delayed TX which never
// completes).  These are observation counters only; they never generate or
// substitute a range.
struct UwbResponderStats {
    uint32_t rx_good = 0;
    uint32_t addressed = 0;
    uint32_t ignored = 0;
    uint32_t rx_timeout = 0;
    uint32_t rx_error = 0;
    uint32_t rx_watchdog = 0;
    uint32_t tx_start_error = 0;
    uint32_t tx_watchdog = 0;
    uint32_t recoveries = 0;
};

// Valid for ROLE_ANCHOR builds.  The tag does not need responder statistics.
const UwbResponderStats &uwb_responder_stats();
