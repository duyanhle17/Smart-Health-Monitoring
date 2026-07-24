import math
import unittest

from backend.core import position_engine as engine


class TwoAnchorPositionTests(unittest.TestCase):
    def setUp(self):
        engine.reset_smooth_state("test-worker")

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


if __name__ == "__main__":
    unittest.main()
