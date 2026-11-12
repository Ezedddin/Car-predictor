"""Reproduce historical price diagnostics. Run with an output directory argument."""

import argparse
from pathlib import Path

import numpy as np
import pandas as pd

from historical_validation import ARCHIVE, FEATURES, fit_catboost, prepare_archive, split_archive


def cohorts(cars):
    return cars.assign(
        mileage_band=pd.cut(cars["mileage_km"], [-1, 50_000, 100_000, 150_000, 200_000, np.inf]),
        model_year_band=(cars["year"] // 3 * 3).astype(str),
        age_band=cars["age"].astype(int),
    )


def historical_medians(history, test, keys_by_specificity):
    result = pd.Series(np.nan, index=test.index)
    for keys in keys_by_specificity:
        grouped = history.groupby(keys, observed=True)["price_eur"].agg(["median", "size"])
        estimates = grouped["median"].where(grouped["size"].ge(5)).rename("estimate")
        result = result.fillna(test.join(estimates, on=keys)["estimate"])
    return result.fillna(history["price_eur"].median())


def metrics(rows):
    actual, prediction = rows["price_eur"], rows["prediction"]
    error = prediction - actual
    variance = ((actual - actual.mean()) ** 2).sum()
    return {
        "n": len(rows), "mae": error.abs().mean(), "median_pct": (error.abs() / actual).median() * 100,
        "overshoot_pct": error.gt(0).mean() * 100, "median_bias": error.median(),
        "rmse": np.sqrt((error ** 2).mean()), "r2": 1 - (error ** 2).sum() / variance if variance else np.nan,
    }


def run(cars):
    all_scores, segments, shifts, tails = [], [], [], []
    for horizon in (1, 2):
        train, val, test = (cohorts(x) for x in split_archive(cars, horizon))
        history = pd.concat([train, val])
        in_band = test["price_eur"].between(25_000, 50_000, inclusive="left")
        supported = test.set_index(["brand_model", "year", "fuel_type"]).index.isin(
            history.set_index(["brand_model", "year", "fuel_type"]).index
        )
        predictions = {
            "global_median": history["price_eur"].median(),
            "model_age_median": historical_medians(history, test, [["brand_model", "age_band"], ["brand_model"]]),
            "comparable_median": historical_medians(history, test, [
                ["brand_model", "year", "fuel_type", "mileage_band"],
                ["brand_model", "year", "fuel_type"], ["brand_model", "year"], ["brand_model", "age_band"],
                ["brand_model"],
            ]),
        }
        # Learn bounds on training data only. Keep validation and test identical.
        bounds = train["price_eur"].quantile([0.005, 0.995])
        clipped_train = train.assign(price_eur=train["price_eur"].clip(*bounds))
        variants = [
            ("catboost", train, val, FEATURES),
            ("catboost_year", train, val, FEATURES + ["year"]),
            ("catboost_winsorized", clipped_train, val, FEATURES),
        ]
        for name, fit, tune, features in variants:
            model, _ = fit_catboost(fit, tune, features)
            predictions[name] = np.exp(model.predict(test[features]))
            print(f"Completed {name}, cutoff {2025 - horizon}", flush=True)

        meta = {"cutoff_year": 2025 - horizon}
        for name, prediction in predictions.items():
            scored = test.assign(prediction=prediction)
            for sample, selected in [
                ("all", scored), ("25k_50k", scored.loc[in_band]),
                ("25k_50k_seen", scored.loc[in_band & supported]),
                ("25k_50k_unseen", scored.loc[in_band & ~supported]),
            ]:
                all_scores.append(meta | {"model": name, "sample": sample} | metrics(selected))
            if name in ("catboost", "comparable_median"):
                for feature in ["brand", "year", "mileage_band", "fuel_type"]:
                    for value, group in scored.loc[in_band].groupby(feature, observed=True):
                        segments.append(meta | {"model": name, "feature": feature, "value": str(value)} | metrics(group))
            if name == "catboost":
                target = scored.loc[in_band].assign(error=lambda x: x.prediction - x.price_eur)
                for fraction in (0.01, 0.05):
                    squared = target.error.pow(2)
                    tails.append(meta | {"tail_fraction": fraction,
                                         "share_squared_error": squared.nlargest(int(len(squared) * fraction)).sum() / squared.sum()})
                for label, subset in [("history", history), ("test", test)]:
                    shifts.append(meta | {"sample": label, "n": len(subset),
                                          "price": subset.price_eur.median(), "age": subset.age.median(),
                                          "mileage": subset.mileage_km.median(),
                                          "electric_pct": subset.fuel_type.eq("electric").mean() * 100})
    return {"scores": all_scores, "segments": segments, "shifts": shifts, "tails": tails}


def selection_overlap(archive, production):
    """Count shared row signatures, preserving multiplicity when signatures repeat."""
    keys = ["snapshot_date", "brand_model", "year", "fuel_type", "transmission",
            "mileage_km", "price_eur"]
    def signatures(rows):
        return rows.loc[rows["snapshot_date"].dt.year.eq(2025), keys].value_counts()

    archive_counts = signatures(archive)
    production_counts = signatures(production)
    matched = archive_counts.combine(production_counts, min, fill_value=0)
    prices = archive_counts.index.get_level_values("price_eur")
    premium = (prices >= 25_000) & (prices < 50_000)
    return [
        {"sample": label, "archive": int(archive_counts.loc[mask].sum()),
         "shared_with_production": int(matched.reindex(archive_counts.index).loc[mask].sum())}
        for label, mask in [("all", np.ones(len(prices), dtype=bool)), ("25k_50k", premium)]
    ]


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    archive = prepare_archive(pd.read_csv(ARCHIVE))
    production = pd.read_parquet(Path(__file__).with_name("dataset_tijd.parquet"))
    pd.DataFrame(selection_overlap(archive, production)).to_csv(args.output / "selection.csv", index=False)
    for name, rows in run(archive).items():
        pd.DataFrame(rows).to_csv(args.output / f"{name}.csv", index=False)
