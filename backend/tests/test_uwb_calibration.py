import unittest

from backend.core.uwb_calibration import RangeCalibrationCapture


class RangeCalibrationCaptureTests(unittest.TestCase):
    def stationary_sample(self, capture, d1=0.81, d2=1.11):
        return capture.add(
            d1, d2, imu_stability=2,
            gx=0.01, gy=-0.02, gz=0.01, linear_accel=0.03,
        )

    def test_ready_capture_reports_per_link_offsets(self):
        capture = RangeCalibrationCapture("WK_102", 1.0, 1.0, min_samples=10)
        for _ in range(10):
            self.assertTrue(self.stationary_sample(capture))

        status = capture.status()
        self.assertTrue(status["ready"])
        self.assertEqual(status["accepted_samples"], 10)
        self.assertAlmostEqual(status["recommended_offsets_m"]["d1"], 0.19)
        self.assertAlmostEqual(status["recommended_offsets_m"]["d2"], -0.11)

    def test_motion_is_rejected_even_when_ranges_look_good(self):
        capture = RangeCalibrationCapture("WK_102", 1.0, 1.0, min_samples=10)
        accepted = capture.add(
            0.8, 1.1, imu_stability=4,
            gx=0.0, gy=0.0, gz=0.5, linear_accel=0.4,
        )

        self.assertFalse(accepted)
        status = capture.status()
        self.assertEqual(status["accepted_samples"], 0)
        self.assertEqual(status["rejected_nonstationary"], 1)
        self.assertFalse(status["ready"])

    def test_large_range_spread_never_becomes_ready(self):
        capture = RangeCalibrationCapture("WK_102", 1.0, 1.0, min_samples=10, max_mad_m=0.05)
        for index in range(10):
            self.assertTrue(self.stationary_sample(capture, 0.7 if index % 2 else 1.1, 1.0))

        status = capture.status()
        self.assertFalse(status["ready"])
        self.assertEqual(status["reason"], "range_spread_too_large_keep_worker_still_or_fix_rf")

    def test_duplicate_or_stale_radio_sample_is_not_counted(self):
        capture = RangeCalibrationCapture("WK_102", 1.0, 1.0, min_samples=10)
        accepted = capture.add(
            0.8, 1.1, imu_stability=2,
            gx=0.01, gy=0.0, gz=0.01, linear_accel=0.02,
            range_seq=42, range_age_ms=250, steps=7,
        )
        duplicate = capture.add(
            0.8, 1.1, imu_stability=2,
            gx=0.01, gy=0.0, gz=0.01, linear_accel=0.02,
            range_seq=42, range_age_ms=250, steps=7,
        )
        stale = capture.add(
            0.8, 1.1, imu_stability=2,
            gx=0.01, gy=0.0, gz=0.01, linear_accel=0.02,
            range_seq=43, range_age_ms=701, steps=7,
        )

        self.assertTrue(accepted)
        self.assertFalse(duplicate)
        self.assertFalse(stale)
        status = capture.status()
        self.assertEqual(status["accepted_samples"], 1)
        self.assertEqual(status["rejected_duplicate_range"], 1)
        self.assertEqual(status["rejected_stale_range"], 1)

    def test_new_radio_epoch_restarts_incomplete_capture_instead_of_locking_out(self):
        capture = RangeCalibrationCapture("WK_102", 1.0, 1.0, min_samples=10)
        for sequence in range(10, 13):
            self.assertTrue(capture.add(
                0.8, 1.1, imu_stability=2,
                gx=0.01, gy=0.0, gz=0.01, linear_accel=0.02,
                range_seq=sequence, range_age_ms=20, range_epoch="boot-a", imu_age_ms=20,
            ))
        self.assertEqual(capture.status()["accepted_samples"], 3)

        self.assertTrue(capture.add(
            0.81, 1.11, imu_stability=2,
            gx=0.01, gy=0.0, gz=0.01, linear_accel=0.02,
            range_seq=0, range_age_ms=20, range_epoch="boot-b", imu_age_ms=20,
        ))
        status = capture.status()
        self.assertEqual(status["accepted_samples"], 1)
        self.assertEqual(status["restarted_range_epoch"], 1)

    def test_stale_imu_is_not_accepted_for_stationary_calibration(self):
        capture = RangeCalibrationCapture("WK_102", 1.0, 1.0, min_samples=10)
        self.assertFalse(capture.add(
            0.8, 1.1, imu_stability=2,
            gx=0.01, gy=0.0, gz=0.01, linear_accel=0.02,
            imu_age_ms=251,
        ))
        self.assertEqual(capture.status()["rejected_stale_imu"], 1)


if __name__ == "__main__":
    unittest.main()
