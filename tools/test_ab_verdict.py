"""bench/ab.py's verdict on a paired A/B comparison never says "noise" or "equivalent" without the evidence for it
(judge r2, 2026-10-27): equivalence needs an A/A control from the SAME campaign and a margin declared before the run,
and every paired difference inside it; a jump that does not repeat is "not consistently reproduced", nothing more."""

import importlib.util
import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("bench_ab", ROOT / "bench" / "ab.py")
ab = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ab)


class Verdict(unittest.TestCase):
    def test_no_aa_control_or_no_margin_is_never_equivalent(self):
        small = [0.5, -0.4, 0.2, -0.1, 0.3, 0.0, -0.2, 0.1, 0.4, -0.3]
        self.assertEqual(ab.verdict(small, None, 5.0)["verdict"], "not consistently reproduced")
        self.assertEqual(ab.verdict(small, small, None)["verdict"], "not consistently reproduced")

    def test_equivalent_only_inside_a_predeclared_margin_with_a_same_campaign_aa(self):
        small = [0.5, -0.4, 0.2, -0.1, 0.3, 0.0, -0.2, 0.1, 0.4, -0.3]
        aa = [0.2, -0.1, 0.1, 0.0, -0.2, 0.3, -0.3, 0.1, 0.0, 0.2]
        got = ab.verdict(small, aa, 2.0)
        self.assertEqual(got["verdict"], "equivalent within ±2.0 ms")
        # one paired difference outside the margin: not equivalent
        self.assertEqual(ab.verdict(small + [9.0], aa, 2.0)["verdict"], "not consistently reproduced")

    def test_a_consistent_slowdown_beyond_the_aa_drift_is_a_regression(self):
        slow = [5.1, 4.2, 6.0, 5.5, 4.8, 5.9, 4.4, 5.2, 6.3, 4.9]
        aa = [0.2, -0.1, 0.1, 0.0, -0.2, 0.3, -0.3, 0.1, 0.0, 0.2]
        self.assertEqual(ab.verdict(slow, aa, 2.0)["verdict"], "regression")

    def test_a_wide_spread_with_no_consistent_sign_is_not_reproduced(self):
        wild = [129.3, -137.5, 9.4, 40.0, -20.0, 3.0, -60.0, 88.0, -5.0, 12.0]
        aa = [9.2, -40.0, 30.0, -12.0, 25.0, 3.0, -8.0, 14.0, 2.0, 6.0]
        self.assertEqual(ab.verdict(wild, aa, 5.0)["verdict"], "not consistently reproduced")


if __name__ == "__main__":
    unittest.main()
