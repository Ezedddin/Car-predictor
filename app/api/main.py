"""API voor de Auto-Voorspeller: verwachte prijs van een occasion over 0-5 jaar.

Gebruikt de bestanden die model-building/model_training.ipynb maakt:
- model_catboost.cbm  het eindmodel (prijs bij het marktniveau van nu, in euro's van 2026)
- marktfactor.csv     laag / midden / hoog per aantal jaren vooruit (time series op de CBS-index)
- model_meta.json     features en het tijdstip van de nieuwste data

Starten (vanuit de map app/api):
    uvicorn main:app --reload
"""

import json
from pathlib import Path

import numpy as np
import pandas as pd
from catboost import CatBoostRegressor
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

MODEL_DIR = Path(__file__).resolve().parents[2] / "model-building"

model = CatBoostRegressor()
model.load_model(str(MODEL_DIR / "model_catboost.cbm"))
meta = json.loads((MODEL_DIR / "model_meta.json").read_text())
FEATURES = meta["features"]
T_NU = meta["t_nu"]
marktfactor = pd.read_csv(MODEL_DIR / "marktfactor.csv", index_col="jaren vooruit")
cpi = pd.read_csv(MODEL_DIR / "cpi.csv", index_col="year")["cpi_all"]

data = pd.read_parquet(MODEL_DIR / "dataset_tijd.parquet",
                       columns=["snapshot_date", "brand", "brand_model", "year", "new_price_eur",
                                "new_price_source", "fuel_type", "transmission"])
laatste = data["snapshot_date"].max()
NU = laatste.year + (laatste.month - 0.5) / 12   # zelfde leeftijdsdefinitie als in dataset_tijd.ipynb
MAX_JAREN = int(marktfactor.index.max())
BOUWJAREN = range(int(data["year"].min()), int(data["year"].max()) + 1)

# Keuzelijsten voor de frontend: per merk de modellen, gesorteerd op hoe vaak ze voorkomen
data["model"] = [bm[len(b) + 1:] for b, bm in zip(data["brand"], data["brand_model"])]
MODELLEN = {merk: groep["model"].value_counts().index.tolist() for merk, groep in data.groupby("brand")}
BRANDSTOFFEN = ["petrol", "diesel", "hybrid", "electric", "lpg", "other"]
TRANSMISSIES = ["manual", "automatic", "other"]

# Nieuwprijs uit de data: mediaan van de exacte nieuwprijzen (autoscout / RDW), van specifiek naar algemeen.
# Dezelfde aanpak als bij de Wayback-auto's in dataset_tijd.ipynb.
exact = data[data["new_price_source"].isin(["autoscout", "rdw_kenteken"])]
NIEUWPRIJS = [
    (["brand_model", "year", "fuel_type"], exact.groupby(["brand_model", "year", "fuel_type"])["new_price_eur"].median()),
    (["brand_model", "year"], exact.groupby(["brand_model", "year"])["new_price_eur"].median()),
    (["brand_model"], exact.groupby("brand_model")["new_price_eur"].median()),
]
# Meest voorkomende brandstof en transmissie per model, als standaardkeuze in het formulier
STANDAARD = data.groupby("brand_model")[["fuel_type", "transmission"]].agg(lambda s: s.mode().iloc[0])

app = FastAPI(title="Auto-Voorspeller API")


class Auto(BaseModel):
    merk: str
    model: str
    bouwjaar: int
    km: int = Field(ge=0, le=600_000, description="Kilometerstand nu")
    km_verkoop: int = Field(ge=0, le=700_000, description="Verwachte kilometerstand bij verkoop")
    verkoop_maanden: int = Field(ge=1, description="Over hoeveel maanden je wilt verkopen")
    brandstof: str
    transmissie: str
    inflatie: float = Field(default=0.0, ge=0, le=0.2, description="Verwachte inflatie per jaar, bijv. 0.02")


@app.get("/api/opties")
def opties():
    return {
        "modellen": MODELLEN,
        "brandstoffen": BRANDSTOFFEN,
        "transmissies": TRANSMISSIES,
        "bouwjaar": {"min": BOUWJAREN.start, "max": BOUWJAREN.stop - 1},
        "max_jaren": MAX_JAREN,
        "nu": str(laatste.to_period("M")),
    }


def zoek_nieuwprijs(brand_model, bouwjaar, brandstof):
    """Nieuwprijs (euro's van het bouwjaar) uit de data, of None als het model niet bekend is."""
    waarden = {"brand_model": brand_model, "year": bouwjaar, "fuel_type": brandstof}
    for kolommen, tabel in NIEUWPRIJS:
        sleutel = tuple(waarden[k] for k in kolommen)
        prijs = tabel.get(sleutel if len(sleutel) > 1 else sleutel[0])
        if prijs is not None and not pd.isna(prijs):
            return float(prijs)
    return None


@app.get("/api/voorstel")
def voorstel(merk: str, model: str):
    """Meest voorkomende brandstof en transmissie voor een model (standaardkeuze in het formulier)."""
    brand_model = f"{merk} {model}"
    standaard = STANDAARD.loc[brand_model] if brand_model in STANDAARD.index else None
    return {
        "brandstof": None if standaard is None else standaard["fuel_type"],
        "transmissie": None if standaard is None else standaard["transmission"],
    }


@app.post("/api/voorspel")
def voorspel(auto: Auto):
    if auto.bouwjaar not in BOUWJAREN:
        raise HTTPException(422, f"Bouwjaar moet tussen {BOUWJAREN.start} en {BOUWJAREN.stop - 1} liggen.")
    if auto.merk not in MODELLEN:
        raise HTTPException(422, f"Onbekend merk: {auto.merk}")
    if auto.brandstof not in BRANDSTOFFEN or auto.transmissie not in TRANSMISSIES:
        raise HTTPException(422, "Onbekende brandstof of transmissie.")

    if auto.verkoop_maanden > 12 * MAX_JAREN:
        raise HTTPException(422, f"Verkopen kan maximaal {MAX_JAREN} jaar vooruit worden voorspeld.")
    if auto.km_verkoop < auto.km:
        raise HTTPException(422, "De kilometerstand bij verkoop kan niet lager zijn dan nu.")

    brand_model = f"{auto.merk} {auto.model}"
    nieuwprijs = zoek_nieuwprijs(brand_model, auto.bouwjaar, auto.brandstof)
    if nieuwprijs is None:
        raise HTTPException(422, f"Geen nieuwprijs bekend voor de {brand_model}.")
    nieuwprijs_2026 = nieuwprijs * cpi.loc[2026] / cpi.loc[auto.bouwjaar]
    leeftijd = max(NU - (auto.bouwjaar + 0.5), 0)

    # Punten voor de grafiek: nu, elk half jaar, en het verkoopmoment. Km loopt gelijkmatig op tot km_verkoop.
    maanden = np.array(sorted({0, auto.verkoop_maanden, *range(6, auto.verkoop_maanden, 6)}))
    jaren = maanden / 12
    km = auto.km + (auto.km_verkoop - auto.km) * maanden / auto.verkoop_maanden
    toekomst = pd.DataFrame({
        "brand_model": brand_model,
        "brand": auto.merk,
        "fuel_type": auto.brandstof,
        "transmission": auto.transmissie,
        "age": leeftijd + jaren,
        "mileage_km": km,
        "new_price_2026": nieuwprijs_2026,
        "t": T_NU + maanden,
        "geschat": 1,   # afgeleid uit vergelijkbare auto's, net als bij de Wayback-data
    })[FEATURES]
    prijs = np.exp(model.predict(toekomst))

    punten = []
    for i, m in enumerate(maanden):
        datum = laatste.to_period("M") + int(m)
        inflatie = (1 + auto.inflatie) ** jaren[i]
        punten.append({
            "maanden": int(m),
            "datum": str(datum),
            "km": int(round(km[i])),
            # marktfactor per heel jaar; tussen twee jaren lineair geïnterpoleerd
            **{s: float(round(prijs[i] * np.interp(jaren[i], marktfactor.index, marktfactor[s]) * inflatie, -1))
               for s in ["laag", "midden", "hoog"]},
        })

    return {
        "punten": punten,
        "leeftijd": round(leeftijd, 1),
        "nieuwprijs": round(nieuwprijs, -2),
        "bekend_model": auto.model in MODELLEN[auto.merk],
        "euro_van": "dat jaar" if auto.inflatie > 0 else str(laatste.year),
    }
