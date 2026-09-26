# AutoScout24 NL scraper

Verzamelt occasion-listings van AutoScout24 Nederland voor 10 merken, **per bouwjaar** 2005 t/m 2026,
en slaat ze op in `data/cars.csv`.

## Installatie

```bash
cd webscrape
pip install -r requirements.txt
```

## Gebruik

```bash
python scraper.py                           # alle merken, 2005 t/m 2026
python scraper.py --brand BMW --year 2015   # één merk + één bouwjaar (test)
python scraper.py --brand Audi              # één merk, alle bouwjaren
python scraper.py --rescan                  # ook al afgeronde combinaties opnieuw doorlopen
```

Voorbeeld van de output:

```
[START] BMW - 2015
BMW 2015 - 643 resultaten op 34 pagina's
BMW 2015 - page 1 - 17 cars found
BMW 2015 - page 2 - 20 cars found
...
[DONE] BMW - 2015 - 643 cars saved (643 gevonden, 0 al aanwezig)
```

Een volledige run doet enkele duizenden requests met 3–6 seconden pauze ertussen en duurt daardoor
ongeveer **4–5 dagen**, omdat voor veel auto's de advertentiepagina geopend wordt om het kenteken te vinden. Je kunt hem altijd onderbreken (Ctrl+C) en later opnieuw starten.

## Hoe het werkt

- Zoek-URL: `https://www.autoscout24.nl/lst/<merk>?fregfrom=<jaar>&fregto=<jaar>&pricefrom=2000&cy=NL&atype=C&page=<n>`
- AutoScout24 zet alle zoekresultaten als JSON in `<script id="__NEXT_DATA__">`, dus
  `requests` + `BeautifulSoup` is voldoende (geen Playwright nodig).
- Per merk → per bouwjaar → per carrosserievorm → alle pagina's tot `numberOfPages` (of tot een lege pagina).
  De carrosserievorm staat niet in de gegevens per auto, daarom zoeken we per vorm apart (filter `body`).
  Samen dekken de vormen alle advertenties (gecontroleerd: BMW 2015, 643 = 643).
- Filters: bouwjaar min = max = geselecteerd jaar, prijs vanaf €2.000, alleen personenauto's in NL,
  `pricetype=public` (koopprijs). Listings met een maand-/leaseprijs of een prijs onder €2.000 worden overgeslagen.
- Instellingen (merken, jaren, delay, filters) staan in `config.py`.

## Opslag, hervatten en duplicaten

| Bestand | Inhoud |
|---|---|
| `data/cars.csv` | De dataset: `brand,model,mileage_km,year,fuel_type,price_eur,transmission,body_type,new_price_eur,new_price_source` |
| `data/seen_ids.txt` | AutoScout24 listing-ID's die al in `cars.csv` staan |
| `data/progress.txt` | Merk/jaar-combinaties die volledig afgerond zijn |

- Na iedere merk/jaar-combinatie worden de resultaten direct naar schijf geschreven.
- Een listing waarvan het ID al in `seen_ids.txt` staat, wordt nooit opnieuw toegevoegd.
- Bij een herstart worden afgeronde combinaties overgeslagen. Met `--rescan` worden ze opnieuw
  doorzocht; alleen nieuwe listings worden dan toegevoegd.
- Opnieuw beginnen: verwijder `seen_ids.txt`, `progress.txt` en `cars.csv`.

## Normalisatie

- `fuel_type`: `petrol`, `diesel`, `electric`, `hybrid`, `lpg`, `other`.
  AutoScout24's "Elektro/Benzine" and "Elektro/Diesel" are both stored as `hybrid`.
- `transmission`: `manual`, `automatic` (inclusief semi-automaat), `other`.
- `body_type`: `hatchback`, `convertible`, `coupe`, `suv` (incl. off-road/pick-up), `station_wagon`, `sedan`, `mpv`, `van`, `other`.
- `new_price_eur`: de oorspronkelijke nieuwprijs (catalogusprijs). Zo wordt hij gevonden:
  1. AutoScout24 geeft hem mee in de zoekresultaten (~45% van de auto's). Dit is dezelfde waarde als de RDW-catalogusprijs.
  2. Anders opent de scraper de advertentiepagina, leest het kenteken en zoekt de catalogusprijs op bij
     [RDW open data](https://opendata.rdw.nl/resource/m9d7-ebf2.json). Het kenteken wordt **niet** opgeslagen.
     Niet elke verkoper vult een kenteken in.
  3. Na een volledige run schat `estimate_new_prices.py` de rest: mediaan van dezelfde merk + model + bouwjaar
     in de dataset, anders de RDW-mediaan voor merk + model + bouwjaar, anders merk + model over alle jaren.
- `new_price_source`: `autoscout`, `rdw_kenteken` (allebei exact) of `schatting`.

Na een onderbroken run kun je de schatting los draaien met `python estimate_new_prices.py`.
Eerdere schattingen worden dan opnieuw berekend. Wil je geen advertentiepagina's openen (veel sneller),
zet dan `FETCH_MISSING_NEW_PRICE = False` in `config.py`.

## Grenzen en fair use

- De scraper leest `robots.txt` en stopt als een URL niet is toegestaan.
- Bij HTTP 429/5xx wacht hij en probeert het opnieuw. Bij HTTP 403 of een CAPTCHA **stopt** hij.
  Er zit geen CAPTCHA-bypass, proxy-rotatie of andere manier in om blokkades te omzeilen.
- De gebruiksvoorwaarden van AutoScout24 beperken geautomatiseerd verzamelen van data. Gebruik de
  data alleen voor persoonlijk of studiegebruik en houd de delay in `config.py` ruim.
