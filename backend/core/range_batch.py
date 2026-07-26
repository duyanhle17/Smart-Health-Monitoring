"""Parse the optional ``telemetry.ranges`` backlog array from the tag.

Contract with the firmware (B1 of the positioning roadmap): the tag keeps
sending its freshest median pair in the flat ``d1``/``d2``/``range_seq``/
``range_age_ms`` fields, and MAY additionally attach

    "ranges": [
        {"d1": 1.234, "d2": 2.345, "seq": 41, "age_ms": 612,
         "nlos_d1": false, "nlos_d2": true, "trusted": true},
        ...
    ]

listing pairs measured since the previous successful POST that never got
their own packet (the one-slot snapshot queue coalesces under HTTP latency).
Backlog entries must carry sequence numbers BELOW the flat ``range_seq``;
the engine's per-worker sequence tracking rejects anything else, so a
malformed or malicious array can replay nothing.

This parser is deliberately strict per item and forgiving overall: a garbage
entry drops that entry, a garbage array drops the array, and the packet's
flat live pair is never affected.
"""

from __future__ import annotations

import math
from typing import Any, List, Optional

# Bound the per-packet work: at the tag's 5 Hz pair rate even a multi-second
# outage fits comfortably; anything longer is stale for a live dashboard.
MAX_BATCH_ITEMS = 16
_MIN_RANGE_M = 0.01
_MAX_RANGE_M = 60.0


def _finite(value: Any) -> Optional[float]:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    result = float(value)
    return result if math.isfinite(result) else None


def _sequence(value: Any) -> Optional[int]:
    number = _finite(value)
    if number is None or number < 0 or not math.isclose(number, round(number), abs_tol=1e-6):
        return None
    return int(round(number))


def parse_range_batch(telemetry: Any, max_items: int = MAX_BATCH_ITEMS) -> List[dict]:
    """Return validated backlog pairs sorted oldest-first by sequence.

    Each returned item has keys: ``d1``, ``d2`` (metres), ``seq`` (int),
    ``age_ms`` (float >= 0), ``nlos`` ((bool, bool)), ``trusted`` (bool).
    Duplicated sequences keep the first occurrence.  When the array holds
    more than ``max_items`` valid entries only the newest ones are kept.
    """
    if not isinstance(telemetry, dict):
        return []
    raw = telemetry.get("ranges")
    if not isinstance(raw, list):
        return []
    live_seq = _sequence(telemetry.get("range_seq"))
    if live_seq is None:
        # Without the live pair's sequence there is no ceiling proving a
        # backlog entry is older than the live pair.  Accepting one would let
        # a spoofed/oversized seq advance the engine's per-worker sequence
        # state and lock out every subsequent live pair until the tag
        # reboots.  A missing/garbage live seq drops the whole array.
        return []
    by_seq: dict[int, dict] = {}
    for entry in raw:
        if not isinstance(entry, dict):
            continue
        d1 = _finite(entry.get("d1"))
        d2 = _finite(entry.get("d2"))
        seq = _sequence(entry.get("seq"))
        age_ms = _finite(entry.get("age_ms"))
        if d1 is None or d2 is None or seq is None or age_ms is None or age_ms < 0.0:
            continue
        if not (_MIN_RANGE_M <= d1 <= _MAX_RANGE_M and _MIN_RANGE_M <= d2 <= _MAX_RANGE_M):
            continue
        if seq >= live_seq:
            # The backlog may only contain pairs OLDER than the packet's live
            # pair; the live pair itself travels in the flat fields.
            continue
        if seq in by_seq:
            continue
        by_seq[seq] = {
            "d1": d1,
            "d2": d2,
            "seq": seq,
            "age_ms": age_ms,
            "nlos": (bool(entry.get("nlos_d1")), bool(entry.get("nlos_d2"))),
            "trusted": bool(entry.get("trusted", True)),
        }
    ordered = [by_seq[key] for key in sorted(by_seq)]
    if len(ordered) > max_items:
        ordered = ordered[-max_items:]
    return ordered
