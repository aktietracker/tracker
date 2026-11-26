# Agartracker

Live-graf: **https://reddayio.github.io/Ossdsign-tracker/**

Hämtar dagligen antal ägare hos **Avanza** och **Nordnet** för flera aktier
(just nu **OssDsign**, **Smart Eye**, **Integrum** – se `STOCKS` i
`track_owners.py`), sparar historik per aktie, uppdaterar en **Excel-fil**
(en flik per aktie), och postar (när Discord-webhooken är på plats) en
daglig samlad uppdatering i Discord med länk till grafen.

Dashboarden har flikar högst upp för att växla mellan aktierna.

Körs helt automatiskt via GitHub Actions varje kväll kl 20:00 svensk tid.
Ingen dator behöver vara på – allt sker i molnet.

---

## Snabböversikt: hur det hänger ihop

```
GitHub Actions (schemalagt varje kväll)
        │
        ▼
track_owners.py
  ├── hämtar Avanza-antal (pyavanza-biblioteket, publikt API)
  ├── hämtar Nordnet-antal (skrapar allaaktier.se)
  ├── sparar en rad i data/history.json
  ├── bygger om data/ossdsign_owners.xlsx (build_excel.py)
  └── postar till Discord (om DISCORD_WEBHOOK_URL finns som secret)
        │
        ▼
index.html (GitHub Pages) läser data/history.json och ritar upp grafen
```

## Filstruktur

```
track_owners.py                 huvudscriptet, körs av GitHub Actions
build_excel.py                  bygger om Excel-filen (en flik per aktie)
requirements.txt                Python-beroenden
index.html                      dashboarden med aktie-flikar (GitHub Pages)
data/history_<key>.json         historik per aktie, en rad per dag
data/agartracker.xlsx           Excel med en flik per aktie, med diagram
.github/workflows/track.yml     schemat: körs 18:00 UTC (~20:00 svensk tid)
```

## Lägga till/ta bort aktier

Redigera listan `STOCKS` i `track_owners.py`:

```python
STOCKS = [
    {"key": "ossdsign", "name": "OssDsign", "avanza_id": "962596", "allaaktier_slug": "ossdsign"},
    {"key": "smarteye", "name": "Smart Eye", "avanza_id": "710675", "allaaktier_slug": "smart-eye"},
    {"key": "integrum", "name": "Integrum", "avanza_id": "753680", "allaaktier_slug": "integrum"},
]
```

- `avanza_id`: numret i Avanzas URL, t.ex. `avanza.se/aktier/om-aktien.html/710675/smart-eye` → `710675`
- `allaaktier_slug`: sista delen av `allaaktier.se/<slug>`-adressen

Lägg samtidigt till motsvarande aktie i `STOCKS`-listan i `index.html`
(sök efter `const STOCKS =`), så dyker fliken upp i dashboarden automatiskt.

## Varför just dessa datakällor (och inte andra)

- **Avanza**: har ett öppet, publikt API som visar `numberOfOwners` för en
  aktie utan inloggning. Vi använder biblioteket `pyavanza` för detta.
  Avanza har historiskt bytt API-struktur (fältet flyttades/döptes om under
  arbetets gång), så koden söker rekursivt efter fältet istället för att lita
  på en exakt sökväg – mer motståndskraftigt mot framtida ändringar.

- **Nordnet**: Nordnets egen webbplats visar **inte** antal ägare per aktie
  utan inloggning (testat och bekräftat). Vi hämtar istället siffran från
  **allaaktier.se**, som visar både Avanza- och Nordnet-antal öppet i vanlig
  text (bara den historiska *grafen* på den sajten kräver premium-inlogg,
  inte nutidssiffrorna). Talen på den sidan ligger i separata HTML-taggar
  med `&nbsp;`/`&#xA0;`-tecken som tusentalsavgränsare, så parsern rensar
  bort HTML-taggar och avkodar dessa specialtecken innan den läser talet.

- **Montrose** (en nyare svensk mäklare) undersöktes också, men exponerar
  inget publikt ägarantal per aktie någonstans vi kunde hitta – varken på
  egen sajt, i appen, eller hos tredjepartssajter. Inte inbyggt av den
  anledningen.

## Historisk backfill (finns inte, och varför)

Ingen av källorna erbjuder historisk data bakåt i tiden på ett sätt vi kan
hämta automatiskt:
- **avanzakollen.se** har historik för Avanza-antal och trackar faktiskt
  OssDsign, men deras `robots.txt` blockerar uttryckligen automatiserad
  åtkomst, vilket vi respekterar.
- **allaaktier.se** har full historik i sin graf, men bakom en betald
  premiumtjänst (99 kr/mån, 14 dagar gratis).

Historiken i det här projektet börjar alltså **från och med den dag
trackern sattes igång** (4 augusti 2026) och växer sig längre för varje dag
som går. Vill du manuellt lägga in enstaka gamla datapunkter du hittat
någon annanstans går det fint – lägg bara till en rad i `data/history.json`
med samma format: `{"date": "YYYY-MM-DD", "avanza": N, "nordnet": N}`.

## Driftsättning / vanliga ändringar

**Byta körtid:** ändra `cron`-raden i `.github/workflows/track.yml`.
Notera att Avanza/Nordnet uppdaterar sina siffror ca 18-19 svensk tid, så
körningen bör ligga efter det.

**Lägga till fler aktier:** hör av dig så bygger vi om scriptet för en
lista av aktier istället för bara OssDsign.

**Byta GitHub-användarnamn:** går, men GitHub sätter **inte** upp
omdirigering för Pages-sidor (bara för repots kod/git-åtkomst). Efter ett
namnbyte måste `CHART_URL`-variabeln (Settings → Secrets and variables →
Actions → Variables) och alla delade länkar uppdateras manuellt till det
nya `nyttnamn.github.io/Ossdsign-tracker/`.

**Repot måste vara publikt** för att GitHub Pages ska fungera gratis
(privata repon kräver GitHub Pro för Pages). Datan som visas är redan
offentlig information (samma siffror som syns öppet på Avanza/allaaktier.se),
så inget känsligt exponeras.

## Felsökning

**Nordnet-delen kraschar:**
```bash
python track_owners.py --debug-nordnet
```
Skriver ut den råa HTML-kontexten runt etiketterna, användbart om
allaaktier.se ändrar sin sidstruktur igen.

**Avanza-delen kraschar:**
Felmeddelandet visar automatiskt vilka fält som faktiskt kom tillbaka från
API:et, vilket gör det enkelt att uppdatera sökningen om Avanza ändrar
struktur igen.

**Requirements.txt ger "invalid start byte"-fel:**
Detta hände en gång pga en osynlig soft-hyphen (troligen från mobil
webbläsares autokorrigering vid redigering direkt i GitHub). Lösning: ladda
ner en ny, ren fil och ladda upp den via "Upload files" istället för att
skriva/klistra direkt i webbläsarens textruta.

## Dashboard-funktioner

Grafen (`index.html`) visar:
- Periodval: Vecka / 1 mån / 3 mån / 6 mån / 1 år / 3 år / Allt
- Metric-kort: Avanza, Nordnet, Totalt (alla med diff + % sen igår), Sen start
- Rekordbricka: högsta antal någonsin per mäklare + datum
- Streak: antal dagar i rad med ökning i totalt antal
- Ratio: Avanza-ägare per Nordnet-ägare

## Kurs

Dagliga stängningskurser hämtas från Avanzas diagramdata (samma instrument-ID
som ägarantalet) och sparas i `data/price_<key>.json`, från insamlingens start
(4 augusti 2026) och framåt. Varje körning hämtar ett års dagsdata och slår
ihop det med filen, så missade dagar fylls i automatiskt vid nästa körning.

I dashboarden visas kursen via kryssrutan "Kurs" (egen skala till höger, ägarna
på en gemensam skala till vänster). Kursen hämtas separat från ägarantalet, så
ett fel på ena stoppar inte det andra.

Avanzas diagram-endpoint är inofficiell och kan ändras, precis som övrig
Avanza-data. Yahoo Finance gav samma slutkurser vid test och kan vara reserv.
