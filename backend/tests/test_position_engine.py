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
        self.original_calibrated = engine.UWB_CALIBRATED
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
        engine.UWB_CALIBRATED = self.original_calibrated
        engine.UWB_IMU_FUSION = self.original_imu_fusion
        engine.IMU_STRIDE_M = self.original_imu_stride
        engine.IMU_YAW_A1_TO_A2_DEG = self.original_imu_yaw_axis
        engine.IMU_FORWARD_OFFSET_DEG = self.original_imu_forward_offset
        engine.IMU_YAW_SIGN = self.original_imu_yaw_sign
        engine.UWB_BRANCH_MIN_HEIGHT_M = self.original_branch_min_height
        engine.UWB_MAX_STEP_DELTA = self.original_max_step_delta

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
        self.assertEqual(status["branch_source"], "work_area")


if __name__ == "__main__":
    unittest.main()
