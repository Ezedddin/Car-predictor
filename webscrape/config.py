"""Settings for the AutoScout24 scraper."""

from pathlib import Path

BASE_URL = "https://www.autoscout24.nl"
SEARCH_URL = BASE_URL + "/lst/{slug}"

# Display name -> URL slug on AutoScout24
BRANDS = {
    "Audi": "audi",
    "BMW": "bmw",
    "Mercedes-Benz": "mercedes-benz",
    "Volkswagen": "volkswagen",
    "Volvo": "volvo",
    "Toyota": "toyota",
    "Ford": "ford",
    "Opel": "opel",
    "Peugeot": "peugeot",
    "Porsche": "porsche",
}

YEAR_START = 2005
YEAR_END = 2026

MIN_PRICE = 2000

# AutoScout24 body type filter value -> normalized body_type.
# Listings don't contain their body type, so every brand/year is searched once per
# body type. Together these values cover all listings (verified: BMW 2015, 643 = 643).
BODY_TYPES = {
    1: "hatchback",
    2: "convertible",
    3: "coupe",
    4: "suv",            # SUV/Off-Road/Pick-Up
    5: "station_wagon",
    6: "sedan",
    12: "mpv",
    13: "van",           # Bedrijfswagen
    7: "other",
}

# Fixed search filters (in addition to brand, year and price)
SEARCH_PARAMS = {
    "atype": "C",          # passenger cars
    "cy": "NL",            # only listings located in the Netherlands
    "ustate": "N,U",       # new + used; 2025/2026 cars are often new/demo
    "pricetype": "public", # regular sale price, no lease price
    "sort": "price",       # stable ordering while paginating
    "desc": "0",
}

# The search results only contain the original new price for part of the cars.
# For the others: open the listing page for the license plate and look up the
# catalogusprijs at RDW open data. The plate is only used for the lookup, never stored.
FETCH_MISSING_NEW_PRICE = True
RDW_URL = "https://opendata.rdw.nl/resource/m9d7-ebf2.json"
RDW_BATCH_SIZE = 50

# Delay between requests (seconds, random within this range)
DELAY_MIN = 3.0
DELAY_MAX = 6.0

REQUEST_TIMEOUT = 30
MAX_RETRIES = 3
# Safety limit against endless loops
MAX_PAGES = 200

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/128.0 Safari/537.36"
)

DATA_DIR = Path(__file__).resolve().parent / "data"
CSV_PATH = DATA_DIR / "cars.csv"
# Listing IDs already stored in cars.csv (for duplicate detection)
SEEN_IDS_PATH = DATA_DIR / "seen_ids.txt"
# Brand/year combinations that are fully done (to resume after a crash)
PROGRESS_PATH = DATA_DIR / "progress.txt"

CSV_COLUMNS = ["brand", "model", "mileage_km", "year", "fuel_type", "price_eur", "transmission", "body_type", "new_price_eur", "new_price_source"]

# ---------------------------------------------------------------------------
# Wayback Machine (wayback_scraper.py): historical listings 2020-2025
# ---------------------------------------------------------------------------

WAYBACK_CDX_URL = "https://web.archive.org/cdx/search/cdx"
# "id_" returns the original archived page without the Wayback toolbar
WAYBACK_PAGE_URL = "https://web.archive.org/web/{timestamp}id_/{url}"
# First month (yyyymm). Before 03-2023 the archived pages show German/Belgian cars, which the
# model doesn't use; set to "202001" to also collect those.
WAYBACK_FROM = "202303"
WAYBACK_YEAR_END = 2025
# Archived model pages are the default search page: page 1 (~20 listings), no country filter.
# Until early 2023 that page shows mostly German/Belgian cars, hence the country column.
WAYBACK_LISTING_URL = "https://www.autoscout24.nl/lst/{brand_slug}/{model_slug}"
# Some captures are empty (listings loaded via JavaScript); try a few per month
WAYBACK_TRIES_PER_MONTH = 3

# archive.org is a free service: keep the delay generous
WAYBACK_DELAY_MIN = 1.0
WAYBACK_DELAY_MAX = 2.0
WAYBACK_TIMEOUT = 60
WAYBACK_MAX_RETRIES = 5

WAYBACK_CSV_PATH = DATA_DIR / "wayback_cars.csv"
WAYBACK_SEEN_IDS_PATH = DATA_DIR / "wayback_seen_ids.txt"
# brand|model|yyyymm combinations that are done
WAYBACK_PROGRESS_PATH = DATA_DIR / "wayback_progress.txt"
# brand|model combinations without any archived page
WAYBACK_MISSING_PATH = DATA_DIR / "wayback_missing_models.txt"

# page_sort: sort order of the archived page ("price" = cheapest first, "standard" = AutoScout24 default)
WAYBACK_CSV_COLUMNS = ["snapshot_date", "country", "page_sort"] + CSV_COLUMNS
