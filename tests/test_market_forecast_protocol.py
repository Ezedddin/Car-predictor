import sys
import unittest
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "model-building"))
from market_forecast_protocol import evaluate, freeze_forecasts


class MarketForecastProtocolTests(unittest.TestCase):
    def test_future_prices_and_cohorts_cannot_change_issued_forecast(self):
        origin = pd.Period("2023-03", freq="M")
        history = pd.DataFrame({
            "snapshot_date": [pd.Timestamp("2023-03-01")] * 5,
            "brand_model": ["A X"] * 5, "year": [2021] * 5, "fuel_type": ["petrol"] * 5,
            "mileage_band": ["0–50000"] * 5, "price_eur": [20_000] * 5,
        })
        later = history.assign(snapshot_date=pd.Timestamp("2024-03-01"), price_eur=15_000)
        unseen = later.assign(brand_model="B Y")
        complete = pd.concat([history, later, unseen], ignore_index=True)
        pd.testing.assert_series_equal(freeze_forecasts(history, origin), freeze_forecasts(complete, origin))
        outcomes, coverage, issued = evaluate(complete)
        self.assertEqual(issued["prediction"].tolist(), [20_000, 20_000])
        self.assertEqual(outcomes[["months", "prediction", "price_eur"]].values.tolist(), [[12, 20_000, 15_000]])
        march = coverage.loc[coverage.origin.eq("2023-03")]
        self.assertEqual(march["matched_cohorts"].tolist(), [1, 0])
