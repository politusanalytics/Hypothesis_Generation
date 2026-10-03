import unittest
from scipy import stats

from statistical_analysis import fisher_test, welch_test, hypothesis_report


class TestStatistics(unittest.TestCase):
    def test_welch_matches_reference_and_interval_excludes_zero(self):
        result = welch_test(100, 10, 2, 100, 12, 3)
        reference = stats.ttest_ind_from_stats(12, 3, 100, 10, 2, 100, equal_var=False)
        self.assertAlmostEqual(result["p_value"], reference.pvalue)
        self.assertEqual(result["decision"], "H0 reddedildi")
        self.assertEqual(result["effect"], 2)
        self.assertGreater(result["confidence_interval"][0], 0)
        self.assertNotIn("Destek Skoru", hypothesis_report(result))

    def test_no_difference_does_not_claim_acceptance(self):
        result = welch_test(100, 10, 2, 100, 10, 2)
        self.assertEqual(result["decision"], "H0 reddedilemedi")
        self.assertAlmostEqual(result["p_value"], 1)

    def test_fisher_matches_reference_and_effect_direction(self):
        result = fisher_test(10, 100, 40, 100)
        self.assertAlmostEqual(result["p_value"], stats.fisher_exact([[40, 60], [10, 90]]).pvalue)
        self.assertAlmostEqual(result["effect"], 0.3)
        self.assertGreater(result["confidence_interval"][0], 0)

    def test_rejects_impossible_data(self):
        for args in ((0, 0, 1, 2), (11, 10, 1, 2), (1.5, 10, 1, 2)):
            with self.subTest(args=args), self.assertRaises(ValueError):
                fisher_test(*args)
        with self.assertRaises(ValueError):
            welch_test(10, 1, 0, 10, 2, 0)
        with self.assertRaises(ValueError):
            welch_test(1, 1, 1, 10, 2, 1)
        with self.assertRaises(ValueError):
            fisher_test(1, 10, 2, 10, group_a="same", group_b="same")
