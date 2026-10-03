import unittest
from unittest.mock import patch
import numpy as np
import pandas as pd
import forecasting


class TestForecasting(unittest.TestCase):
    def test_regular_series_requires_explicit_gap_policy(self):
        rows = [{"period": "2024-01-01", "value": 10}, {"period": "2024-03-01", "value": 30}]
        with self.assertRaises(ValueError):
            forecasting.regular_series(rows, "month")
        series = forecasting.regular_series(rows, "month", "zero")
        self.assertEqual(list(series), [10, 0, 30])

    def test_invalid_dates_and_duplicates_are_not_silently_dropped(self):
        for rows in ([{"period": "invalid", "value": 10}],
                     [{"period": "2024-01-01", "value": 1}, {"period": "2024-01-15", "value": 2}]):
            with self.assertRaises(ValueError):
                forecasting.regular_series(rows, "month")

    def test_forecast_has_intervals_metrics_and_no_training_leakage(self):
        rng = np.random.default_rng(42)
        series = pd.Series(20 + np.arange(48) * 2 + rng.normal(0, 1, 48),
                           index=pd.date_range("2020-01-01", periods=48, freq="MS"))
        with patch("forecasting._fit", wraps=forecasting._fit) as fit:
            result = forecasting.forecast_series(series, 6)
        first_training = fit.call_args_list[0].args[0]
        self.assertEqual(len(first_training), 42)
        self.assertLess(first_training.index[-1], result["validation"]["period"].min())
        frame = result["forecast"]
        self.assertEqual(len(frame), 6)
        self.assertTrue((frame["lower"] <= frame["forecast"]).all())
        self.assertTrue((frame["upper"] >= frame["forecast"]).all())
        self.assertGreaterEqual(result["metrics"]["mae"], 0)
        self.assertTrue(result["beats_naive"])

    def test_short_or_constant_data_does_not_invent_forecasts(self):
        for n in (10, 24):
            series = pd.Series(np.ones(n), index=pd.date_range("2020-01-01", periods=n, freq="MS"))
            with self.subTest(n=n), self.assertRaises(ValueError):
                forecasting.forecast_series(series)
