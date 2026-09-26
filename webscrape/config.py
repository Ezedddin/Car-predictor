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

# Fixed search filters (in addition to brand, year and price)
SEARCH_PARAMS = {
    "atype": "C",          # passenger cars
    "cy": "NL",            # only listings located in the Netherlands
    "ustate": "N,U",       # new + used; 2025/2026 cars are often new/demo
    "pricetype": "public", # regular sale price, no lease price
    "sort": "price",       # stable ordering while paginating
    "desc": "0",
}

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

CSV_COLUMNS = ["brand", "model", "mileage_km", "year", "fuel_type", "price_eur", "transmission"]
