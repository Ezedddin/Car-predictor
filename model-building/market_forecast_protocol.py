"""Forecast later asking-price medians for cohorts fixed at historical month ends."""

import argparse
from pathlib import Path

import pandas as pd

from historical_error_analysis import cohorts, metrics
from historical_validation import ARCHIVE, prepare_archive

KEYS = ["brand_model", "year", "fuel_type", "mileage_band"]
MIN_LISTINGS = 5


def market_snapshot(cars, month):
    in_month = cars["snapshot_date"].dt.to_period("M").eq(month)
    grouped = cars.loc[in_month].groupby(KEYS, observed=True)["price_eur"].agg(["size", "median"])
    return grouped.loc[grouped["size"].ge(MIN_LISTINGS), "median"]


def freeze_forecasts(cars, origin):
    """The forecast table is complete before any target-month prices are read."""
    history = cars.loc[cars["snapshot_date"].lt((origin + 1).start_time)]
    return market_snapshot(history, origin).rename("prediction")


def evaluate(cars):
    outcomes, coverage, issued = [], [], []
    for origin in pd.period_range("2023-03", "2023-12", freq="M"):
        forecasts = freeze_forecasts(cars, origin)
        for horizon in (12, 24):
            target = origin + horizon
            issued.append(forecasts.reset_index().assign(
                origin=str(origin.end_time.date()), target=str(target), months=horizon
            ))
            actual = market_snapshot(cars, target).rename("price_eur")
            matched = forecasts.to_frame().join(actual, how="inner").reset_index()
            outcomes.append(matched.assign(origin=str(origin.end_time.date()), target=str(target), months=horizon))
            coverage.append({"origin": str(origin), "target": str(target), "months": horizon,
                             "forecast_cohorts": len(forecasts), "matched_cohorts": len(matched)})
    return pd.concat(outcomes, ignore_index=True), pd.DataFrame(coverage), pd.concat(issued, ignore_index=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    cars = cohorts(prepare_archive(pd.read_csv(ARCHIVE)))
    results, coverage, issued = evaluate(cars)
    issued.to_csv(args.output / "market_issued.csv", index=False)
    results.to_csv(args.output / "market_forecasts.csv", index=False)
    coverage.to_csv(args.output / "market_coverage.csv", index=False)
    for months, group in results.groupby("months"):
        print(months, metrics(group))
        print("Matched / issued:", coverage.loc[coverage.months.eq(months),
              ["matched_cohorts", "forecast_cohorts"]].sum().to_dict())
