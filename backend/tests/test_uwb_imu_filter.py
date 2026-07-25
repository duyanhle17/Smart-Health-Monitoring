import math
import unittest

from backend.core.uwb_imu_filter import UwbImuFilter, UwbImuFilterConfig


def ranges_for(point, anchors=((0.0, 0.0), (2.0, 0.0))):
    return tuple(math.hypot(point[0] - anchor[0], point[1] - anchor[1]) for anchor in anchors)


class UwbImuFilterTests(unittest.TestCase):
    def make_filter(self, **config_values):
        config = UwbImuFilterConfig(
            range_std_m=0.05,
            initial_position_std_m=1.0,
            initial_velocity_std_mps=1.0,
            process_accel_std_mps2=0.4,
            imu_accel_std_mps2=0.1,
            hold_seconds=1.0,
            **config_values,
        )
        return UwbImuFilter(((0.0, 0.0), (2.0, 0.0)), allowed_side=1, config=config)

    def bootstrap(self, tracker, point=(0.8, 1.0), timestamp=0.0):
        d1, d2 = ranges_for(point)
        return tracker.update_ranges(d1, d2, timestamp_s=timestamp)

    def test_bootstrap_uses_declared_side_and_direct_two_range_fix(self):
        tracker = self.make_filter()
        result = self.bootstrap(tracker, point=(0.8, 1.0))

        self.assertTrue(result.valid)
        self.assertTrue(result.accepted_uwb)
        self.assertFalse(result.held)
        self.assertEqual(result.reason, "uwb_bootstrap")
        self.assertAlmostEqual(result.position_m[0], 0.8, places=5)
        self.assertAlmostEqual(result.position_m[1], 1.0, places=5)
        self.assertGreater(result.position_m[1], 0.0)
        self.assertIsNotNone(result.nis)

    def test_imu_alone_never_publishes_a_coordinate_and_hold_expires(self):
        tracker = self.make_filter()

        prediction = tracker.predict(
            timestamp_s=0.0,
            body_linear_accel_mps2=(1.0, 0.0),
            map_heading_deg=0.0,
            imu_ok=True,
            heading_calibrated=True,
        )
        self.assertTrue(prediction["imu_used"])
        self.assertFalse(tracker.estimate(now_s=0.1).valid)
        self.assertIsNone(tracker.estimate(now_s=0.1).position_m)

        accepted = self.bootstrap(tracker, timestamp=0.2)
        self.assertTrue(accepted.valid)
        held = tracker.step(
            timestamp_s=0.8,
            body_linear_accel_mps2=(0.0, 0.0),
            map_heading_deg=0.0,
            imu_ok=True,
            heading_calibrated=True,
        )
        self.assertTrue(held.valid)
        self.assertTrue(held.held)
        self.assertFalse(held.accepted_uwb)

        expired = tracker.estimate(now_s=1.21)
        self.assertFalse(expired.valid)
        self.assertIsNone(expired.position_m)
        self.assertEqual(expired.reason, "uwb_hold_expired")

    def test_acceleration_prediction_requires_calibrated_trusted_heading(self):
        # A trusted 90-degree map heading rotates body +x acceleration to +y.
        trusted = self.make_filter(max_prediction_dt_s=2.0)
        self.bootstrap(trusted)
        trusted.predict(
            timestamp_s=1.0,
            body_linear_accel_mps2=(1.0, 0.0),
            map_heading_deg=90.0,
            imu_ok=True,
            heading_calibrated=True,
            heading_accuracy_deg=5.0,
        )
        trusted_state = trusted.state_vector()
        self.assertAlmostEqual(trusted_state[0], 0.8, places=4)
        self.assertAlmostEqual(trusted_state[1], 1.5, places=4)
        self.assertAlmostEqual(trusted_state[2], 0.0, places=4)
        self.assertAlmostEqual(trusted_state[3], 1.0, places=4)

        untrusted = self.make_filter(max_prediction_dt_s=2.0)
        self.bootstrap(untrusted)
        diagnostic = untrusted.predict(
            timestamp_s=1.0,
            body_linear_accel_mps2=(1.0, 0.0),
            map_heading_deg=90.0,
            imu_ok=True,
            heading_calibrated=False,
        )
        untrusted_state = untrusted.state_vector()
        self.assertFalse(diagnostic["imu_used"])
        self.assertEqual(diagnostic["imu_reason"], "map_heading_uncalibrated")
        self.assertAlmostEqual(untrusted_state[0], 0.8, places=4)
        self.assertAlmostEqual(untrusted_state[1], 1.0, places=4)
        self.assertAlmostEqual(untrusted_state[2], 0.0, places=4)
        self.assertAlmostEqual(untrusted_state[3], 0.0, places=4)

        disabled = self.make_filter(use_imu=False, max_prediction_dt_s=2.0)
        self.bootstrap(disabled)
        disabled_diagnostic = disabled.predict(
            timestamp_s=1.0,
            body_linear_accel_mps2=(1.0, 0.0),
            map_heading_deg=0.0,
            imu_ok=True,
            heading_calibrated=True,
        )
        self.assertFalse(disabled_diagnostic["imu_used"])
        self.assertEqual(disabled_diagnostic["imu_reason"], "imu_disabled")
        self.assertAlmostEqual(disabled.state_vector()[0], 0.8, places=4)

    def test_stationary_zupt_reduces_velocity_without_refreshing_uwb_age(self):
        tracker = self.make_filter()
        accepted = self.bootstrap(tracker)
        self.assertEqual(accepted.uwb_age_s, 0.0)

        # A deterministic unit-test setup: inject only an internal velocity
        # state after a legitimate UWB bootstrap, then ask a trusted BNO still
        # cue to estimate velocity zero.  The cue must not extend the UWB hold.
        tracker._state[2] = 1.4
        tracker._state[3] = -0.8
        before_speed = math.hypot(*tracker.state_vector()[2:])
        result = tracker.apply_stationary_zupt(
            timestamp_s=0.2,
            stationary=True,
            imu_ok=True,
            stationary_trusted=True,
        )
        after_speed = math.hypot(*tracker.state_vector()[2:])
        self.assertTrue(result.valid)
        self.assertTrue(result.held)
        self.assertTrue(result.zupt_applied)
        self.assertLess(after_speed, before_speed * 0.2)
        self.assertAlmostEqual(tracker.last_accepted_uwb_s, 0.0)

        self.assertFalse(tracker.estimate(now_s=1.01).valid)

    def test_nlos_or_large_innovation_is_rejected_and_only_held_fix_is_returned(self):
        tracker = self.make_filter()
        initial = self.bootstrap(tracker)
        self.assertTrue(initial.valid)
        initial_position = initial.position_m

        # A physically valid but implausibly distant range pair must not drag
        # the live coordinate across the map just because it intersects.
        far_d1, far_d2 = ranges_for((1.7, 3.0))
        rejected = tracker.update_ranges(far_d1, far_d2, timestamp_s=0.2)
        self.assertFalse(rejected.accepted_uwb)
        self.assertTrue(rejected.valid)
        self.assertTrue(rejected.held)
        self.assertTrue(rejected.nlos_suspected)
        self.assertIn(rejected.reason, {"range_residual_too_large", "innovation_gate_rejected"})
        self.assertAlmostEqual(rejected.position_m[0], initial_position[0], places=4)
        self.assertAlmostEqual(rejected.position_m[1], initial_position[1], places=4)

        flagged = tracker.update_ranges(*ranges_for((0.9, 1.0)), timestamp_s=0.3, nlos_flags=(True, False))
        self.assertFalse(flagged.accepted_uwb)
        self.assertTrue(flagged.valid)
        self.assertTrue(flagged.nlos_suspected)
        self.assertEqual(flagged.reason, "nlos_flagged")

    def test_direct_range_update_moves_state_and_keeps_two_range_atomicity(self):
        tracker = self.make_filter(innovation_gate_chi2=20.0)
        self.bootstrap(tracker, point=(0.8, 1.0))
        d1, d2 = ranges_for((1.05, 1.0))
        result = tracker.update_ranges(d1, d2, timestamp_s=0.25)

        self.assertTrue(result.valid)
        self.assertTrue(result.accepted_uwb)
        self.assertEqual(result.reason, "uwb_update")
        self.assertGreater(result.position_m[0], 0.8)
        self.assertLess(result.position_m[0], 1.06)
        self.assertIsNotNone(result.nis)
        self.assertIn("innovation_m", result.details)

    def test_low_geometry_does_not_bootstrap_a_fake_2d_track_by_default(self):
        tracker = self.make_filter()
        # At the midpoint on the anchor line, height is zero.  With two
        # anchors that cannot initialise the unobserved perpendicular axis.
        result = tracker.update_ranges(1.0, 1.0, timestamp_s=0.0)
        self.assertFalse(result.valid)
        self.assertFalse(result.accepted_uwb)
        self.assertEqual(result.reason, "bootstrap_low_geometry")
        self.assertTrue(result.low_geometry)

    def test_bad_or_untrusted_range_never_bootstraps(self):
        tracker = self.make_filter()
        untrusted = tracker.update_ranges(1.2, 1.3, timestamp_s=0.0, range_trusted=(True, False))
        self.assertFalse(untrusted.valid)
        self.assertEqual(untrusted.reason, "range_untrusted")

        invalid = tracker.update_ranges(0.1, 0.1, timestamp_s=0.1)
        self.assertFalse(invalid.valid)
        self.assertEqual(invalid.reason, "ranges_shorter_than_baseline")

    def test_out_of_order_uwb_packet_is_not_applied(self):
        tracker = self.make_filter()
        self.bootstrap(tracker, timestamp=1.0)
        original = tracker.state_vector()
        stale = tracker.update_ranges(*ranges_for((1.5, 1.0)), timestamp_s=0.5)
        self.assertFalse(stale.accepted_uwb)
        self.assertTrue(stale.valid)
        self.assertTrue(stale.held)
        self.assertEqual(stale.reason, "out_of_order_timestamp")
        self.assertEqual(tracker.state_vector(), original)

    def test_declared_anchor_side_remains_an_invariant_after_bootstrap(self):
        tracker = self.make_filter(max_prediction_dt_s=2.0, max_imu_accel_mps2=5.0)
        self.bootstrap(tracker, point=(1.0, 0.2), timestamp=0.0)
        before = tracker.state_vector()

        # A physically implausible/mis-mounted IMU acceleration could try to
        # push the state through the A1-A2 baseline. With two anchors that
        # would become indistinguishable from the mirror solution, so the
        # filter must keep the declared +side instead of crossing or clamping.
        diagnostic = tracker.predict(
            timestamp_s=1.0,
            body_linear_accel_mps2=(0.0, -5.0),
            map_heading_deg=0.0,
            imu_ok=True,
            heading_calibrated=True,
            heading_accuracy_deg=2.0,
        )
        after = tracker.state_vector()

        self.assertTrue(diagnostic["side_constrained"])
        self.assertEqual(after, before)
        self.assertGreaterEqual(after[1], 0.0)


if __name__ == "__main__":
    unittest.main()
