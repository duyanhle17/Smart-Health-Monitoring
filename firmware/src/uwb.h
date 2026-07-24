#pragma once
#include <stdint.h>

// Only the function matching the build's role (ROLE_TAG / ROLE_ANCHOR) is
// compiled - the anchor half needs ANCHOR_ID, which a tag build does not have.

// Initialise the DW3000 for the current role. Returns false on failure.
bool uwb_begin();

// TAG: single-sided two-way ranging against one anchor (by ID, 1..NUM_ANCHORS).
// On success sets dist_m and returns true; false on timeout/error.
bool uwb_range(uint8_t anchor_id, double &dist_m);

// ANCHOR: run one responder cycle (blocks up to ~102 ms waiting for a poll).
// Returns true when it answered a poll addressed to this anchor.
bool uwb_responder_tick();
