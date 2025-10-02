# HA Molnus — README

Detta repo innehåller en **Home Assistant custom integration** för Molnus (kamera/tjänst). Den loggar in mot `https://molnus.com/auth/token`, hämtar bilder via `/images/get`, parsar ut `captureDate`, `url` och top-prediction (`label` + `accuracy`) och kan **skriva datapunkter till InfluxDB** (valfritt). Integrationens sensorer exponerar även en lokal historik (i attribut) så du kan se vad som hittats.

Nedan hittar du: installation (HACS eller manuellt), konfiguration (inkl. Influx), hur du testar och ett exempel på Flux-query för Grafana.

---

# Innehåll i repot
```
ha-molnus/
├─ README.md                <- du läser denna fil
├─ hacs.json
└─ custom_components/molnus/
   ├─ __init__.py
   ├─ manifest.json
   ├─ const.py
   ├─ client.py
   ├─ coordinator.py
   ├─ config_flow.py
   ├─ sensor.py
   ├─ strings.json
   └─ translations/sv.json
```

---

# Förutsättningar
- Home Assistant (Core/OS) med möjlighet att lägga till `custom_components`.
- (Valfritt men rekommenderat) InfluxDB 2.x och Grafana om du vill göra riktiga tidsserie-analyser (t.ex. vilka tider på dygnet vildsvin förekommer).
- Internetåtkomst för att anropa `molnus.com`.
- PyPI-bibliotek som behövs deklareras i `manifest.json`: `httpx>=0.27.0` och `influxdb-client>=1.30.0`. Om du installerar via HACS/Release så hämtas dessa automatiskt.

---

# Installationsalternativ

## A — Installera via HACS (rekommenderat för enkel uppdatering)
1. Push repo till GitHub (public eller privat).  
   - I `manifest.json` finns `codeowners` — byt `@DITT-USER` till ditt GitHub-namn om du vill.
2. I Home Assistant: gå till **HACS → tre prickar → Custom repositories**.  
   - Lägg in din repo-URL och välj kategori **Integration**.  
3. I HACS → Integrations, hitta *Molnus* → Klicka **Install**.  
4. Starta om Home Assistant (om HACS kräver det).  
5. Gå till **Inställningar → Enheter & tjänster → Lägg till integration → Molnus** och fyll i inloggningsuppgifter + (valfritt) `camera_id`, `auto_fetch_interval_hours` och Influx-inställningar (se nästa avsnitt).

## B — Manuell installation
1. Kopiera mappen `custom_components/molnus` till din Home Assistant-katalog:  
   `/config/custom_components/molnus/`  
2. Starta om Home Assistant.  
3. Lägg till integration via **Inställningar → Enheter & tjänster → Lägg till integration → Molnus**.

---

# Konfiguration (Config Flow)
När du lägger till integrationen via UI får du ett formulär med följande fält:

- **Email** (required) — din Molnus-inloggning.  
- **Password** (required) — lösenord.  
- **Camera ID** (optional) — om du vill att integrationen ska auto-hämta bilder för en specifik kamera.  
- **Auto fetch interval (hours)** (optional, default 1) — hur ofta auto-hämtning sker.  
- **Influx URL** (optional) — ex. `http://10.0.1.5:8086`  
- **Influx Token** (optional) — token med write-behörighet.  
- **Influx Org** (optional)  
- **Influx Bucket** (optional) — ex. `molnus`

> Influx-fälten är frivilliga. Om de är ifyllda kommer integrationen skriva datapunkter till InfluxDB (en punkt per bild/top-prediction) med timestamp = `captureDate`.

---

# Vad integrationen exponerar i Home Assistant

1. **Label-sensorer**  
   - En sensor per känd art/label (konfigurerad i `const.py` under `LABELS`). Sensorerna är numeriska (0/1) och sätts till `1` om minst en bild i senaste hämtningen innehöll den arten, annars `0`.  
   - Entity id exempel: `sensor.molnus_<entry_id>_label_CAPREOLUS` (displaynamn beroende på entry).

2. **Latest URL sensor** (optionellt i tidigare versioner)  
   - Exponerar senaste bildens `url`. (I nuvarande implementation kan det finnas `other_sensors` för denna.)

3. **Historik i attribut**  
   - Varje label-sensor (och latest-sensor) exponerar attributet `history`: lista med objekt `{captureDate, url, label, accuracy}` (senaste först). Historiken sparas i integrationens minne och trimmar till max antal poster (konfig i kod, default 500).

4. **Service**  
   - `molnus.fetch_images` — manuell hämtning. Service-data:
     ```yaml
     entry_id: "<valfritt entry_id>"   # om flertalet entries, annars utelämna för första
     camera_id: "e80ef272-..."         # required om du inte angav camera_id i config
     offset: 0
     limit: 50
     wildlife_required: false
     ```

---

# InfluxDB (snabbstart även i Home Assistant OS / Supervisor)

### Installera InfluxDB
- Om du kör Home Assistant OS: öppna **Supervisor → Add-on Store** och installera InfluxDB-community add-on (eller kör InfluxDB i Docker/server).  
- Starta add-on och skapa i Influx UI:
  - **Organization**
  - **Bucket** (t.ex. `molnus`)
  - **Token** med write-behörighet till bucketen

### Ange Influx-konfig i integrationen
- Fyll `influx_url`, `influx_token`, `influx_org`, `influx_bucket` i config-flow vid setup av Molnus-integration.

### Vad skrivs till Influx?
- Measurement: `molnus_image`  
- Tags: `species` (t.ex. `SUS_SCROFA`), `camera_id`  
- Field: `accuracy` (float)  
- Timestamp: `captureDate` (API:t levererar) — så du får korrekt tidsplacering i Influx.

---

# Grafana / Flux-query — räkna timmar på dygnet
När punkter samlats i Influx (bucket `molnus`) kan du i Grafana använda Flux för att räkna antal detektioner per timme för en art. Exempel (sista 30 dagarna, art `SUS_SCROFA`):

```flux
from(bucket: "molnus")
  |> range(start: -30d)
  |> filter(fn: (r) => r._measurement == "molnus_image" and r["species"] == "SUS_SCROFA")
  |> aggregateWindow(every: 1h, fn: count, createEmpty: false)
  |> map(fn: (r) => ({ r with hour: date.hour(t: r._time) }))
  |> group(columns: ["hour"])
  |> sum(column: "_value")
  |> sort(columns: ["hour"])
```

- Grafana-panel: välj Bar chart eller Time series; ställ in X-axis som `hour` och Y som `_value`.  
- Du kan enkelt byta art genom att ändra filter på `species`.

---

# Test & felsökning

## Snabbtest (manuellt)
1. Kör service `molnus.fetch_images` (Developer Tools → Services) med `camera_id`.  
2. Kontrollera Home Assistant-loggar: `Settings → System → Logs` eller via SSH `docker logs homeassistant`.  
3. I Influx UI: Data Explorer → kontrollera att measurement `molnus_image` får nya punkter.

## Aktivera debug-loggning (för integrationen)
I `configuration.yaml`:
```yaml
logger:
  default: warning
  logs:
    custom_components.molnus: debug
```
Starta om HA och titta i loggarna.

## Vanliga problem
- **401/Authentication failed**: kontrollera e-post/lösenord; kontrollera att Molnus inte kräver 2FA.  
- **429 / rate-limited**: sänk frekvens (öka `auto_fetch_interval_hours`) och implementera backoff. Jag kan hjälpa lägga in backoff i klienten om du önskar.  
- **Influx-skrivning misslyckas**: kontrollera token/org/bucket/url, CORS/brandväggar, och att `influxdb-client` är installerat (HACS/manifest brukar installera beroenden).

---

# Säkerhet & etik
- Använd endast dina egna inloggningsuppgifter eller sådana du har tillåtelse till.  
- Läs Molnus Terms of Service — reverse-engineering eller automatiserade anrop kan vara förbjudet enligt deras villkor.  
- Store tokens/credentials: Home Assistant lagrar `entry.data` krypterat i `.storage` (UI-config flow) — säkert nog för normalt bruk. Undvik att lägga känsliga värden i klartextfiler.

---

# Anpassningar & framtida förbättringar
- Backoff/retry vid 429 eller nätfel.  
- Option för att logga alla predictions (inte bara topp) till Influx.  
- Möjlighet att filtrera på min. accuracy vid sparning till Influx.  
- Export av historik till CSV via service.  
- Eventuell HACS-publikation/PR för att bli officiell i HACS.

---

# Licens
Inget licensfält i denna README — inkludera gärna en `LICENSE` i ditt repo (MIT, Apache2 eller annan) om du vill publicera.

---

# Behöver du hjälp att klistra in / packa filerna?
Säg till så kan jag generera färdiga filblock att klistra in, eller skapa en zip-fil du kan ladda ner (om du vill). Jag kan också hjälpa med Flux-queries anpassade för fler species eller skapa en färdig Grafana-panel JSON.

Lycka till — säg till om jag ska generera `README.md` som färdigt filinnehåll (klar att klistra in) eller om du vill att jag skapar zip med alla filer.
