# Auto-Voorspeller: web-app

Vul je auto in, wanneer je hem wilt verkopen en met hoeveel km, en zie de verwachte prijs op dat moment (tot 5 jaar vooruit), met een bandbreedte.

```
app/
  api/        FastAPI: laadt het model en rekent de voorspelling uit
  frontend/   React (Vite): formulier, grafiek en tabel
```

De API gebruikt de bestanden die `model-building/model_training.ipynb` maakt:
`model_catboost.cbm`, `marktfactor.csv`, `model_meta.json` (plus `cpi.csv`), en de opzoektabellen in
`model-building/app_data/`. Die laatste maak je na een nieuwe dataset of een nieuw model opnieuw met:

```bash
python app/api/maak_app_data.py
```

Zo hoeft de server de hele dataset niet te laden en past hij in 512 MB geheugen.

## Online zetten (Render)

De `Dockerfile` in de hoofdmap bouwt de frontend en zet die samen met de API en het model in één container.
`render.yaml` vertelt Render hoe:

1. Log in op <https://render.com> met je GitHub-account.
2. **New → Blueprint**, kies deze repo. Render leest `render.yaml` en bouwt de container (gratis plan).
3. Na het bouwen staat de app op `https://auto-voorspeller-xxxx.onrender.com`. Elke push naar `main` zet automatisch de nieuwe versie online.

Het gratis plan valt na 15 minuten zonder bezoek in slaap; het eerste bezoek daarna duurt ongeveer een minuut.

## Starten

**Snel (één server).** Als `app/frontend/dist` bestaat (`npm run build` in `app/frontend`), serveert de API ook de frontend:

```bash
python -m uvicorn main:app --app-dir app/api --port 8000
```

Open <http://localhost:8000>.

**Ontwikkelen (met hot reload).** Twee terminals, allebei vanuit de hoofdmap van het project.

**1. API** (poort 8000)

```bash
pip install -r app/api/requirements.txt
python -m uvicorn main:app --app-dir app/api --port 8000 --reload
```

Testen: <http://localhost:8000/docs>

**2. Frontend** (poort 5173)

```bash
cd app/frontend
npm install
npm run dev
```

Open <http://localhost:5173>. Verzoeken naar `/api` worden doorgestuurd naar de API (zie `vite.config.js`).

## API

| Endpoint | Wat |
|---|---|
| `GET /api/opties` | merken met hun modellen, brandstoffen, transmissies, bouwjaren, de huidige maand |
| `GET /api/voorstel?merk=&model=` | meest voorkomende brandstof en transmissie van het model |
| `POST /api/voorspel` | prijs nu, elk half jaar en op het verkoopmoment (laag / midden / hoog). De nieuwprijs zoekt de API zelf op in de data |

Voorbeeld `POST /api/voorspel`:

```json
{"merk": "Volkswagen", "model": "Golf", "bouwjaar": 2020, "brandstof": "petrol", "transmissie": "manual",
 "km": 90000, "km_verkoop": 120000, "verkoop_maanden": 24, "inflatie": 0.02}
```
