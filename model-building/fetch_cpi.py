"""Download the consumer price index (CPI) per year from CBS StatLine and save it as cpi.csv.

Sources (CBS open data):
- 86141NED  Consumentenprijzen; CPI 2025=100 (2010 - now)
- 83131NED  Consumentenprijzen; prijsindex 2015=100 (1996 - 2025), used for the years before 2010.
  Those values are rescaled to 2025=100 via the overlapping year 2015.

Columns in cpi.csv (2025 = 100):
- cpi_all        "000000 Alle bestedingen"  -> general inflation
- cpi_used_cars  "071120 Tweedehandsauto's" -> price development of used cars

For the current year the full year figure is not published yet; the most recent month is used instead.

Usage:
    python fetch_cpi.py
"""

from pathlib import Path

import pandas as pd
import requests

ODATA = "https://opendata.cbs.nl/ODataApi/odata/{table}/TypedDataSet"
NEW_TABLE = "86141NED"   # 2025=100
OLD_TABLE = "83131NED"   # 2015=100
CATEGORIES = {
    "cpi_all": "T001112  ",
    "cpi_used_cars": "CPI071120",
}
FIRST_YEAR = 2005
OUT_PATH = Path(__file__).resolve().parent / "cpi.csv"


def fetch(table, category):
    """All periods for one category: DataFrame with columns Perioden, CPI_1."""
    params = {
        "$filter": f"Bestedingscategorieen eq '{category}'",
        "$select": "Perioden,CPI_1",
    }
    resp = requests.get(ODATA.format(table=table), params=params, timeout=30)
    resp.raise_for_status()
    return pd.DataFrame(resp.json()["value"]).dropna()


def yearly(df):
    """{year: index} from the year figures ("2015JJ00"), plus the latest month for an incomplete year."""
    years = {int(p[:4]): v for p, v in zip(df["Perioden"], df["CPI_1"]) if p.endswith("JJ00")}
    months = df[df["Perioden"].str.contains("MM")].sort_values("Perioden")
    if not months.empty:
        last_year = int(months["Perioden"].iloc[-1][:4])
        if last_year not in years:
            years[last_year] = months["CPI_1"].iloc[-1]
    return years


def main():
    columns = {}
    for name, category in CATEGORIES.items():
        new = yearly(fetch(NEW_TABLE, category))
        old = yearly(fetch(OLD_TABLE, category))
        factor = new[2015] / old[2015]
        series = {y: round(v * factor, 2) for y, v in old.items() if y < min(new)}
        series.update(new)
        columns[name] = series

    cpi = pd.DataFrame(columns).sort_index()
    cpi = cpi[cpi.index >= FIRST_YEAR]
    cpi.index.name = "year"
    cpi.to_csv(OUT_PATH)
    print(cpi)
    print(f"Opgeslagen in {OUT_PATH}")


if __name__ == "__main__":
    main()
