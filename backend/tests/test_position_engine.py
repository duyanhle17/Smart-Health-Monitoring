import math
import time
import unittest

from backend.core import position_engine as engine


class TwoAnchorPositionTests(unittest.TestCase):
    def setUp(self):
        engine.reset_smooth_state("test-worker")
        self.original_baseline = engine.ANCHOR_BASELINE_M
        self.original_d1_offset = engine.UWB_D1_OFFSET_M
        self.original_d2_offset = engine.UWB_D2_OFFSET_M
        self.original_d1_height_delta = engine.UWB_D1_HEIGHT_DELTA_M
        self.original_d2_height_delta = engine.UWB_D2_HEIGHT_DELTA_M
        self.original_calibrated = engine.UWB_CALIBRATED
        self.original_line_fallback = engine.UWB_LINE_FALLBACK
        self.original_line_tolerance = engine.LINE_FALLBACK_TOLERANCE_M
        self.original_two_d_fusion = engine.UWB_2D_FUSION
        self.original_two_d_require_metadata = engine.UWB_2D_REQUIRE_RANGE_METADATA
        self.original_work_area_point = engine.WORK_AREA_POINT
        self.original_imu_fusion = engine.UWB_IMU_FUSION
        self.original_imu_stride = engine.IMU_STRIDE_M
        self.original_imu_yaw_axis = engine.IMU_YAW_A1_TO_A2_DEG
        self.original_imu_forward_offset = engine.IMU_FORWARD_OFFSET_DEG
        self.original_imu_yaw_sign = engine.IMU_YAW_SIGN
        self.original_branch_min_height = engine.UWB_BRANCH_MIN_HEIGHT_M
        self.original_max_step_delta = engine.UWB_MAX_STEP_DELTA

    def tearDown(self):
        engine.ANCHOR_BASELINE_M = self.original_baseline
        engine.UWB_D1_OFFSET_M = self.original_d1_offset
        engine.UWB_D2_OFFSET_M = self.original_d2_offset
        engine.UWB_D1_HEIGHT_DELTA_M = self.original_d1_height_delta
        engine.UWB_D2_HEIGHT_DELTA_M = self.original_d2_height_delta
        engine.UWB_CALIBRATED = self.original_calibrated
        engine.UWB_LINE_FALLBACK = self.original_line_fallback
        engine.LINE_FALLBACK_TOLERANCE_M = self.original_line_tolerance
        engine.UWB_2D_FUSION = self.original_two_d_fusion
        engine.UWB_2D_REQUIRE_RANGE_METADATA = self.original_two_d_require_metadata
        engine.WORK_AREA_POINT = self.original_work_area_point
        engine.UWB_IMU_FUSION = self.original_imu_fusion
        engine.IMU_STRIDE_M = self.original_imu_stride
        engine.IMU_YAW_A1_TO_A2_DEG = self.original_imu_yaw_axis
        engine.IMU_FORWARD_OFFSET_DEG = self.original_imu_forward_offset
        engine.IMU_YAW_SIGN = self.original_imu_yaw_sign
        engine.UWB_BRANCH_MIN_HEIGHT_M = self.original_branch_min_height
        engine.UWB_MAX_STEP_DELTA = self.original_max_step_delta

    def enable_direct_fusion(self):
        engine.ANCHOR_BASELINE_M = 2.0
        engine.UWB_D1_OFFSET_M = 0.0
        engine.UWB_D2_OFFSET_M = 0.0
        engine.UWB_2D_FUSION = True
        engine.UWB_LINE_FALLBACK = False
        engine.UWB_2D_REQUIRE_RANGE_METADATA = True

    def direct_fix(self, worker_id, x, y, sequence, age_ms=0, epoch=None):
        d1, d2 = engine.distances_from_position(x, y, noise_std=0.0)
        return engine.estimate_position(
            worker_id, d1, d2,
            range_seq=sequence, range_age_ms=age_ms, range_epoch=epoch,
            imu_ok=True, stability=4,
            gyro_x=0.0, gyro_y=0.0, gyro_z=0.0,
            linear_accel=0.0,
        )

    def test_known_point_round_trips_on_allowed_side(self):
        expected_x, expected_y = 50.0, 70.0
        d1, d2 = engine.distances_from_position(expected_x, expected_y, noise_std=0.0)
        point = engine.dual_anchor_tracking(d1, d2)
        self.assertIsNotNone(point)
        # Simulator payloads round ranges to centimetres, so centimetre-scale
        # coordinate error is expected even when the geometry is exact.
        self.assertAlmostEqual(point[0], expected_x, places=1)
        self.assertAlmostEqual(point[1], expected_y, places=1)

    def test_mirror_branch_is_resolved_to_work_area_side(self):
        # (50, 70) and (50, -40) have the same two ranges for anchors on y=15.
        d1, d2 = engine.distances_from_position(50.0, 70.0, noise_std=0.0)
        point = engine.dual_anchor_tracking(d1, d2)
        self.assertGreater(point[1], 15.0)

    def test_impossible_ranges_are_rejected_not_projected_to_anchor_line(self):
        # With the default 6m anchor baseline, these circles cannot intersect.
        point = engine.estimate_position("test-worker", 0.20, 0.20)
        self.assertIsNone(point)
        status = engine.get_fix_status("test-worker")
        self.assertFalse(status["valid"])
        self.assertEqual(status["reason"], "ranges_shorter_than_anchor_baseline")

    def test_status_contains_real_metric_ranges_after_valid_fix(self):
        d1, d2 = engine.distances_from_position(40.0, 65.0, noise_std=0.0)
        point = engine.estimate_position("test-worker", d1, d2, yaw=45.0)
        self.assertIsNotNone(point)
        status = engine.get_fix_status("test-worker")
        self.assertTrue(status["valid"])
        self.assertTrue(math.isfinite(status["geometry_height_m"]))
        self.assertAlmostEqual(status["yaw_deg"], 45.0)

    def test_link_offsets_are_applied_before_two_anchor_geometry(self):
        # Deployment calibration: anchors are 2m apart and the tag is known to
        # be exactly midway (1m from each).  The raw links each have a fixed
        # RF/antenna bias, so the solver must see their corrected 1m ranges.
        engine.ANCHOR_BASELINE_M = 2.0
        engine.UWB_D1_OFFSET_M = 0.80
        engine.UWB_D2_OFFSET_M = 0.60
        engine.reset_smooth_state("offset-worker")

        point = engine.estimate_position("offset-worker", 0.20, 0.40)
        self.assertIsNotNone(point)
        status = engine.get_fix_status("offset-worker")
        self.assertTrue(status["valid"])
        self.assertAlmostEqual(status["raw_d1_m"], 0.20)
        self.assertAlmostEqual(status["raw_d2_m"], 0.40)
        self.assertAlmostEqual(status["d1_m"], 1.00)
        self.assertAlmostEqual(status["d2_m"], 1.00)
        # 2m physical baseline maps the known midpoint to logical (50, 15).
        self.assertAlmostEqual(point[0], 50.0)
        self.assertAlmostEqual(point[1], 15.0)
        self.assertTrue(status["low_geometry"])

    def test_surveyed_height_delta_is_removed_before_2d_geometry(self):
        # The anchors sit 0.60m above the worker tag. UWB reports slant
        # distance, while the two-dimensional map must solve floor distance.
        engine.ANCHOR_BASELINE_M = 2.0
        engine.UWB_D1_HEIGHT_DELTA_M = 0.60
        engine.UWB_D2_HEIGHT_DELTA_M = 0.60
        worker_id = "height-worker"
        engine.reset_smooth_state(worker_id)
        horizontal_d1 = math.hypot(1.0, 0.8)
        horizontal_d2 = math.hypot(1.0, 0.8)
        slant_d1 = math.hypot(horizontal_d1, 0.60)
        slant_d2 = math.hypot(horizontal_d2, 0.60)

        point = engine.estimate_position(worker_id, slant_d1, slant_d2)
        status = engine.get_fix_status(worker_id)

        self.assertIsNotNone(point)
        self.assertAlmostEqual(point[0], 50.0, places=2)
        self.assertAlmostEqual(point[1], 47.0, places=2)
        self.assertAlmostEqual(status["d1_slant_m"], slant_d1, places=3)
        self.assertAlmostEqual(status["d1_m"], horizontal_d1, places=3)

    def test_valid_uncalibrated_two_range_fix_is_publishable(self):
        # The exact, tape-measured baseline is sufficient to draw a live
        # estimate. RF calibration changes the confidence label, not whether
        # the UI receives a fabricated/default point instead of this result.
        engine.ANCHOR_BASELINE_M = 2.0
        engine.UWB_D1_OFFSET_M = 0.0
        engine.UWB_D2_OFFSET_M = 0.0
        engine.UWB_CALIBRATED = False
        worker_id = "uncalibrated-live-worker"
        engine.reset_smooth_state(worker_id)

        fix = engine.estimate_position(worker_id, 1.0, 1.0)
        status = engine.get_fix_status(worker_id)

        self.assertIsNotNone(fix)
        self.assertTrue(status["valid"])
        self.assertFalse(status["calibrated"])
        self.assertTrue(engine.is_publishable_uwb_fix(fix, status))

    def test_invalid_range_is_not_publishable(self):
        engine.ANCHOR_BASELINE_M = 2.0
        worker_id = "invalid-live-worker"
        engine.reset_smooth_state(worker_id)

        fix = engine.estimate_position(worker_id, 0.1, 0.1)
        status = engine.get_fix_status(worker_id)

        self.assertIsNone(fix)
        self.assertFalse(engine.is_publishable_uwb_fix(fix, status))

    def test_declared_line_fallback_is_opt_in_and_explicitly_degraded(self):
        # A 2m baseline with two 0.85m corrected ranges is 0.30m too short to
        # be a circle intersection, but is inside the explicitly bounded
        # on-line fallback tolerance.
        engine.ANCHOR_BASELINE_M = 2.0
        engine.UWB_D1_OFFSET_M = 0.0
        engine.UWB_D2_OFFSET_M = 0.0
        engine.UWB_LINE_FALLBACK = False
        worker_id = "line-worker"
        engine.reset_smooth_state(worker_id)

        self.assertIsNone(engine.estimate_position(worker_id, 0.85, 0.85))
        self.assertEqual(engine.get_fix_status(worker_id)["reason"], "ranges_shorter_than_anchor_baseline")

        engine.UWB_LINE_FALLBACK = True
        engine.reset_smooth_state(worker_id)
        point = engine.estimate_position(worker_id, 0.85, 0.85)
        status = engine.get_fix_status(worker_id)

        self.assertIsNotNone(point)
        self.assertTrue(status["valid"])
        self.assertTrue(status["degraded"])
        self.assertEqual(status["geometry_mode"], "line")
        self.assertTrue(status["perpendicular_unobserved"])
        self.assertAlmostEqual(status["line_position_m"], 1.0)
        self.assertAlmostEqual(point[0], 50.0)
        self.assertAlmostEqual(point[1], 15.0)
        self.assertTrue(engine.is_publishable_uwb_fix(point, status))

    def test_declared_line_fallback_rejects_a_large_gap_instead_of_fake_midpoint(self):
        engine.ANCHOR_BASELINE_M = 2.0
        engine.UWB_LINE_FALLBACK = True
        worker_id = "bad-line-worker"
        engine.reset_smooth_state(worker_id)

        point = engine.estimate_position(worker_id, 0.20, 0.20)
        status = engine.get_fix_status(worker_id)

        self.assertIsNone(point)
        self.assertFalse(status["valid"])
        self.assertEqual(status["reason"], "ranges_shorter_than_anchor_baseline")
        self.assertEqual(status["line_fallback_rejected"], "gap_too_large")

    def test_declared_line_fallback_projects_old_2d_state_onto_anchor_line(self):
        engine.ANCHOR_BASELINE_M = 2.0
        engine.UWB_LINE_FALLBACK = True
        worker_id = "line-projection-worker"
        engine.reset_smooth_state(worker_id)
        engine._smooth_state[worker_id] = {
            "x": 50.0,
            "y": 45.0,
            "vx": 0.0,
            "vy": 0.0,
            "at": time.monotonic() - 0.4,
        }

        point = engine.estimate_position(
            worker_id, 0.85, 0.85, stability=4,
            gyro_x=0.0, gyro_y=0.0, gyro_z=0.0,
        )

        self.assertIsNotNone(point)
        self.assertAlmostEqual(point[1], 15.0)
        self.assertAlmostEqual(point[0], 50.0)
        self.assertIn(worker_id, engine._line_range_windows)
        engine.reset_smooth_state(worker_id)
        self.assertNotIn(worker_id, engine._line_range_windows)

    def test_calibrated_imu_prior_can_hold_a_known_mirror_branch(self):
        # A point 0.2m off a 2m anchor line has two valid in-map solutions.
        # A previous *real UWB* fix plus one measured step selects the nearby
        # branch; the output remains the UWB circle intersection.
        engine.ANCHOR_BASELINE_M = 2.0
        engine.UWB_IMU_FUSION = True
        engine.IMU_STRIDE_M = 0.20
        engine.IMU_YAW_A1_TO_A2_DEG = 0.0
        engine.IMU_FORWARD_OFFSET_DEG = 0.0
        engine.IMU_YAW_SIGN = 1.0
        engine.UWB_BRANCH_MIN_HEIGHT_M = 0.10
        worker_id = "fusion-worker"
        engine.reset_smooth_state(worker_id)
        engine._smooth_state[worker_id] = {
            "x": 50.0,
            "y": 7.0,
            "at": time.monotonic() - 1.0,
            "steps": 0,
        }
        distance = math.sqrt(1.0**2 + 0.2**2)

        point = engine.estimate_position(worker_id, distance, distance,
                                         yaw=0.0, steps=1, imu_ok=True)
        self.assertIsNotNone(point)
        status = engine.get_fix_status(worker_id)
        self.assertTrue(status["valid"])
        self.assertTrue(status["pdr_available"])
        self.assertEqual(status["branch_source"], "imu_pdr")
        self.assertLess(point[1], 15.0)

    def test_yaw_without_a_new_step_never_changes_the_work_area_branch(self):
        engine.ANCHOR_BASELINE_M = 2.0
        engine.UWB_IMU_FUSION = True
        engine.IMU_STRIDE_M = 0.20
        engine.IMU_YAW_A1_TO_A2_DEG = 0.0
        engine.UWB_BRANCH_MIN_HEIGHT_M = 0.10
        worker_id = "no-step-worker"
        engine.reset_smooth_state(worker_id)
        engine._smooth_state[worker_id] = {
            "x": 50.0,
            "y": 7.0,
            "at": time.monotonic() - 1.0,
            "steps": 5,
        }
        distance = math.sqrt(1.0**2 + 0.2**2)

        engine.estimate_position(worker_id, distance, distance,
                                 yaw=90.0, steps=5, imu_ok=True)
        status = engine.get_fix_status(worker_id)
        self.assertFalse(status["pdr_available"])
        self.assertEqual(status["pdr_reason"], "no_new_steps")

    def test_stationary_bno_damps_a_real_uwb_innovation(self):
        engine.ANCHOR_BASELINE_M = 2.0
        engine.UWB_D1_OFFSET_M = 0.0
        engine.UWB_D2_OFFSET_M = 0.0
        worker_id = "stationary-worker"
        engine.reset_smooth_state(worker_id)

        first_d1, first_d2 = engine.distances_from_position(50.0, 45.0, noise_std=0.0)
        first = engine.estimate_position(
            worker_id, first_d1, first_d2, steps=10, imu_ok=True,
            gyro_x=0.0, gyro_y=0.0, gyro_z=0.0,
            linear_accel=0.0, stability=2,
        )
        second_d1, second_d2 = engine.distances_from_position(65.0, 45.0, noise_std=0.0)
        second = engine.estimate_position(
            worker_id, second_d1, second_d2, steps=10, imu_ok=True,
            gyro_x=0.0, gyro_y=0.0, gyro_z=0.0,
            linear_accel=0.0, stability=2,
        )
        status = engine.get_fix_status(worker_id)

        self.assertEqual(status["motion_state"], "stationary")
        self.assertLessEqual(status["smoothing_alpha"], engine.STATIONARY_ALPHA)
        self.assertLess(math.dist(first, second), 2.0)

    def test_gyro_turn_is_exposed_as_a_uwb_confidence_gate(self):
        engine.ANCHOR_BASELINE_M = 2.0
        engine.UWB_D1_OFFSET_M = 0.0
        engine.UWB_D2_OFFSET_M = 0.0
        worker_id = "turning-worker"
        engine.reset_smooth_state(worker_id)
        d1, d2 = engine.distances_from_position(50.0, 45.0, noise_std=0.0)

        engine.estimate_position(
            worker_id, d1, d2, steps=2, imu_ok=True,
            gyro_x=0.0, gyro_y=0.0, gyro_z=0.0,
            linear_accel=0.4, stability=4,
        )
        engine.estimate_position(
            worker_id, d1, d2, steps=2, imu_ok=True,
            gyro_x=0.0, gyro_y=0.0, gyro_z=0.8,
            linear_accel=0.4, stability=4,
        )
        status = engine.get_fix_status(worker_id)

        self.assertEqual(status["motion_state"], "turning")
        self.assertGreaterEqual(status["gyro_rad_s"], 0.8)
        self.assertEqual(status["branch_source"], "work_area")

    def test_direct_two_range_ekf_publishes_an_asymmetric_off_line_fix(self):
        self.enable_direct_fusion()
        worker_id = "direct-ekf-worker"
        engine.reset_smooth_state(worker_id)

        point = self.direct_fix(worker_id, 70.0, 55.0, sequence=1)
        status = engine.get_fix_status(worker_id)

        self.assertIsNotNone(point)
        # Firmware transports centimetre-rounded ranges, which maps to a few
        # tenths of a logical UI unit with this 2 m / 80-unit baseline.
        self.assertAlmostEqual(point[0], 70.0, delta=0.3)
        self.assertAlmostEqual(point[1], 55.0, delta=0.3)
        self.assertTrue(status["valid"])
        self.assertTrue(status["fusion_accepted_uwb"])
        self.assertEqual(status["geometry_mode"], "two_anchor_ekf")
        self.assertEqual(status["fusion_range_sequence"], "range_sequence_fresh")
        self.assertFalse(status["imu_accel_prediction"])
        self.assertTrue(engine.is_publishable_uwb_fix(point, status))

    def test_direct_two_range_ekf_requires_fresh_metadata_and_does_not_reuse_a_pair(self):
        self.enable_direct_fusion()
        worker_id = "direct-sequence-worker"
        engine.reset_smooth_state(worker_id)
        d1, d2 = engine.distances_from_position(70.0, 55.0, noise_std=0.0)

        missing = engine.estimate_position(worker_id, d1, d2)
        self.assertIsNone(missing)
        self.assertEqual(engine.get_fix_status(worker_id)["reason"], "range_age_required")

        first = engine.estimate_position(worker_id, d1, d2, range_seq=10, range_age_ms=0)
        self.assertIsNotNone(first)
        tracker = engine._uwb_imu_filters[worker_id]
        before = tracker.state_vector()

        duplicate = engine.estimate_position(worker_id, d1, d2, range_seq=10, range_age_ms=0)
        self.assertIsNone(duplicate)
        self.assertEqual(engine.get_fix_status(worker_id)["reason"], "range_snapshot_duplicate_or_out_of_order")
        self.assertEqual(tracker.state_vector(), before)

        stale = engine.estimate_position(worker_id, d1, d2, range_seq=11, range_age_ms=701)
        self.assertIsNone(stale)
        self.assertEqual(engine.get_fix_status(worker_id)["reason"], "range_snapshot_stale")
        self.assertEqual(tracker.state_vector(), before)

        recovered = engine.estimate_position(worker_id, d1, d2, range_seq=12, range_age_ms=0)
        self.assertIsNotNone(recovered)
        self.assertTrue(engine.get_fix_status(worker_id)["fusion_accepted_uwb"])

    def test_direct_two_range_ekf_recovers_after_source_epoch_change(self):
        self.enable_direct_fusion()
        worker_id = "direct-reboot-worker"
        engine.reset_smooth_state(worker_id)

        self.assertIsNotNone(self.direct_fix(
            worker_id, 70.0, 55.0, sequence=10, epoch=101
        ))
        old_tracker = engine._uwb_imu_filters[worker_id]
        restarted = self.direct_fix(
            worker_id, 70.0, 55.0, sequence=0, epoch=202
        )
        status = engine.get_fix_status(worker_id)

        self.assertIsNotNone(restarted)
        self.assertIs(engine._uwb_imu_filters[worker_id], old_tracker)
        self.assertTrue(status["fusion_accepted_uwb"])
        self.assertEqual(status["fusion_range_sequence"], "range_epoch_changed")

        # A delayed HTTP packet from the retired pre-reboot source must not
        # rewind the fresh boot's EKF state merely because its ranges are real.
        before_delayed = old_tracker.state_vector()
        delayed = self.direct_fix(
            worker_id, 30.0, 55.0, sequence=11, epoch=101
        )
        self.assertIsNone(delayed)
        self.assertEqual(engine.get_fix_status(worker_id)["reason"], "range_epoch_retired")
        self.assertEqual(old_tracker.state_vector(), before_delayed)

        self.assertIsNotNone(self.direct_fix(
            worker_id, 70.0, 55.0, sequence=1, epoch=202
        ))

    def test_direct_two_range_ekf_never_accepts_a_numeric_reset_without_epoch(self):
        self.enable_direct_fusion()
        worker_id = "direct-legacy-reset-worker"
        engine.reset_smooth_state(worker_id)

        self.assertIsNotNone(self.direct_fix(worker_id, 70.0, 55.0, sequence=10))
        tracker = engine._uwb_imu_filters[worker_id]
        before = tracker.state_vector()

        # A lower counter alone can be a delayed/out-of-order payload. Current
        # firmware provides range_epoch at boot, so the backend must not infer
        # a reboot from this untrusted numeric pattern.
        self.assertIsNone(self.direct_fix(
            worker_id, 30.0, 55.0, sequence=0, epoch=0
        ))
        self.assertEqual(
            engine.get_fix_status(worker_id)["reason"],
            "range_sequence_reset_requires_epoch",
        )
        self.assertEqual(tracker.state_vector(), before)
        self.assertIsNotNone(self.direct_fix(worker_id, 70.0, 55.0, sequence=11))

    def test_direct_two_range_ekf_keeps_declared_side_at_low_geometry(self):
        self.enable_direct_fusion()
        worker_id = "direct-side-invariant-worker"
        engine.reset_smooth_state(worker_id)

        # Start just far enough off the anchor baseline to establish the
        # configured (+) side. The next pair is tangent/ambiguous, but it must
        # be labelled as such rather than select the unobservable mirror.
        first = self.direct_fix(
            worker_id, 50.0, 23.0, sequence=1, epoch="boot-side"
        )
        self.assertIsNotNone(first)
        tangent = engine.estimate_position(
            worker_id, 1.0, 1.0,
            range_seq=2, range_age_ms=0, range_epoch="boot-side",
            imu_ok=True, stability=4,
            gyro_x=0.0, gyro_y=0.0, gyro_z=0.0,
            linear_accel=0.0,
        )
        status = engine.get_fix_status(worker_id)

        self.assertIsNotNone(tangent)
        self.assertGreaterEqual(tangent[1], engine.ANCHORS[0]["y"])
        self.assertTrue(status["low_geometry"])
        self.assertTrue(status["branch_ambiguous"])
        self.assertEqual(status["branch"], "ekf_allowed_side")

    def test_direct_two_range_ekf_rejects_line_fallback_conflict_and_low_geometry_bootstrap(self):
        self.enable_direct_fusion()
        worker_id = "direct-conflict-worker"
        engine.UWB_LINE_FALLBACK = True
        self.assertIsNone(self.direct_fix(worker_id, 70.0, 55.0, sequence=1))
        self.assertEqual(engine.get_fix_status(worker_id)["reason"], "two_d_fusion_requires_line_fallback_disabled")

        engine.UWB_LINE_FALLBACK = False
        self.assertIsNone(engine.estimate_position(worker_id, 1.0, 1.0, range_seq=1, range_age_ms=0))
        status = engine.get_fix_status(worker_id)
        self.assertEqual(status["reason"], "bootstrap_low_geometry")
        self.assertTrue(status["low_geometry"])
        self.assertIsNotNone(self.direct_fix(worker_id, 70.0, 55.0, sequence=2))

    def test_direct_ekf_outside_map_resets_before_a_later_valid_bootstrap(self):
        self.enable_direct_fusion()
        worker_id = "direct-map-boundary-worker"
        engine.reset_smooth_state(worker_id)

        # Logical x=130 is a valid two-circle geometry but outside the UI map.
        self.assertIsNone(self.direct_fix(worker_id, 130.0, 55.0, sequence=1))
        self.assertEqual(engine.get_fix_status(worker_id)["reason"], "ekf_outside_configured_map")
        self.assertFalse(engine._uwb_imu_filters[worker_id].initialized)

        valid = self.direct_fix(worker_id, 70.0, 55.0, sequence=2)
        self.assertIsNotNone(valid)
        self.assertTrue(engine.get_fix_status(worker_id)["fusion_accepted_uwb"])

    def test_direct_ekf_requires_work_area_to_select_a_real_side(self):
        self.enable_direct_fusion()
        engine.WORK_AREA_POINT = (50.0, 15.0)
        worker_id = "direct-work-area-worker"
        self.assertIsNone(self.direct_fix(worker_id, 70.0, 55.0, sequence=1))
        self.assertEqual(engine.get_fix_status(worker_id)["reason"], "work_area_point_on_anchor_baseline")


if __name__ == "__main__":
    unittest.main()
