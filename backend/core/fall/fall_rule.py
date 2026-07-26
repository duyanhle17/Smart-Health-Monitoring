"""Deterministic fall gate driven by firmware |a| extremes.

The ML fall model (fall_state.py) needs a 5 s window at a telemetry rate the
uplink does not deliver, and real firmware never sends ``fall_alert`` - so for
hardware workers the existing path could never raise a fall.  This rule is the
first trigger fed by what the tag actually measures: the firmware tracks
max/min |a| at the BNO event rate over a ~2 s hold window (``acc_peak`` /
``acc_valley``, in g), so a 50-100 ms impact between two posts stays visible.

The classic fall signature is a free-fall dip (|a| well below 1 g while the
body is dropping) followed by an impact spike.  A very hard impact alone also
triggers, because a collapse from standing has no free-fall phase.

Thresholds are conservative literature starting points and MUST be tuned with
drop tests on the real helmet before the alarm is relied on.
"""

import math

# |a| in g. A fall impact is typically 3-6 g at the head/torso; normal gait
# stays under ~2 g and a jump landing reaches ~2-3 g.
IMPACT_PEAK_G = 2.8
# An impact this hard is alarm-worthy even without a preceding dip.
HARD_IMPACT_PEAK_G = 4.5
# Free-fall dip: |a| approaches 0 g while dropping. Walking never goes
# below ~0.6 g for a full 50 ms accelerometer sample.
FREEFALL_VALLEY_G = 0.45
# BNO08x accelerometer full scale is 8 g (16 g absolute worst case);
# anything beyond is transport garbage, not physics.
MAX_PLAUSIBLE_PEAK_G = 16.0
# Firmware holds an extreme for ~2 s; allow uplink latency on top. Older
# evidence has already been reported by earlier packets.
MAX_EVIDENCE_AGE_MS = 4000.0
# The dip must precede the impact. Ages are per-post snapshots of the same
# clock, so a small tolerance covers the case where both extremes come from
# the same accelerometer sample.
ORDER_TOLERANCE_MS = 60.0
# How long the app layer keeps fall_status=FALL after a rule trigger, matching
# the ML path's FALL_HOLD_DURATION so the dashboard alarm cannot flicker off
# while the worker is still down.
FALL_RULE_HOLD_S = 15.0


def _finite(value):
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def _fresh_age(age_ms):
    """None = firmware omitted the age; ages are trusted only when sane."""
    age = _finite(age_ms)
    if age is None:
        return None
    if age < 0.0 or age > MAX_EVIDENCE_AGE_MS:
        return False
    return age


def evaluate_fall_rule(acc_peak, acc_valley, peak_age_ms=None, valley_age_ms=None):
    """Classify one telemetry packet's |a| extremes.

    Returns a JSON-safe dict; ``triggered`` is the only decision output, the
    rest is diagnostics for the dashboard and for threshold tuning.  Absent or
    malformed evidence never triggers and never raises.
    """
    result = {
        "triggered": False,
        "impact": False,
        "hard_impact": False,
        "freefall": False,
        "order_ok": None,
        "reason": "no_peak",
        "peak_g": None,
        "valley_g": None,
    }

    peak = _finite(acc_peak)
    if peak is None:
        return result
    if peak <= 0.0 or peak > MAX_PLAUSIBLE_PEAK_G:
        result["reason"] = "implausible_peak"
        return result
    result["peak_g"] = round(peak, 2)

    peak_age = _fresh_age(peak_age_ms)
    if peak_age is False:
        result["reason"] = "stale_peak"
        return result

    result["impact"] = peak >= IMPACT_PEAK_G
    result["hard_impact"] = peak >= HARD_IMPACT_PEAK_G

    valley = _finite(acc_valley)
    valley_age = _fresh_age(valley_age_ms)
    if valley is not None and 0.0 <= valley <= FREEFALL_VALLEY_G and valley_age is not False:
        result["freefall"] = True
        result["valley_g"] = round(valley, 2)
    elif valley is not None and valley >= 0.0:
        result["valley_g"] = round(valley, 2)

    # Dip-then-impact ordering: the valley must be at least as old as the
    # peak. Unknown ages leave the order unverified rather than blocking.
    if isinstance(peak_age, float) and isinstance(valley_age, float):
        result["order_ok"] = valley_age + ORDER_TOLERANCE_MS >= peak_age
    order_ok = result["order_ok"] is not False

    if result["hard_impact"]:
        result["triggered"] = True
        result["reason"] = "hard_impact"
    elif result["impact"] and result["freefall"] and order_ok:
        result["triggered"] = True
        result["reason"] = "freefall_then_impact"
    elif result["impact"]:
        result["reason"] = "impact_without_freefall"
    elif result["freefall"]:
        result["reason"] = "freefall_without_impact"
    else:
        result["reason"] = "below_thresholds"
    return result


__all__ = ["evaluate_fall_rule", "FALL_RULE_HOLD_S"]
