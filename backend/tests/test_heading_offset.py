import math
import unittest

from backend.core import heading_offset


def feed_walk(worker, *, t0, start, heading_deg, dist_m, yaw_game, epoch=1, upm=40.0, steps=8):
    """Feed one straight walk as a series of published fixes; returns end time."""
    heading = math.radians(heading_deg)
    for index in range(steps + 1):
        fraction = index / steps
        x_m = start[0] + math.cos(heading) * dist_m * fraction
        y_m = start[1] + math.sin(heading) * dist_m * fraction
        heading_offset.observe_fix(
            worker,
            t_s=t0 + 2.0 * fraction,
            x_units=x_m * upm,
            y_units=y_m * upm,
            units_per_metre=upm,
            yaw_game_deg=yaw_game,
            yaw_game_age_ms=50.0,
            imu_epoch=epoch,
        )
    return t0 + 2.0


class HeadingOffsetLearnerTests(unittest.TestCase):
    def setUp(self):
        heading_offset._reset_all()

    def tearDown(self):
        heading_offset._reset_all()

    def commission_plus_sign(self, worker="wk-plus"):
        # Consistent with map = yaw_game + (-30): three straight walks in two
        # different directions, 10 s apart so windows never blend.
        t = feed_walk(worker, t0=0.0, start=(0.0, 0.0), heading_deg=0.0, dist_m=1.6, yaw_game=30.0)
        t = feed_walk(worker, t0=t + 10.0, start=(2.0, 0.0), heading_deg=90.0, dist_m=1.6, yaw_game=120.0)
        feed_walk(worker, t0=t + 20.0, start=(2.0, 2.0), heading_deg=0.0, dist_m=1.6, yaw_game=30.0)
        return worker

    def test_learns_offset_and_positive_sign_from_two_directions(self):
        worker = self.commission_plus_sign()
        self.assertTrue(heading_offset.commissioned(worker))
        diag = heading_offset.diagnostics(worker)
        self.assertEqual(diag["sign"], 1)
        self.assertAlmostEqual(diag["offset_deg"], -30.0, delta=3.0)
        mapped = heading_offset.map_heading(worker, yaw_game_deg=45.0, imu_epoch=1)
        self.assertIsNotNone(mapped)
        self.assertAlmostEqual(mapped, 15.0, delta=3.0)

    def test_learns_mirrored_sign(self):
        worker = "wk-minus"
        # Consistent with map = -yaw_game + 10.
        t = feed_walk(worker, t0=0.0, start=(0.0, 0.0), heading_deg=0.0, dist_m=1.6, yaw_game=10.0)
        t = feed_walk(worker, t0=t + 10.0, start=(2.0, 0.0), heading_deg=90.0, dist_m=1.6, yaw_game=-80.0)
        feed_walk(worker, t0=t + 20.0, start=(2.0, 2.0), heading_deg=0.0, dist_m=1.6, yaw_game=10.0)
        self.assertTrue(heading_offset.commissioned(worker))
        diag = heading_offset.diagnostics(worker)
        self.assertEqual(diag["sign"], -1)
        mapped = heading_offset.map_heading(worker, yaw_game_deg=-35.0, imu_epoch=1)
        self.assertAlmostEqual(mapped, 45.0, delta=3.0)

    def test_single_direction_never_commissions(self):
        worker = "wk-one-way"
        # One walking direction fits BOTH sign hypotheses: without heading
        # diversity the learner must refuse to choose.
        t = 0.0
        for _ in range(5):
            t = feed_walk(worker, t0=t + 10.0, start=(0.0, 0.0), heading_deg=0.0, dist_m=1.6, yaw_game=30.0)
        self.assertFalse(heading_offset.commissioned(worker))
        self.assertIsNone(heading_offset.map_heading(worker, yaw_game_deg=30.0, imu_epoch=1))

    def test_imu_epoch_change_resets_everything(self):
        worker = self.commission_plus_sign()
        self.assertTrue(heading_offset.commissioned(worker))
        heading_offset.observe_fix(
            worker,
            t_s=1000.0,
            x_units=10.0,
            y_units=10.0,
            units_per_metre=40.0,
            yaw_game_deg=0.0,
            yaw_game_age_ms=50.0,
            imu_epoch=2,
        )
        self.assertFalse(heading_offset.commissioned(worker))
        self.assertIsNone(heading_offset.map_heading(worker, yaw_game_deg=45.0, imu_epoch=2))

    def test_stale_epoch_yaw_is_not_mapped(self):
        worker = self.commission_plus_sign()
        self.assertIsNone(heading_offset.map_heading(worker, yaw_game_deg=45.0, imu_epoch=99))

    def test_curved_path_teaches_nothing(self):
        worker = "wk-curve"
        upm = 40.0
        # A tight arc: plenty of path length, no straightness.
        for index in range(40):
            angle = index * (math.pi / 20.0)
            heading_offset.observe_fix(
                worker,
                t_s=index * 0.1,
                x_units=math.cos(angle) * 0.8 * upm,
                y_units=math.sin(angle) * 0.8 * upm,
                units_per_metre=upm,
                yaw_game_deg=math.degrees(angle),
                yaw_game_age_ms=50.0,
                imu_epoch=1,
            )
        self.assertFalse(heading_offset.commissioned(worker))
        self.assertEqual(heading_offset.diagnostics(worker)["segments"], 0)

    def test_stationary_worker_teaches_nothing(self):
        worker = "wk-still"
        for index in range(30):
            heading_offset.observe_fix(
                worker,
                t_s=index * 0.4,
                x_units=40.0,
                y_units=40.0,
                units_per_metre=40.0,
                yaw_game_deg=90.0,
                yaw_game_age_ms=50.0,
                imu_epoch=1,
            )
        self.assertEqual(heading_offset.diagnostics(worker)["segments"], 0)

    def test_broken_mapping_decommissions_after_consecutive_strikes(self):
        worker = self.commission_plus_sign()
        self.assertTrue(heading_offset.commissioned(worker))
        # The tag was remounted: walks now run ~60 deg away from what the
        # learned mapping predicts.  Judged against the PRE-update offset,
        # each segment is a strike and the third one revokes the mapping.
        t = 100.0
        for _ in range(heading_offset.DECOMMISSION_STRIKES):
            t = feed_walk(worker, t0=t + 10.0, start=(0.0, 0.0), heading_deg=60.0, dist_m=1.6, yaw_game=30.0)
        self.assertFalse(heading_offset.commissioned(worker))

    def test_good_segment_resets_strikes_and_keeps_commission(self):
        worker = self.commission_plus_sign()
        t = 100.0
        for _ in range(heading_offset.DECOMMISSION_STRIKES - 1):
            t = feed_walk(worker, t0=t + 10.0, start=(0.0, 0.0), heading_deg=60.0, dist_m=1.6, yaw_game=30.0)
        # One consistent walk (track 0, yaw 30, offset -30) clears the strikes.
        t = feed_walk(worker, t0=t + 10.0, start=(0.0, 0.0), heading_deg=0.0, dist_m=1.6, yaw_game=30.0)
        for _ in range(heading_offset.DECOMMISSION_STRIKES - 1):
            t = feed_walk(worker, t0=t + 10.0, start=(0.0, 0.0), heading_deg=60.0, dist_m=1.6, yaw_game=30.0)
        self.assertTrue(heading_offset.commissioned(worker))

    def test_none_epoch_sample_does_not_wipe_a_commissioned_learner(self):
        worker = self.commission_plus_sign()
        heading_offset.observe_fix(
            worker,
            t_s=1000.0,
            x_units=10.0,
            y_units=10.0,
            units_per_metre=40.0,
            yaw_game_deg=0.0,
            yaw_game_age_ms=50.0,
            imu_epoch=None,
        )
        self.assertTrue(heading_offset.commissioned(worker))

    def test_stale_yaw_samples_are_ignored(self):
        worker = "wk-stale-yaw"
        feed = dict(t_s=0.0, x_units=0.0, y_units=0.0, units_per_metre=40.0,
                    yaw_game_deg=0.0, imu_epoch=1)
        heading_offset.observe_fix(worker, yaw_game_age_ms=5000.0, **feed)
        learner = heading_offset._learners.get(worker)
        self.assertTrue(learner is None or len(learner.points) == 0)


if __name__ == "__main__":
    unittest.main()
