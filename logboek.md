# Logboek project Auto prijs voorspeller

Om de data die ik wil krijgen ga ik een webscraper bouwen. Deze webscraper scraped de advertenties van auto’s op autoscout.
De informatie die we screpen zijn:
Merk, model, km-stand, bouwjaar, fueltype, prijs in euro, transmissie vorm, bodytype en als er een occasion prijs bij staat gemeld pakken we die ook. Er zijn ook nog 2 andere data waardes die we scrapen en dat zijn de kentekens en het id van de advertentie. Het kenteken halen we op zzodat als we geen occasionprijs kunnen vinden op autoscout dan vragen we de occasion prijs op via de RDW API. De id van de advertentie halen we op zodat als de scraper is gestopt en we hem weer aanwillen zitten dat het dan niet de data scraped van advertenties die we al hebben gescraped, zo voorkomen we dubbele data tijdens het scrapen.

Het heeft 5 dagen geduurd voordat we allen hebben kunnen scrapen. IK heb de data nu. Heb een datum van de scrapinugdag erbij gezet zodat we dat kunnen aftrekken van de bouwjaar om zo te kijken hoe oud de auto is. We hebben de outliers verwijderd zoals advertenties waar staat dat een mercedes wordt verkocht voor 1.000.000 of een peaguet 2-7 voor 100.000. We hadden in eerste instantie dat we de csv files hadden gemaakt maar omdat we veel data hebben wordt een csv fle heel zwaar en github accedpteerd een bestand dat maximaal 50mb is. DUs hebben we het laten saven naar een pargeut file

---

## Van één momentopname naar data over de tijd (eind oktober)

Ik wil voorspellen wat een auto over bijvoorbeeld 1 tot 5 jaar waard is. Daar kwam ik achter een probleem: mijn data was één momentopname (oktober 2026). Daaruit kun je wel leren wat een oudere auto kost, maar niet hoe de hele markt over de tijd verandert. Ook mag je bij data over de tijd niet willekeurig splitsen in train en test, want dan "kijkt" het model in de toekomst.

Daarom heb ik een tweede bron toegevoegd: oude versies van AutoScout24 via de **Wayback Machine** (internetarchief), van maart 2023 tot en met 2025. Samen met mijn eigen scrape heb ik nu advertenties van 2023 tot 2026.

Wat ik met de data heb gedaan (`dataset_tijd.ipynb` → `dataset_tijd.parquet`, 266.884 advertenties):
- **Samengevoegd** met per advertentie de datum waarop hij online stond (`snapshot_date`).
- **Nieuwprijs voor de oude advertenties:** die staat niet in het archief. Ik schat hem met de mediaan van de echte nieuwprijzen (AutoScout/RDW) van hetzelfde model en bouwjaar, en anders van hetzelfde model.
- **Opgeschoond:** zonder model, bouwjaar, km of prijs eruit; bouwjaar vanaf 2005; km onder de 600.000; vraagprijs hooguit 1,5× de nieuwprijs; nieuwprijzen die meer dan 3× afwijken van wat normaal is voor dat model (tikfouten) eruit. Carrosserievorm is leeg (NaN) bij de oude data, omdat het archief die niet heeft.
- **Duplicaten heb ik bewust laten staan.** Dezelfde auto die op meerdere momenten te koop staat, laat juist zien hoe zijn prijs verandert.
- **Inflatie:** alle bedragen omgerekend naar euro's van 2026 met de consumentenprijsindex van het CBS. Zo vergelijk je een prijs uit 2023 eerlijk met een prijs uit 2026.
- **Leeftijd als kommagetal:** moment min (bouwjaar + 0,5). Met hele jaren werd elke auto op 1 januari ineens een jaar ouder, en dat gaf een zaagtand in de data.
- Overbodige kolommen en oude bestanden opgeruimd.

Ik heb ook gecontroleerd of de twee bronnen wel te vergelijken zijn. Bij vergelijkbare auto's lag het prijsverschil tussen eind 2025 (archief) en 2026 (mijn scrape) rond +2%. Het CBS meet in die periode +1,2%. Dat ligt dicht bij elkaar, dus ik heb de bron niet als kenmerk aan het model meegegeven. Bij het voorspellen weet je die toch niet.

## Modellen (`model_training.ipynb`)

**Retrospectieve vergelijking:** training tot juni 2024, validatie in de tweede helft van 2024 en testdata uit 2025. De tweede vergelijking traint op 2023 en hergebruikt de instellingen uit de validatie van 2024. Beide vergelijkingen gebruiken imputatie en filters gebaseerd op gegevens uit 2026. De onafhankelijke historische backtest staat in `model-building/historical_validation.py`.

**Deel 1, de prijs van een auto.** Drie modellen vergeleken:
- **Baseline:** mediaanprijs per model en leeftijd. Elk echt model moet dit verslaan.
- **Ridge-regressie:** lineair model met splines voor leeftijd en km.
- **CatBoost** (gradient boosting met beslisbomen): de winnaar. Zes instellingen getest; de beste is diepte 10, learning rate 0,05, l2 10.

De oorspronkelijke retrospectieve mediane fouten waren **10,2%** (train t/m 2024) en **13,3%** (train op 2023). Deze scores meten de volledige verkoopprognose van de app niet.

**Deel 2, de markt over de tijd.** Beslisbomen kunnen niet voorspellen hoe de hele markt verder beweegt. Daarvoor heb ik vier tijdreeksmodellen vergeleken op de CBS-prijsindex voor tweedehands auto's (2005–2025): random walk, random walk met drift, ARIMA(1,1,0) en **ETS met gedempte trend**. ETS won, met 2,8% fout. Het levert een marktfactor (laag, midden, hoog) per jaar vooruit.

**De voorspelling:** prijs bij verkoop = CatBoost-prijs × marktfactor.

**Modelgrootte:** het eerste eindmodel had 13.140 bomen en was 247 MB, te groot voor GitHub. Met maximaal 4.000 bomen is het 77 MB, met dezelfde scores.

**Nauwkeurigheid** (getest op 41.564 auto's uit 2025):

| Fout | 1 jaar vooruit | 2 jaar vooruit |
|---|---|---|
| binnen 10% | 49% | 40% |
| binnen 20% | 78% | 67% |
| binnen 30% | 90% | 82% |

- Het model is het best bij auto's van €20.000 tot €80.000. Bij auto's onder €10.000 is het minder goed: daar bepalen staat en onderhoud meer van de prijs, en dat staat niet in de data.
- Het model voorspelt vaker te hoog dan te laag: 58% bij 1 jaar en 70% bij 2 jaar vooruit. Dat komt doordat de prijzen na inflatiecorrectie in 2024–2025 iets daalden en het model het laatste marktniveau doortrekt.

## Web-app

Gebouwd met **FastAPI** (Python, laadt het model) en **React** (formulier, grafiek en tabel).

- Je vult in: merk, model, bouwjaar, brandstof, transmissie, km-stand nu, wanneer je wilt verkopen en de km-stand bij verkoop (standaard 15.000 km per jaar). De nieuwprijs hoef je niet in te vullen; die zoekt de app zelf op in de data.
- Je ziet de verwachte vraagprijs op het verkoopmoment met een marge, het waardeverlies, een grafiek en een tabel per half jaar.
- Vormgeving: licht met groen, later rustiger gemaakt zodat het er minder "gegenereerd" uitziet.

## Feedback uit de demo en wat ik ermee heb gedaan

**Feedback:** het zou handig zijn om ook verschillende auto's met elkaar te kunnen vergelijken.

**Wat ik ermee heb gedaan:** in het formulier zit nu een knop **"+ Vergelijk"**. Die voegt een tweede auto toe als tabblad (Auto 1 / Auto 2). De tweede auto begint als kopie van de eerste, zodat je alleen hoeft aan te passen wat anders is.
- Het verkoopmoment en de inflatie gelden voor beide auto's, zodat je eerlijk vergelijkt. De km-stand stel je per auto in.
- Je ziet beide verwachte prijzen naast elkaar, met nu, waardeverlies en km bij verkoop.
- Een conclusie in één zin, bijvoorbeeld "Golf 2020 is bij verkoop € 800 meer waard".
- Eén grafiek met twee lijnen (groen en oranje), elk met een eigen marge.
- Een tabel met de prijs van beide auto's en het verschil per half jaar.
- Op mobiel staan de twee auto's onder elkaar.

## Eigen verbetering: prijs van nu was te hoog

Bij het testen zag ik dat de prijs van nu vaak wat te hoog was. Een Golf uit 2020 kwam op € 22.960 uit, terwijl vergelijkbare advertenties rond € 21.900 zaten. Twee aanpassingen:
- Een instelling in de app (`geschat=1`) deed alsof de nieuwprijs een schatting was, zoals bij de oude archiefdata, en dat duwde de prijs omhoog. Die staat nu goed.
- De app vergelijkt de prijs met de echte advertenties van vergelijkbare auto's (zelfde model, bouwjaar, brandstof en transmissie) en schuift hem bij als het model daar structureel naast zit, met hooguit 20%. In de app staat bijvoorbeeld: "nu te koop: 98 vergelijkbare advertenties, mediaan € 20.960 bij 104.000 km".

## Online zetten

- **Render** (gratis), vanuit mijn GitHub-repo. Elke push naar `main` zet automatisch de nieuwe versie online. Alles zit in één Docker-container: de API, het model en de frontend.
- Het gratis plan heeft 512 MB geheugen, en de app gebruikte 625 MB. De tabellen die de app nodig heeft worden nu vooraf berekend (`maak_app_data.py`), zodat de server de hele dataset niet hoeft te laden. Nu gebruikt hij 380 MB.
- De code staat op GitHub en in mijn map op de GitLab van de groep (`Personal-projects/Ezeddin/Auto-Voorspeller`).

## Problemen onderweg

- **iCloud haalde bestanden weg.** Mijn project staat in iCloud en mijn schijf was bijna vol. Daardoor zette macOS bestanden (zoals de pakketten van de frontend en zelfs het model) alleen nog in de cloud, en de app liep vast. Oplossing: de frontend één keer bouwen en via de API serveren, zodat er nog maar één server nodig is.

## Verantwoord gebruik

Mensen kunnen op basis van deze app beslissen wanneer ze hun auto verkopen of wat ze ervoor vragen. Daarom heb ik nagedacht over wat de app wel en niet kan, en hoe ik dat duidelijk maak.

**Eerlijk over wat het is**
- Onder elke uitkomst staat: *"Dit is een schatting, geen taxatie. Voor goedkopere auto's onder de € 10.000 is deze voorspelling minder betrouwbaar."* Als een van de prijzen onder de € 10.000 komt, wordt die melding oranje.
- Het model kent alleen merk, model, bouwjaar, km-stand, brandstof en transmissie. Schade, onderhoud, opties en de staat van de auto ziet het niet. Een taxateur ziet die wel.
- Het model voorspelt **vraagprijzen** uit advertenties, geen echte verkoopprijzen. Wat je uiteindelijk krijgt, ligt vaak lager.

**Laten zien hoe zeker de uitkomst is**
- De app toont geen los getal, maar een verwachte prijs met een marge (laag tot hoog).
- De app laat zien op hoeveel echte advertenties van vergelijkbare auto's de prijs van nu gebaseerd is, en hoeveel het model is bijgesteld.
- Bij een model met weinig data verschijnt een waarschuwing.
- Onderaan staan de bronnen (AutoScout24 en CBS) en de toelichting dat de scenario’s toekomstige vraagprijzen schatten.

**Bekende zwakke plekken** (zie ook de tabel bij Modellen)
- Bij auto's onder € 10.000 zit maar 38% van de voorspellingen binnen 10%; bij auto's van € 20.000 tot € 40.000 is dat 55%.
- Het model voorspelt vaker te hoog dan te laag: 58% bij 1 jaar en 70% bij 2 jaar vooruit. Wie op de app vertrouwt, kan dus te optimistisch zijn over zijn verkoopprijs.
- De marge in de app is smaller dan de echte onzekerheid. Dat staat bij "Wat nog beter kan".
- Populaire modellen hebben veel data en dus betere voorspellingen dan zeldzame modellen.

**Verantwoord data verzamelen**
- De scraper leest `robots.txt` en slaat pagina's over die niet toegestaan zijn.
- Tussen verzoeken wacht hij 3 tot 6 seconden, zodat AutoScout24 niet zwaar belast wordt. Bij een blokkade (HTTP 403 of een CAPTCHA) stopt hij in plaats van het te omzeilen.
- **Privacy:** het kenteken wordt alleen gebruikt om de nieuwprijs op te zoeken bij de open data van de RDW, en wordt **niet opgeslagen**. In de dataset staan geen kentekens, namen of andere gegevens van verkopers.
- De data is alleen voor dit schoolproject gebruikt.

**Geen gegevens van gebruikers**
- De app slaat niets op van wat je invult. Er is geen account, er wordt niets bijgehouden en de berekening gebeurt alleen op het moment dat je op "Bereken" klikt.

## Wat nog beter kan

- De marge in de app is te smal: ongeveer ±3,5%, terwijl 90% van de voorspellingen pas binnen 30% valt. Een betere manier is quantile regression: een eerlijke onder- en bovengrens per auto.
- De neiging om te hoog te voorspellen, vooral bij 2 jaar vooruit, corrigeren met een markttrend.
- Vraagprijzen zijn geen verkoopprijzen. Echte transactieprijzen zouden beter zijn, maar die zijn niet openbaar.
