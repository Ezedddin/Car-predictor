"""Diagnostic only: isolate a catalog-price feature constructed with 2026 data."""

import numpy as np
import pandas as pd
from catboost import CatBoostRegressor

from historical_error_analysis import metrics
from historical_validation import ARCHIVE, CATEGORIES, FEATURES, prepare_archive, split_archive

KEYS = ["snapshot_date", "brand_model", "year", "fuel_type", "transmission", "mileage_km", "price_eur"]


def run():
    archive = prepare_archive(pd.read_csv(ARCHIVE))
    production = pd.read_parquet(ARCHIVE.parents[2] / "model-building/dataset_tijd.parquet")
    # Matching by observed row signature. Ambiguous catalog prices cannot be assigned reliably.
    catalog = production.loc[production.snapshot_date.dt.year.lt(2026), KEYS + ["new_price_2026"]]
    catalog = catalog.drop_duplicates().drop_duplicates(KEYS, keep=False)
    joined = archive.merge(catalog, on=KEYS, how="left", validate="many_to_one")
    matched = joined.loc[joined.new_price_2026.notna()]
    results = []
    for horizon in (1, 2):
        train, validation, test = split_archive(matched, horizon)
        history = pd.concat([train, validation])
        months = history.snapshot_date.dt.to_period("M")
        weights = 1 / months.groupby(months).transform("size")
        for with_catalog in (False, True):
            features = FEATURES + (["new_price_2026"] if with_catalog else [])
            model = CatBoostRegressor(iterations=800, depth=8, learning_rate=0.05, random_seed=42,
                                      cat_features=CATEGORIES, verbose=False, allow_writing_files=False,
                                      thread_count=4)
            model.fit(history[features], np.log(history.price_eur), sample_weight=weights / weights.mean())
            scored = test.assign(prediction=np.exp(model.predict(test[features])))
            for label, subset in [("all", scored), ("25k_50k", scored.loc[
                scored.price_eur.between(25_000, 50_000, inclusive="left")
            ])]:
                result = {"cutoff": 2025 - horizon, "train_n": len(history),
                          "catalog_2026": with_catalog, "sample": label} | metrics(subset)
                results.append(result)
            if not with_catalog:
                _, _, full_test = split_archive(joined, horizon)
                full_test = full_test.assign(prediction=np.exp(model.predict(full_test[features])))
                for label, subset in [
                    ("full_archive", full_test),
                    ("unmatched_only", full_test.loc[full_test.new_price_2026.isna()]),
                ]:
                    results.append({"cutoff": 2025 - horizon, "train_n": len(history),
                                    "catalog_2026": False, "sample": label} | metrics(subset))
            print(pd.DataFrame(results[-(2 if with_catalog else 4):]).round(3).to_string(index=False), flush=True)
    return results


if __name__ == "__main__":
    run()
