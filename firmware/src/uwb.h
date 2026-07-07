#pragma once
#include <stdint.h>

// Initialise the DW3000 for the current role. Returns false on failure.
bool uwb_begin();

// TAG: single-sided two-way ranging against one anchor (by ID).
// On success sets dist_m and returns true; false on timeout/error.
bool uwb_range(uint8_t anchor_id, double &dist_m);

// ANCHOR: run one responder cycle. Call continuously in loop().
void uwb_responder_tick();
