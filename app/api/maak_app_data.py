"""Maakt de kleine bestanden die de API nodig heeft, uit dataset_tijd.parquet en het model.

Zo hoeft de server bij het opstarten niet de hele dataset te laden en past hij in 512 MB geheugen.
Opnieuw draaien na een nieuwe dataset of een nieuw model (vanuit de hoofdmap van het project):
    python app/api/maak_app_data.py

Schrijft naar model-building/app_data/:
- info.json            nieuwste snapshot, bouwjaren, modellen per merk, standaard brandstof/transmissie
- nieuwprijs_*.parquet mediaan van de exacte nieuwprijzen, van specifiek naar algemeen
- huidig.parquet       advertenties van nu met de verhouding vraagprijs / voorspelling (voor het ijken)
"""

import json
from pathlib import Path

import numpy as np
import pandas as pd
from catboost import CatBoostRegressor

MODEL_DIR = Path(__file__).resolve().parents[2] / "model-building"
UIT = MODEL_DIR / "app_data"
NIEUWPRIJS_NIVEAUS = [["brand_model", "year", "fuel_type"], ["brand_model", "year"], ["brand_model"]]


def main():
    UIT.mkdir(exist_ok=True)
    meta = json.loads((MODEL_DIR / "model_meta.json").read_text())
    features = meta["features"]

    data = pd.read_parquet(MODEL_DIR / "dataset_tijd.parquet")
    laatste = data["snapshot_date"].max()

    # Keuzelijsten voor de frontend: per merk de modellen, gesorteerd op hoe vaak ze voorkomen
    data["model"] = [bm[len(b) + 1:] for b, bm in zip(data["brand"], data["brand_model"])]
    modellen = {merk: groep["model"].value_counts().index.tolist() for merk, groep in data.groupby("brand")}
    # Meest voorkomende brandstof en transmissie per model, als standaardkeuze in het formulier
    standaard = data.groupby("brand_model")[["fuel_type", "transmission"]].agg(lambda s: s.mode().iloc[0])

    (UIT / "info.json").write_text(json.dumps({
        "laatste": laatste.strftime("%Y-%m-%d"),
        "bouwjaar_min": int(data["year"].min()),
        "bouwjaar_max": int(data["year"].max()),
        "modellen": modellen,
        "standaard": standaard.to_dict(orient="index"),
    }, ensure_ascii=False))

    # Nieuwprijs: dezelfde aanpak als bij de Wayback-auto's in dataset_tijd.ipynb
    exact = data[data["new_price_source"].isin(["autoscout", "rdw_kenteken"])]
    for i, kolommen in enumerate(NIEUWPRIJS_NIVEAUS):
        exact.groupby(kolommen)["new_price_eur"].median().reset_index().to_parquet(UIT / f"nieuwprijs_{i}.parquet")

    # Advertenties van nu: vraagprijs gedeeld door wat het model voor precies die auto voorspelt
    model = CatBoostRegressor()
    model.load_model(str(MODEL_DIR / "model_catboost.cbm"))
    huidig = data[data["snapshot_date"] == laatste].copy()
    huidig["t"] = meta["t_nu"]
    huidig["geschat"] = huidig["new_price_source"].str.startswith("schatting").astype(int)
    huidig["verhouding"] = huidig["price_2026"] / np.exp(model.predict(huidig[features]))
    huidig[["brand_model", "year", "fuel_type", "transmission", "mileage_km", "price_eur", "verhouding"]] \
        .reset_index(drop=True).to_parquet(UIT / "huidig.parquet")

    print(f"Klaar: {UIT} ({len(huidig):,} advertenties van {laatste:%Y-%m-%d})")


if __name__ == "__main__":
    main()
