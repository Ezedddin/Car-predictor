"""Historical AutoScout24 listings from the Wayback Machine (web.archive.org).

For every brand + model in data/cars.csv, this looks up the archived model page
(https://www.autoscout24.nl/lst/<brand>/<model>) for every month from 2020 to 2025
and stores the listings on it in data/wayback_cars.csv, together with the snapshot
date. That gives prices over time instead of only 2026.

Every snapshot is the default search page as it was crawled: page 1 (~20 listings),
no country filter. Until early 2023 those listings are mostly German/Belgian cars,
so the country of every listing is stored in the `country` column.

Usage:
    python wayback_scraper.py                              # all models from cars.csv
    python wayback_scraper.py --brand Volkswagen --model Golf  # one model (test)
    python wayback_scraper.py --rescan                     # also redo months that are done
"""

import argparse
import csv
import json
import logging
import os
import random
import re
import sys
import time
from collections import defaultdict

import requests
from bs4 import BeautifulSoup

import config
from scraper import (FUEL_CODES, FUEL_TEXT, is_lease_price, normalize_transmission,
                     parse_int)

log = logging.getLogger("wayback")


# ---------------------------------------------------------------------------
# Normalization
# ---------------------------------------------------------------------------

# AutoScout24 body type text (Dutch) -> normalized body_type, same values as scraper.py
BODY_TEXT = {
    "hatchback": "hatchback",
    "cabrio": "convertible",
    "coup": "coupe",
    "suv": "suv",
    "station": "station_wagon",
    "sedan": "sedan",
    "mpv": "mpv",
    "bedrijfswagen": "van",
}


def normalize_body(text):
    text = str(text or "").lower()
    if not text:
        return ""
    return next((v for k, v in BODY_TEXT.items() if k in text), "other")


def normalize_fuel(code, text):
    fuel = FUEL_CODES.get(str(code or "").lower())
    if fuel is None:
        text = str(text or "").lower()
        if "elektro/" in text or "hybride" in text:
            fuel = "hybrid"
        else:
            fuel = next((v for k, v in FUEL_TEXT.items() if k in text), None)
    return fuel or "other"


def find_year(*values):
    for value in values:
        match = re.search(r"(19|20)\d{2}", str(value or ""))
        if match:
            return int(match.group(0))
    return None


def raw(value):
    """Older pages wrap values as {"raw": ..., "formatted": ...}."""
    if isinstance(value, dict):
        return value.get("raw") if value.get("raw") is not None else value.get("formatted")
    return value


def model_slugs(model):
    """Candidate URL slugs for a model name, e.g. "C 200" -> "c-200", "RAV4" -> "rav-4"."""
    base = re.sub(r"\s+", "-", model.strip().lower())
    candidates = [base, re.sub(r"(?<=[a-z])(?=\d)", "-", base), base.replace("-", "")]
    return list(dict.fromkeys(c for c in candidates if c))


# ---------------------------------------------------------------------------
# Parsing (three page formats: old HTML until ~04-2022, two __NEXT_DATA__ layouts after)
# ---------------------------------------------------------------------------

def parse_next_listing(listing, brand, fallback_model):
    vehicle = listing.get("vehicle") or {}
    tracking = listing.get("tracking") or {}
    # 2023+: [{"iconName": ..., "data": ...}]; late 2022: plain strings like "Handgeschakeld"
    detail_list = listing.get("vehicleDetails") or []
    details = {d.get("iconName"): d.get("data") for d in detail_list if isinstance(d, dict)}
    detail_texts = [d for d in detail_list if isinstance(d, str)]
    if detail_texts and "transmission" not in details:
        details["transmission"] = next(
            (t for t in detail_texts if normalize_transmission(t) != "other"), None)

    # 2023+: "price"; 2022: "prices" -> "public"
    price = listing.get("price") or {}
    if not price:
        public = (listing.get("prices") or {}).get("public") or {}
        price = {"priceRaw": public.get("priceRaw"), "priceFormatted": public.get("price")}
    if is_lease_price(price):
        return None
    price_eur = parse_int(price.get("priceRaw")) or parse_int(tracking.get("price")) \
        or parse_int(price.get("priceFormatted"))
    if price_eur is None or price_eur < config.MIN_PRICE:
        return None

    mileage = parse_int(tracking.get("mileage"))
    if mileage is None:
        mileage = parse_int(raw(vehicle.get("mileageInKm")) or details.get("mileage_road"))

    fuel_category = vehicle.get("fuelCategory")
    fuel_code = fuel_category.get("raw") if isinstance(fuel_category, dict) else None
    fuel_text = fuel_category.get("formatted") if isinstance(fuel_category, dict) else fuel_category
    transmission = vehicle.get("transmission") or raw(vehicle.get("transmissionType")) \
        or details.get("transmission") or details.get("gearbox")
    new_price = parse_int(price.get("suggestedRetailPrice"))

    return {
        "country": (listing.get("location") or {}).get("countryCode") or "",
        "brand": brand,
        "model": (vehicle.get("model") or vehicle.get("modelGroup") or fallback_model).strip(),
        "mileage_km": mileage if mileage is not None else "",
        "year": find_year(tracking.get("firstRegistration"), raw(vehicle.get("firstRegistrationDate")),
                          details.get("calendar")) or "",
        "fuel_type": normalize_fuel(tracking.get("fuelType") or fuel_code,
                                    vehicle.get("fuel") or fuel_text
                                    or details.get("nozzle") or details.get("gas_pump")),
        "price_eur": price_eur,
        "transmission": normalize_transmission(transmission),
        "body_type": normalize_body(raw(vehicle.get("bodyType"))),
        "new_price_eur": new_price or "",
        "new_price_source": "autoscout" if new_price else "",
    }


def parse_old_listing(item, brand, fallback_model):
    price_el = item.select_one("[data-item-name='price']")
    price_text = price_el.get_text(" ", strip=True) if price_el else ""
    if is_lease_price({"priceFormatted": price_text}):
        return None
    price_eur = parse_int(price_text)
    if price_eur is None or price_eur < config.MIN_PRICE:
        return None

    mileage = year = fuel_text = None
    for li in item.select("[data-item-name='vehicle-details'] li, ul li"):
        text = li.get_text(" ", strip=True)
        if mileage is None and re.search(r"\d\s*km$", text):
            mileage = parse_int(text)
        elif year is None and re.fullmatch(r"\d{2}/\d{4}", text):
            year = find_year(text)
        elif fuel_text is None and any(k in text.lower() for k in FUEL_TEXT):
            fuel_text = text
    transmission = item.select_one("[data-item-name='transmission-type']")

    title = item.select_one(".cldt-summary-makemodel")
    model = title.get_text(" ", strip=True) if title else ""
    if model.lower().startswith(brand.lower()):
        model = model[len(brand):].strip()

    seller = item.select_one("[data-item-name='seller']")
    country = re.search(r"\b([A-Z]{2})[- ]?\d{4}", seller.get_text(" ", strip=True)) if seller else None

    return {
        "country": country.group(1) if country else "",
        "brand": brand,
        "model": model or fallback_model,
        "mileage_km": mileage if mileage is not None else "",
        "year": year or "",
        "fuel_type": normalize_fuel(None, fuel_text),
        "price_eur": price_eur,
        "transmission": normalize_transmission(transmission.get_text(strip=True) if transmission else ""),
        "body_type": "",
        "new_price_eur": "",
        "new_price_source": "",
    }


def same_model_name(row, model):
    """Use the spelling from cars.csv when only spaces/dashes differ (old pages: "RAV 4" vs "RAV4")."""
    compact = lambda m: re.sub(r"[\s-]", "", m).lower()
    if compact(row["model"]) == compact(model):
        row["model"] = model
    return row


def parse_snapshot(html, brand, model):
    """Returns {listing_id: row} for one archived page."""
    rows = {}
    match = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', html, re.S)
    if match:
        props = json.loads(match.group(1))["props"]["pageProps"]
        query = props.get("pageQuery") or {}
        sort = str(query.get("sort") or "") + ("_desc" if str(query.get("desc")) == "1" else "")
        for listing in props.get("listings") or []:
            if str((listing.get("vehicle") or {}).get("make") or "").lower() != brand.lower():
                continue  # e.g. sponsored listings of another brand
            row = parse_next_listing(listing, brand, model)
            if listing.get("id") and row:
                rows[listing["id"]] = dict(same_model_name(row, model), page_sort=sort)
        return rows

    soup = BeautifulSoup(html, "html.parser")
    for item in soup.select("div.cldt-summary-full-item"):
        container = item.find_parent(attrs={"data-guid": True})
        listing_id = container.get("data-guid") if container else None
        title = item.select_one(".cldt-summary-makemodel")
        if not listing_id or not title or not title.get_text(strip=True).lower().startswith(brand.lower()):
            continue
        row = parse_old_listing(item, brand, model)
        if row:
            # The old site showed the cheapest cars first
            rows[listing_id] = dict(same_model_name(row, model), page_sort="price")
    return rows


# ---------------------------------------------------------------------------
# Storage
# ---------------------------------------------------------------------------

def read_lines(path):
    if not path.exists():
        return set()
    with open(path, encoding="utf-8") as f:
        return {line.strip() for line in f if line.strip()}


def append_lines(path, lines):
    with open(path, "a", encoding="utf-8") as f:
        for line in lines:
            f.write(line + "\n")
        f.flush()
        os.fsync(f.fileno())


class Storage:
    def __init__(self):
        config.DATA_DIR.mkdir(parents=True, exist_ok=True)
        path = config.WAYBACK_CSV_PATH
        if not path.exists() or path.stat().st_size == 0:
            with open(path, "w", newline="", encoding="utf-8") as f:
                csv.writer(f).writerow(config.WAYBACK_CSV_COLUMNS)
        with open(path, newline="", encoding="utf-8") as f:
            header = next(csv.reader(f), [])
        if header != config.WAYBACK_CSV_COLUMNS:
            sys.exit(f"{path} heeft andere kolommen dan verwacht. Verplaats het bestand en start opnieuw.")
        self.seen_ids = read_lines(config.WAYBACK_SEEN_IDS_PATH)
        self.done = read_lines(config.WAYBACK_PROGRESS_PATH)

    def save(self, rows_by_id, snapshot_date):
        """Store listings we haven't seen before (a car stays online for months: keep the first snapshot)."""
        new = {i: dict(r, snapshot_date=snapshot_date) for i, r in rows_by_id.items() if i not in self.seen_ids}
        if new:
            with open(config.WAYBACK_CSV_PATH, "a", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=config.WAYBACK_CSV_COLUMNS)
                writer.writerows(new.values())
                f.flush()
                os.fsync(f.fileno())
            append_lines(config.WAYBACK_SEEN_IDS_PATH, new.keys())
            self.seen_ids.update(new.keys())
        return len(new)

    def mark_done(self, key):
        append_lines(config.WAYBACK_PROGRESS_PATH, [key])
        self.done.add(key)


# ---------------------------------------------------------------------------
# HTTP
# ---------------------------------------------------------------------------

class Client:
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": "Auto-Voorspeller (school project; historical car prices)"})
        self.last_request = 0.0

    def _wait(self):
        delay = random.uniform(config.WAYBACK_DELAY_MIN, config.WAYBACK_DELAY_MAX)
        remaining = self.last_request + delay - time.time()
        if remaining > 0:
            time.sleep(remaining)
        self.last_request = time.time()

    def get(self, url, params=None):
        for attempt in range(1, config.WAYBACK_MAX_RETRIES + 1):
            self._wait()
            try:
                resp = self.session.get(url, params=params, timeout=config.WAYBACK_TIMEOUT)
            except requests.RequestException as exc:
                log.warning("Netwerkfout (poging %d/%d): %s", attempt, config.WAYBACK_MAX_RETRIES, exc)
                time.sleep(20 * attempt)
                continue
            # archive.org answers "Temporarily Offline" with 200/503 when it is overloaded
            offline = "Temporarily Offline" in resp.text[:3000]
            if resp.status_code == 200 and not offline:
                return resp.text
            if resp.status_code in (404, 403):
                return None
            wait = parse_int(resp.headers.get("Retry-After")) or 60 * attempt
            log.warning("HTTP %d%s, %ds wachten (poging %d/%d)", resp.status_code,
                        " (Temporarily Offline)" if offline else "", wait, attempt, config.WAYBACK_MAX_RETRIES)
            time.sleep(wait)
        return None


def monthly_snapshots(client, url):
    """{yyyymm: [timestamps]} for all successful captures of url in the configured years."""
    text = client.get(config.WAYBACK_CDX_URL, {
        "url": url,
        "from": config.WAYBACK_FROM,
        "to": config.WAYBACK_YEAR_END,
        "output": "json",
        "fl": "timestamp",
        "filter": "statuscode:200",
        "collapse": "timestamp:8",  # at most one capture per day
    })
    if text is None:
        raise RuntimeError(f"CDX-opvraging mislukt voor {url}")
    months = defaultdict(list)
    for (timestamp,) in (json.loads(text)[1:] if text.strip() else []):
        months[timestamp[:6]].append(timestamp)
    return months


# ---------------------------------------------------------------------------
# Scraping
# ---------------------------------------------------------------------------

def load_models(brand_filter=None, model_filter=None):
    """Unique (brand, model) pairs from cars.csv, most listings first."""
    counts = defaultdict(int)
    with open(config.CSV_PATH, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            if row["model"] and row["model"] != "Overig":
                counts[(row["brand"], row["model"])] += 1
    pairs = sorted(counts, key=lambda p: -counts[p])
    if brand_filter:
        pairs = [p for p in pairs if p[0].lower() == brand_filter.lower()]
    if model_filter:
        pairs = [p for p in pairs if p[1].lower() == model_filter.lower()]
    return pairs


def scrape_model(client, storage, brand, model, rescan):
    brand_slug = config.BRANDS[brand]
    missing = read_lines(config.WAYBACK_MISSING_PATH)
    if f"{brand}|{model}" in missing and not rescan:
        log.info("[SKIP] %s %s (geen archief)", brand, model)
        return 0

    url, months = None, {}
    for slug in model_slugs(model):
        candidate = config.WAYBACK_LISTING_URL.format(brand_slug=brand_slug, model_slug=slug)
        months = monthly_snapshots(client, candidate)
        if months:
            url = candidate
            break
    if not url:
        log.info("[MISSING] %s %s - geen snapshots gevonden", brand, model)
        append_lines(config.WAYBACK_MISSING_PATH, [f"{brand}|{model}"])
        return 0

    todo = [m for m in sorted(months) if f"{brand}|{model}|{m}" not in storage.done or rescan]
    log.info("[START] %s %s - %d maanden in archief, %d te doen (%s)", brand, model, len(months), len(todo), url)

    saved_total = 0
    for month in todo:
        rows, used = {}, None
        for timestamp in months[month][:config.WAYBACK_TRIES_PER_MONTH]:
            html = client.get(config.WAYBACK_PAGE_URL.format(timestamp=timestamp, url=url))
            if not html:
                continue
            try:
                rows = parse_snapshot(html, brand, model)
            except Exception as exc:
                log.warning("%s %s %s - snapshot niet te lezen: %s", brand, model, timestamp, exc)
                continue
            if rows:
                used = timestamp
                break

        snapshot_date = f"{used[:4]}-{used[4:6]}-{used[6:8]}" if used else ""
        saved = storage.save(rows, snapshot_date) if used else 0
        saved_total += saved
        countries = defaultdict(int)
        for r in rows.values():
            countries[r["country"] or "?"] += 1
        log.info("%s %s %s - %d listings (%s), %d nieuw", brand, model, month, len(rows),
                 ", ".join(f"{c}:{n}" for c, n in sorted(countries.items())) or "-", saved)
        storage.mark_done(f"{brand}|{model}|{month}")

    log.info("[DONE] %s %s - %d auto's opgeslagen", brand, model, saved_total)
    return saved_total


def main():
    parser = argparse.ArgumentParser(description="AutoScout24 historische listings via de Wayback Machine")
    parser.add_argument("--brand", help="Alleen dit merk (bijv. BMW)")
    parser.add_argument("--model", help="Alleen dit model (bijv. X1)")
    parser.add_argument("--rescan", action="store_true", help="Ook al afgeronde maanden opnieuw doen")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s", datefmt="%H:%M:%S")

    pairs = load_models(args.brand, args.model)
    if not pairs:
        sys.exit("Geen modellen gevonden in cars.csv voor deze selectie.")
    log.info("%d modellen te doorlopen", len(pairs))

    storage = Storage()
    client = Client()
    total = 0
    try:
        for n, (brand, model) in enumerate(pairs, 1):
            log.info("--- model %d/%d", n, len(pairs))
            try:
                total += scrape_model(client, storage, brand, model, args.rescan)
            except RuntimeError as exc:
                log.error("%s - overgeslagen, wordt bij de volgende run opnieuw geprobeerd", exc)
    except KeyboardInterrupt:
        log.info("Onderbroken door gebruiker.")

    log.info("Klaar. %d nieuwe auto's opgeslagen in %s (totaal %d listings).",
             total, config.WAYBACK_CSV_PATH, len(storage.seen_ids))


if __name__ == "__main__":
    main()
