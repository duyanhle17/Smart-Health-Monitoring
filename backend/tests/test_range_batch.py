import unittest

from backend.core.range_batch import parse_range_batch


def item(seq, d1=1.2, d2=1.3, age_ms=500.0, **extra):
    entry = {"d1": d1, "d2": d2, "seq": seq, "age_ms": age_ms}
    entry.update(extra)
    return entry


class ParseRangeBatchTests(unittest.TestCase):
    def test_sorts_oldest_first_and_normalises_fields(self):
        telemetry = {
            "range_seq": 50,
            "ranges": [item(42, age_ms=300.0, nlos_d2=True), item(40, age_ms=900.0)],
        }
        parsed = parse_range_batch(telemetry)
        self.assertEqual([entry["seq"] for entry in parsed], [40, 42])
        self.assertEqual(parsed[1]["nlos"], (False, True))
        self.assertTrue(parsed[0]["trusted"])

    def test_backlog_may_not_reach_or_pass_the_live_sequence(self):
        telemetry = {"range_seq": 50, "ranges": [item(49), item(50), item(51)]}
        parsed = parse_range_batch(telemetry)
        self.assertEqual([entry["seq"] for entry in parsed], [49])

    def test_garbage_entries_and_garbage_arrays_are_dropped(self):
        self.assertEqual(parse_range_batch({"ranges": "boom"}), [])
        self.assertEqual(parse_range_batch(None), [])
        self.assertEqual(parse_range_batch({}), [])
        telemetry = {
            "range_seq": 50,
            "ranges": [
                "text",
                item(40, d1=float("nan")),
                item(41, d2=None),
                item("x"),
                item(42, age_ms=-5.0),
                item(43, d1=99.0),
                item(44),
            ],
        }
        parsed = parse_range_batch(telemetry)
        self.assertEqual([entry["seq"] for entry in parsed], [44])

    def test_duplicate_sequences_keep_first_and_cap_keeps_newest(self):
        telemetry = {
            "range_seq": 100,
            "ranges": [item(7, d1=1.0), item(7, d1=2.0)] + [item(i) for i in range(10, 40)],
        }
        parsed = parse_range_batch(telemetry, max_items=4)
        self.assertEqual([entry["seq"] for entry in parsed], [36, 37, 38, 39])
        solo = parse_range_batch({"range_seq": 100, "ranges": [item(7, d1=1.0), item(7, d1=2.0)]})
        self.assertEqual(len(solo), 1)
        self.assertEqual(solo[0]["d1"], 1.0)

    def test_missing_live_sequence_drops_the_whole_backlog(self):
        # Without the live pair's sequence there is no ceiling: a spoofed huge
        # backlog seq could advance the engine's sequence state and lock out
        # every later live pair until reboot.  The array must be dropped.
        self.assertEqual(parse_range_batch({"ranges": [item(3)]}), [])
        self.assertEqual(
            parse_range_batch({"range_seq": "junk", "ranges": [item(3)]}), []
        )
        self.assertEqual(
            parse_range_batch({"range_seq": None, "ranges": [item(4000000000)]}), []
        )


if __name__ == "__main__":
    unittest.main()
