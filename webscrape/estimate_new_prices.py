"""Estimate new_price_eur for cars where no exact new price was found.

Runs automatically at the end of a complete scraper run, and can also be run on its own:
    python estimate_new_prices.py

Order of estimates (first one that gives a value wins):
1. median of the exact new prices in cars.csv for the same brand + model + year
2. median RDW catalogusprijs for the same brand + model + year of first registration
3. median of the exact new prices in cars.csv for the same brand + model (all years)

Earlier estimates are recalculated on every run, so they improve as the dataset grows.
"""

import csv
import logging
import os
import statistics
import time
from collections import defaultdict

import requests

import config

log = logging.getLogger("autoscout24")

EXACT_SOURCES = {"autoscout", "rdw_kenteken"}
ESTIMATE_SOURCE = "schatting"
RDW_MIN_CARS = 3


def rdw_median(brand, model, year):
    """Median RDW catalogusprijs for brand + model + year, or None."""
    model = model.upper().replace("'", "''")
    params = {
        "$select": "median(catalogusprijs) as med, count(*) as n",
        "$where": (
            f"merk='{brand.upper()}' "
            f"and (handelsbenaming like '{model}%' or handelsbenaming like '% {model}%') "
            f"and datum_eerste_toelating between '{year}0101' and '{year}1231' "
            f"and catalogusprijs > 0"
        ),
    }
    for attempt in range(1, config.MAX_RETRIES + 1):
        try:
            resp = requests.get(config.RDW_URL, params=params, timeout=config.REQUEST_TIMEOUT)
            resp.raise_for_status()
            result = (resp.json() or [{}])[0]
            if int(result.get("n") or 0) >= RDW_MIN_CARS and result.get("med"):
                return round(float(result["med"]))
            return None
        except Exception as exc:
            log.warning("RDW-fout (poging %d/%d): %s", attempt, config.MAX_RETRIES, exc)
            time.sleep(10 * attempt)
    return None


def estimate():
    if not config.CSV_PATH.exists():
        log.warning("%s bestaat niet; niets te schatten.", config.CSV_PATH)
        return

    with open(config.CSV_PATH, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    # Reset old estimates so they are recalculated with the current data
    for row in rows:
        if row["new_price_source"] not in EXACT_SOURCES:
            row["new_price_eur"] = ""
            row["new_price_source"] = ""

    by_model_year = defaultdict(list)
    by_model = defaultdict(list)
    for row in rows:
        if row["new_price_eur"]:
            price = int(row["new_price_eur"])
            by_model_year[(row["brand"], row["model"], row["year"])].append(price)
            by_model[(row["brand"], row["model"])].append(price)

    missing = [r for r in rows if not r["new_price_eur"]]
    log.info("[SCHATTING] %d van %d auto's zonder exacte nieuwprijs", len(missing), len(rows))

    rdw_cache = {}
    counts = defaultdict(int)
    for row in missing:
        key = (row["brand"], row["model"], row["year"])
        price = None
        if by_model_year.get(key):
            price = statistics.median(by_model_year[key])
            counts["dataset merk+model+jaar"] += 1
        else:
            if key not in rdw_cache and row["model"] and row["year"]:
                rdw_cache[key] = rdw_median(*key)
                time.sleep(1)
            price = rdw_cache.get(key)
            if price:
                counts["RDW merk+model+jaar"] += 1
            elif by_model.get(key[:2]):
                price = statistics.median(by_model[key[:2]])
                counts["dataset merk+model"] += 1
        if price:
            row["new_price_eur"] = round(price)
            row["new_price_source"] = ESTIMATE_SOURCE
        else:
            counts["geen schatting mogelijk"] += 1

    # Write to a temporary file first, so cars.csv is never left half-written
    tmp_path = config.CSV_PATH.with_suffix(".tmp")
    with open(tmp_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=config.CSV_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp_path, config.CSV_PATH)

    for method, n in counts.items():
        log.info("[SCHATTING] %s: %d", method, n)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s", datefmt="%H:%M:%S")
    estimate()
