"""API voor de Auto-Voorspeller: verwachte prijs van een occasion over 0-5 jaar.

Gebruikt de bestanden die model-building/model_training.ipynb maakt:
- model_catboost.cbm  het eindmodel (prijs bij het marktniveau van nu, in euro's van 2026)
- marktfactor.csv     laag / midden / hoog per aantal jaren vooruit (time series op de CBS-index)
- model_meta.json     features en het tijdstip van de nieuwste data
En de opzoektabellen in model-building/app_data/ (gemaakt door maak_app_data.py).

Starten (vanuit de map app/api):
    uvicorn main:app --reload
"""

import json
from pathlib import Path

import numpy as np
import pandas as pd
from catboost import CatBoostRegressor
from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

MODEL_DIR = Path(__file__).resolve().parents[2] / "model-building"

model = CatBoostRegressor()
model.load_model(str(MODEL_DIR / "model_catboost.cbm"))
meta = json.loads((MODEL_DIR / "model_meta.json").read_text())
FEATURES = meta["features"]
T_NU = meta["t_nu"]
marktfactor = pd.read_csv(MODEL_DIR / "marktfactor.csv", index_col="jaren vooruit")
cpi = pd.read_csv(MODEL_DIR / "cpi.csv", index_col="year")["cpi_all"]

# Opzoektabellen uit de dataset, vooraf gemaakt door maak_app_data.py (zodat de server niet de hele dataset laadt)
APP_DATA = MODEL_DIR / "app_data"
info = json.loads((APP_DATA / "info.json").read_text())
laatste = pd.Timestamp(info["laatste"])
NU = laatste.year + (laatste.month - 0.5) / 12   # zelfde leeftijdsdefinitie als in dataset_tijd.ipynb
MAX_JAREN = int(marktfactor.index.max())
BOUWJAREN = range(info["bouwjaar_min"], info["bouwjaar_max"] + 1)

# Keuzelijsten voor de frontend: per merk de modellen, gesorteerd op hoe vaak ze voorkomen
MODELLEN = info["modellen"]
BRANDSTOFFEN = ["petrol", "diesel", "hybrid", "electric", "lpg", "other"]
TRANSMISSIES = ["manual", "automatic", "other"]
# Meest voorkomende brandstof en transmissie per model, als standaardkeuze in het formulier
STANDAARD = info["standaard"]

# Nieuwprijs uit de data: mediaan van de exacte nieuwprijzen (autoscout / RDW), van specifiek naar algemeen.
# Dezelfde aanpak als bij de Wayback-auto's in dataset_tijd.ipynb.
NIEUWPRIJS = []
for i in range(3):
    tabel = pd.read_parquet(APP_DATA / f"nieuwprijs_{i}.parquet")
    kolommen = [k for k in tabel.columns if k != "new_price_eur"]
    NIEUWPRIJS.append((kolommen, tabel.set_index(kolommen)["new_price_eur"]))

# Advertenties van nu (nieuwste AutoScout24-snapshot), om de prijs van nu te ijken aan wat er echt gevraagd wordt.
# Per advertentie: vraagprijs gedeeld door wat het model voor precies die auto voorspelt.
huidig = pd.read_parquet(APP_DATA / "huidig.parquet")
MIN_VERGELIJKBAAR = 5
MAX_CORRECTIE = 0.2   # het model hooguit 20% bijstellen


def vergelijkbare(brand_model, bouwjaar, brandstof, transmissie):
    """Advertenties van nu voor hetzelfde model en bouwjaar, zo specifiek als de data toelaat."""
    basis = huidig[(huidig["brand_model"] == brand_model) & (huidig["year"] == bouwjaar)]
    for groep in (basis[(basis["fuel_type"] == brandstof) & (basis["transmission"] == transmissie)],
                  basis[basis["fuel_type"] == brandstof],
                  basis):
        if len(groep) >= MIN_VERGELIJKBAAR:
            return groep
    return basis.iloc[:0]

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
    standaard = STANDAARD.get(f"{merk} {model}", {})
    return {"brandstof": standaard.get("fuel_type"), "transmissie": standaard.get("transmission")}


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
        "geschat": 0,   # mediaan van exacte nieuwprijzen, net als bij de advertenties waarmee we ijken
    })[FEATURES]
    prijs = np.exp(model.predict(toekomst))

    # IJken: zit het model voor vergelijkbare advertenties van nu structureel te hoog of te laag, dan schuift de
    # hele lijn mee. Het waardeverloop (de vorm van de lijn) blijft van het model.
    groep = vergelijkbare(brand_model, auto.bouwjaar, auto.brandstof, auto.transmissie)
    correctie = float(np.clip(groep["verhouding"].median(), 1 - MAX_CORRECTIE, 1 + MAX_CORRECTIE)) if len(groep) else 1.0
    prijs *= correctie

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
        "vergelijkbaar": None if groep.empty else {
            "aantal": len(groep),
            "mediaan_prijs": round(float(groep["price_eur"].median()), -1),
            "mediaan_km": int(round(groep["mileage_km"].median(), -3)),
            "correctie": round(correctie - 1, 3),
        },
        "euro_van": "dat jaar" if auto.inflatie > 0 else str(laatste.year),
    }


# De gebouwde frontend (npm run build in app/frontend) op dezelfde server, zodat één server genoeg is.
# Staat onderaan, zodat de /api-routes voorgaan.
DIST = Path(__file__).resolve().parents[1] / "frontend" / "dist"
if DIST.exists():
    app.mount("/", StaticFiles(directory=DIST, html=True), name="frontend")
