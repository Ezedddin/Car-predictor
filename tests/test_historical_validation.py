import sys
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "model-building"))
from historical_validation import ARCHIVE, FEATURES, prepare_archive, price_metrics, split_archive


class HistoricalValidationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.raw = pd.read_csv(ARCHIVE)
        cls.cars = prepare_archive(cls.raw)

    def test_cutoffs_separate_training_validation_and_test(self):
        for horizon, final_year in [(1, 2024), (2, 2023)]:
            with self.subTest(horizon=horizon):
                train, val, test = split_archive(self.cars, horizon)
                self.assertLess(train.snapshot_date.max(), val.snapshot_date.min())
                self.assertLess(val.snapshot_date.max(), test.snapshot_date.min())
                self.assertEqual(val.snapshot_date.max().year, final_year)
                self.assertEqual(set(test.snapshot_date.dt.year), {2025})

    def test_catalog_prices_cannot_change_cohort_or_features(self):
        changed = self.raw.assign(new_price_eur=1_000_000)
        pd.testing.assert_frame_equal(self.cars[FEATURES], prepare_archive(changed)[FEATURES])

    def test_future_row_cannot_change_earlier_preprocessing(self):
        cutoff = "2024-01-01"
        earlier = self.raw[self.raw["snapshot_date"] < cutoff]
        pd.testing.assert_frame_equal(
            self.cars[self.cars["snapshot_date"] < cutoff], prepare_archive(earlier)
        )

    def test_metrics_use_actual_price_bands_and_strict_overshoots(self):
        actual = np.array([5000, 10000, 25000, 50000])
        predicted = np.array([6000, 10000, 20000, 60000])
        total, low, middle, upper, premium = price_metrics(actual, predicted)
        self.assertEqual(total["MAE_EUR"], 4000)
        self.assertEqual(total["mediane_fout_pct"], 20.0)
        self.assertEqual(total["overschat_pct"], 50.0)
        self.assertEqual([row["aantal"] for row in (low, middle, upper, premium)], [1, 1, 1, 1])
        self.assertIsNone(low["R2"])
        self.assertEqual(middle["overschat_pct"], 0.0)
