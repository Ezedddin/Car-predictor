"""AutoScout24 Netherlands scraper.

Walks through all result pages per brand and per year and stores the cars
in data/cars.csv. The search results are embedded as JSON in the <script id="__NEXT_DATA__">
of every page, so requests + BeautifulSoup is enough (no JavaScript needed).

Usage:
    python scraper.py                         # all brands, 2005 to 2026
    python scraper.py --brand BMW --year 2015 # a single combination (test)
    python scraper.py --rescan                # also redo combinations that are already done
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
import urllib.robotparser

import requests
from bs4 import BeautifulSoup

import config

log = logging.getLogger("autoscout24")


class BlockedError(Exception):
    """AutoScout24 refuses access (403 / CAPTCHA). We stop instead of working around it."""


# ---------------------------------------------------------------------------
# Normalization
# ---------------------------------------------------------------------------

# AutoScout24 fuel codes (tracking.fuelType)
FUEL_CODES = {
    "b": "petrol",
    "d": "diesel",
    "e": "electric",
    "2": "hybrid",   # electric/petrol
    "3": "hybrid",   # electric/diesel
    "l": "lpg",
}

FUEL_TEXT = {
    "benzine": "petrol",
    "diesel": "diesel",
    "elektrisch": "electric",
    "elektro": "electric",
    "lpg": "lpg",
}

def normalize_fuel(listing):
    vehicle = listing.get("vehicle") or {}
    code = str((listing.get("tracking") or {}).get("fuelType") or "").lower()
    text = str(vehicle.get("fuel") or "").lower()

    fuel = FUEL_CODES.get(code)
    if fuel is None:
        # "Elektro/Benzine" and "Elektro/Diesel" are both stored as hybrid
        if "elektro/" in text or "hybride" in text:
            fuel = "hybrid"
        else:
            fuel = next((v for k, v in FUEL_TEXT.items() if k in text), None)
    return fuel or "other"


def normalize_transmission(value):
    text = str(value or "").lower()
    if "automa" in text or "semi" in text:
        return "automatic"
    if "hand" in text or "manual" in text:
        return "manual"
    return "other"


def parse_int(value):
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return int(value)
    digits = re.sub(r"[^\d]", "", str(value))
    return int(digits) if digits else None


def parse_year(listing):
    reg = (listing.get("tracking") or {}).get("firstRegistration") or ""
    match = re.search(r"(19|20)\d{2}", str(reg))
    if match:
        return int(match.group(0))
    for detail in listing.get("vehicleDetails") or []:
        if detail.get("iconName") == "calendar":
            match = re.search(r"(19|20)\d{2}", str(detail.get("data") or ""))
            if match:
                return int(match.group(0))
    return None


def is_lease_price(price):
    """True if the price is a monthly / lease amount instead of a purchase price."""
    text = " ".join(
        str(price.get(k) or "") for k in ("priceFormatted", "priceSuperscriptString", "vatLabel")
    ).lower()
    return any(marker in text for marker in ("p/m", "/mnd", "per maand", "/maand", "lease", "p.m."))


def parse_listing(listing, brand, search_year):
    """Convert one raw listing into a CSV row. Returns None if the listing is not usable."""
    vehicle = listing.get("vehicle") or {}
    price = listing.get("price") or {}

    if is_lease_price(price):
        return None
    price_eur = parse_int(price.get("priceRaw"))
    if price_eur is None:
        price_eur = parse_int(price.get("priceFormatted"))
    if price_eur is None or price_eur < config.MIN_PRICE:
        return None

    mileage = parse_int((listing.get("tracking") or {}).get("mileage"))
    if mileage is None:
        mileage = parse_int(vehicle.get("mileageInKm"))

    model = (vehicle.get("model") or vehicle.get("modelGroup") or "").strip()

    return {
        "brand": brand,
        "model": model,
        "mileage_km": mileage if mileage is not None else "",
        "year": parse_year(listing) or search_year,
        "fuel_type": normalize_fuel(listing),
        "price_eur": price_eur,
        "transmission": normalize_transmission(vehicle.get("transmission")),
    }


# ---------------------------------------------------------------------------
# Storage
# ---------------------------------------------------------------------------

class Storage:
    def __init__(self):
        config.DATA_DIR.mkdir(parents=True, exist_ok=True)
        if not config.CSV_PATH.exists() or config.CSV_PATH.stat().st_size == 0:
            with open(config.CSV_PATH, "w", newline="", encoding="utf-8") as f:
                csv.writer(f).writerow(config.CSV_COLUMNS)
        self.seen_ids = self._read_lines(config.SEEN_IDS_PATH)
        self.done = self._read_lines(config.PROGRESS_PATH)

    @staticmethod
    def _read_lines(path):
        if not path.exists():
            return set()
        with open(path, encoding="utf-8") as f:
            return {line.strip() for line in f if line.strip()}

    @staticmethod
    def _append(path, lines):
        with open(path, "a", encoding="utf-8") as f:
            for line in lines:
                f.write(line + "\n")
            f.flush()
            os.fsync(f.fileno())

    def save(self, rows_by_id):
        """Write new rows to disk immediately. rows_by_id: {listing_id: row}."""
        new = {i: r for i, r in rows_by_id.items() if i not in self.seen_ids}
        if not new:
            return 0
        with open(config.CSV_PATH, "a", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=config.CSV_COLUMNS)
            writer.writerows(new.values())
            f.flush()
            os.fsync(f.fileno())
        self._append(config.SEEN_IDS_PATH, new.keys())
        self.seen_ids.update(new.keys())
        return len(new)

    def mark_done(self, key):
        self._append(config.PROGRESS_PATH, [key])
        self.done.add(key)


# ---------------------------------------------------------------------------
# HTTP
# ---------------------------------------------------------------------------

class Client:
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": config.USER_AGENT,
            "Accept": "text/html,application/xhtml+xml",
            "Accept-Language": "nl-NL,nl;q=0.9",
        })
        self.robots = urllib.robotparser.RobotFileParser(config.BASE_URL + "/robots.txt")
        try:
            self.robots.read()
        except Exception as exc:
            log.warning("Kon robots.txt niet lezen (%s)", exc)
            self.robots = None
        self.last_request = 0.0

    def _wait(self):
        delay = random.uniform(config.DELAY_MIN, config.DELAY_MAX)
        remaining = self.last_request + delay - time.time()
        if remaining > 0:
            time.sleep(remaining)
        self.last_request = time.time()

    def get(self, url, params):
        full_url = requests.Request("GET", url, params=params).prepare().url
        if self.robots and not self.robots.can_fetch("*", full_url):
            raise PermissionError(f"robots.txt staat {full_url} niet toe")

        for attempt in range(1, config.MAX_RETRIES + 1):
            self._wait()
            try:
                resp = self.session.get(url, params=params, timeout=config.REQUEST_TIMEOUT)
            except requests.RequestException as exc:
                log.warning("Netwerkfout (poging %d/%d): %s", attempt, config.MAX_RETRIES, exc)
                time.sleep(10 * attempt)
                continue

            if resp.status_code == 200:
                if "captcha" in resp.text[:5000].lower() and "__NEXT_DATA__" not in resp.text:
                    raise BlockedError("CAPTCHA-pagina ontvangen")
                return resp.text
            if resp.status_code == 403:
                raise BlockedError("HTTP 403 Forbidden")
            if resp.status_code == 429 or resp.status_code >= 500:
                wait = parse_int(resp.headers.get("Retry-After")) or 30 * attempt
                log.warning("HTTP %d, %ds wachten (poging %d/%d)",
                            resp.status_code, wait, attempt, config.MAX_RETRIES)
                time.sleep(wait)
                continue
            log.warning("HTTP %d voor %s", resp.status_code, full_url)
            return None
        return None


# ---------------------------------------------------------------------------
# Scraping
# ---------------------------------------------------------------------------

def parse_page(html):
    soup = BeautifulSoup(html, "html.parser")
    script = soup.find("script", id="__NEXT_DATA__")
    if script is None or not script.string:
        raise ValueError("__NEXT_DATA__ niet gevonden in pagina")
    props = json.loads(script.string)["props"]["pageProps"]
    return props.get("listings") or [], props.get("numberOfPages") or 0, props.get("numberOfResults") or 0


def scrape_brand_year(client, storage, brand, slug, year):
    log.info("[START] %s - %d", brand, year)
    url = config.SEARCH_URL.format(slug=slug)
    rows = {}
    page = 1
    total_pages = None

    while page <= config.MAX_PAGES:
        params = dict(config.SEARCH_PARAMS,
                      fregfrom=year, fregto=year, pricefrom=config.MIN_PRICE, page=page)
        try:
            html = client.get(url, params)
            if html is None:
                log.error("%s %d - page %d - overgeslagen (geen geldige response)", brand, year, page)
                page += 1
                if total_pages is None:
                    break
                continue
            listings, n_pages, n_results = parse_page(html)
        except (BlockedError, PermissionError):
            raise
        except Exception as exc:
            log.error("%s %d - page %d - fout: %s", brand, year, page, exc)
            page += 1
            if total_pages is None:
                break
            continue

        if total_pages is None:
            total_pages = n_pages
            log.info("%s %d - %d resultaten op %d pagina's", brand, year, n_results, n_pages)

        page_rows = 0
        for listing in listings:
            try:
                listing_id = listing.get("id")
                if not listing_id or listing_id in rows:
                    continue
                if str((listing.get("vehicle") or {}).get("make") or "").lower() != brand.lower():
                    continue  # e.g. sponsored listings of another brand
                row = parse_listing(listing, brand, year)
                if row is not None:
                    rows[listing_id] = row
                    page_rows += 1
            except Exception as exc:
                log.warning("%s %d - page %d - listing overgeslagen: %s", brand, year, page, exc)

        log.info("%s %d - page %d - %d cars found", brand, year, page, page_rows)

        if not listings or page >= (total_pages or 0):
            break
        page += 1

    saved = storage.save(rows)
    log.info("[DONE] %s - %d - %d cars saved (%d gevonden, %d al aanwezig)",
             brand, year, saved, len(rows), len(rows) - saved)
    return saved


def main():
    parser = argparse.ArgumentParser(description="AutoScout24 NL scraper")
    parser.add_argument("--brand", help="Alleen dit merk (bijv. BMW)")
    parser.add_argument("--year", type=int, help="Alleen dit bouwjaar (bijv. 2015)")
    parser.add_argument("--rescan", action="store_true",
                        help="Ook merk/jaar-combinaties opnieuw scrapen die al afgerond zijn")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s", datefmt="%H:%M:%S")

    brands = config.BRANDS
    if args.brand:
        match = {b: s for b, s in brands.items() if b.lower() == args.brand.lower()}
        if not match:
            sys.exit(f"Onbekend merk: {args.brand}. Kies uit: {', '.join(brands)}")
        brands = match
    years = [args.year] if args.year else range(config.YEAR_START, config.YEAR_END + 1)

    storage = Storage()
    client = Client()
    total = 0

    try:
        for brand, slug in brands.items():
            for year in years:
                key = f"{brand}|{year}"
                if key in storage.done and not args.rescan:
                    log.info("[SKIP] %s - %d (al afgerond)", brand, year)
                    continue
                total += scrape_brand_year(client, storage, brand, slug, year)
                storage.mark_done(key)
    except BlockedError as exc:
        log.error("Toegang geweigerd door AutoScout24 (%s). Scraper stopt; probeer later opnieuw.", exc)
    except PermissionError as exc:
        log.error("%s. Scraper stopt.", exc)
    except KeyboardInterrupt:
        log.info("Onderbroken door gebruiker.")

    log.info("Klaar. %d nieuwe auto's opgeslagen in %s (totaal %d listings).",
             total, config.CSV_PATH, len(storage.seen_ids))


if __name__ == "__main__":
    main()
