"""Historische vraagprijsbenchmark met voertuigkenmerken uit de testadvertentie.

Dit is een vergelijking per kalenderjaar, zonder productiecorrecties.
"""

from pathlib import Path

import numpy as np
import pandas as pd

ARCHIVE = Path(__file__).resolve().parents[1] / "webscrape/data/wayback_cars.csv"
CATEGORIES = ["brand_model", "brand", "fuel_type", "transmission"]
FEATURES = CATEGORIES + ["age", "mileage_km"]
PARAMETERS = [
    {"depth": 6, "learning_rate": 0.1},
    {"depth": 8, "learning_rate": 0.05},
]


def prepare_archive(data):
    dates = pd.to_datetime(data["snapshot_date"], errors="coerce")
    years = dates.dt.year
    valid = (
        data["country"].eq("NL")
        & data["page_sort"].eq("standard")
        & dates.ge("2023-03-01")
        & data["year"].ge(2005)
        & data["year"].le(years)
        & data["model"].notna()
        & data["model"].ne("Overig")
        & data["brand"].notna()
        & data["price_eur"].gt(0)
        & data["mileage_km"].ge(0)
        & data["mileage_km"].lt(600_000)
    )
    cars = data.loc[valid, ["brand", "model", "fuel_type", "transmission",
                            "year", "price_eur", "mileage_km"]].copy()
    cars["snapshot_date"] = dates.loc[valid]
    cars["brand_model"] = cars["brand"] + " " + cars["model"]
    cars[CATEGORIES] = cars[CATEGORIES].fillna("other").astype(str)
    moment = cars["snapshot_date"].dt.year + (cars["snapshot_date"].dt.month - 0.5) / 12
    cars["age"] = (moment - cars["year"] - 0.5).clip(lower=0)
    return cars.sort_values("snapshot_date", kind="stable")


def split_archive(cars, horizon):
    if horizon not in (1, 2):
        raise ValueError("Gebruik een horizon van één of twee jaar.")
    end = pd.Timestamp(year=2026 - horizon, month=1, day=1)
    validation_start = end - pd.DateOffset(months=3)
    dates = cars["snapshot_date"]
    return (
        cars.loc[dates.lt(validation_start)],
        cars.loc[dates.ge(validation_start) & dates.lt(end)],
        cars.loc[dates.ge("2025-01-01") & dates.lt("2026-01-01")],
    )


def price_metrics(actual, predicted):
    """Scores per werkelijke prijsklasse en voor alle advertenties samen."""
    error = np.abs(actual - predicted)
    tiers = [
        ("Alles", np.ones(len(actual), dtype=bool)),
        ("< €10.000", actual < 10_000),
        ("€10.000–<€25.000", (actual >= 10_000) & (actual < 25_000)),
        ("€25.000–<€50.000", (actual >= 25_000) & (actual < 50_000)),
        ("≥ €50.000", actual >= 50_000),
    ]
    rows = []
    for label, mask in tiers:
        values, errors = actual[mask], error[mask]
        variance = np.sum((values - values.mean()) ** 2) if len(values) else 0
        rows.append({
            "prijsklasse": label,
            "aantal": len(values),
            "MAE_EUR": round(errors.mean()) if len(values) else None,
            "mediane_fout_pct": round(100 * np.median(errors / values), 1) if len(values) else None,
            "overschat_pct": round(100 * np.mean(predicted[mask] > values), 1) if len(values) else None,
            "R2": round(1 - np.sum(errors**2) / variance, 3) if variance > 0 else None,
        })
    return rows


def fit_catboost(train, validation, features=FEATURES):
    from catboost import CatBoostRegressor, Pool

    def pool(rows):
        month = rows["snapshot_date"].dt.to_period("M")
        weights = 1 / month.groupby(month).transform("size")
        return Pool(rows[features], np.log(rows["price_eur"]),
                    cat_features=CATEGORIES, weight=weights / weights.mean())

    if train.empty or validation.empty:
        raise ValueError("Onvoldoende historische advertenties voor deze splitsing.")
    train_pool, validation_pool = pool(train), pool(validation)
    options = dict(random_seed=42, verbose=False, allow_writing_files=False, thread_count=4)
    scores = []
    for parameters in PARAMETERS:
        model = CatBoostRegressor(iterations=1500, early_stopping_rounds=75,
                                  **options, **parameters)
        model.fit(train_pool, eval_set=validation_pool, use_best_model=True)
        mae = np.abs(np.exp(model.predict(validation_pool)) - validation["price_eur"]).mean()
        scores.append((mae, model.tree_count_, parameters))

    _, trees, parameters = min(scores, key=lambda score: score[0])
    model = CatBoostRegressor(iterations=trees, **options, **parameters)
    model.fit(pool(pd.concat([train, validation])))
    return model, trees


def backtest(cars, horizon):
    train, validation, test = split_archive(cars, horizon)
    model, trees = fit_catboost(train, validation)
    actual = test["price_eur"].to_numpy()
    predicted = np.exp(model.predict(test[FEATURES]))
    context = {
        "train_tot_jaar": 2025 - horizon,
        "testjaar": 2025,
        "train": len(train),
        "validatie": len(validation),
        "bomen": trees,
    }
    return [context | metrics for metrics in price_metrics(actual, predicted)]


if __name__ == "__main__":
    archive = prepare_archive(pd.read_csv(ARCHIVE))
    results = [row for h in (1, 2) for row in backtest(archive, h)]
    print(pd.DataFrame(results).to_string(index=False))
