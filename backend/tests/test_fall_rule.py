"""Unit tests for the deterministic acc_peak/acc_valley fall gate."""

import pytest

from backend.core.fall.fall_rule import evaluate_fall_rule


def test_classic_fall_dip_then_impact_triggers():
    # Free-fall dip 300 ms before a 3.5 g impact: the canonical signature.
    result = evaluate_fall_rule(3.5, 0.30, peak_age_ms=200, valley_age_ms=500)
    assert result["triggered"] is True
    assert result["reason"] == "freefall_then_impact"
    assert result["impact"] and result["freefall"] and result["order_ok"]


def test_walking_never_triggers():
    result = evaluate_fall_rule(1.8, 0.75, peak_age_ms=100, valley_age_ms=400)
    assert result["triggered"] is False
    assert result["reason"] == "below_thresholds"


def test_jump_landing_impact_without_deep_freefall():
    # 3 g landing but the valley never reached free-fall depth.
    result = evaluate_fall_rule(3.0, 0.55, peak_age_ms=150, valley_age_ms=350)
    assert result["triggered"] is False
    assert result["reason"] == "impact_without_freefall"


def test_hard_impact_alone_triggers():
    # A collapse from standing has no free-fall phase; 5 g alone is enough.
    result = evaluate_fall_rule(5.0, 0.9, peak_age_ms=100, valley_age_ms=50)
    assert result["triggered"] is True
    assert result["reason"] == "hard_impact"


def test_freefall_without_impact_does_not_trigger():
    # Dropping the helmet onto a soft surface: dip but no spike.
    result = evaluate_fall_rule(2.0, 0.2, peak_age_ms=100, valley_age_ms=600)
    assert result["triggered"] is False
    assert result["reason"] == "freefall_without_impact"


def test_inverted_order_blocks_moderate_impact():
    # Peak clearly before the dip (valley much newer): not dip-then-impact.
    result = evaluate_fall_rule(3.2, 0.3, peak_age_ms=1500, valley_age_ms=100)
    assert result["triggered"] is False
    assert result["order_ok"] is False


def test_same_sample_order_tolerance():
    # Both extremes from (nearly) the same accelerometer sample still count.
    result = evaluate_fall_rule(3.2, 0.3, peak_age_ms=200, valley_age_ms=170)
    assert result["triggered"] is True


def test_unknown_ages_still_trigger_combined_rule():
    # Old firmware without age fields: order is unverifiable, not blocking.
    result = evaluate_fall_rule(3.2, 0.3)
    assert result["triggered"] is True
    assert result["order_ok"] is None


def test_stale_evidence_does_not_trigger():
    result = evaluate_fall_rule(3.5, 0.3, peak_age_ms=10000, valley_age_ms=10500)
    assert result["triggered"] is False
    assert result["reason"] == "stale_peak"


def test_stale_valley_only_blocks_freefall():
    result = evaluate_fall_rule(3.5, 0.3, peak_age_ms=100, valley_age_ms=99000)
    assert result["triggered"] is False
    assert result["freefall"] is False


def test_transport_garbage_peak_rejected():
    result = evaluate_fall_rule(200.0, 0.0, peak_age_ms=10, valley_age_ms=10)
    assert result["triggered"] is False
    assert result["reason"] == "implausible_peak"


@pytest.mark.parametrize("peak,valley", [
    (None, None),
    ("not-a-number", 0.2),
    (float("nan"), 0.2),
    (float("inf"), 0.2),
    (-1.0, 0.2),
])
def test_malformed_evidence_never_triggers_or_raises(peak, valley):
    result = evaluate_fall_rule(peak, valley, peak_age_ms=10, valley_age_ms=20)
    assert result["triggered"] is False


def test_result_is_json_safe_diagnostics():
    result = evaluate_fall_rule(3.5, 0.30, peak_age_ms=200, valley_age_ms=500)
    assert result["peak_g"] == 3.5
    assert result["valley_g"] == 0.3
    import json
    json.dumps(result)
