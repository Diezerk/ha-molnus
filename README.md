# HA Molnus — README (English)

This repository contains a **Home Assistant custom integration** for Molnus (camera/service). It logs in to `https://molnus.com/auth/token`, fetches images via `/images/get`, parses `captureDate`, `url` and the top prediction (`label` + `accuracy`), and can **write datapoints to InfluxDB** (optional). The integration's sensors also expose a local history (in attributes) so you can inspect what has been detected.

Below you will find: installation instructions (HACS or manual), configuration (including Influx), how to test, and an example Flux query for Grafana.

---

## Repository structure
```
ha-molnus/
├─ README.md                <- this file (English)
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

## Requirements / prerequisites
- Home Assistant (Core/OS) with the ability to add `custom_components`.
- (Optional, recommended) InfluxDB 2.x and Grafana for proper time-series analysis (e.g., to see what times of day boar occur most often).  
- Internet access to contact `molnus.com`.
- Python packages declared in `manifest.json`: `httpx>=0.27.0` and `influxdb-client>=1.30.0`. If you install via HACS/releases these dependencies will be installed automatically.

---

## Installation options

### A — Install via HACS (recommended for easy updates)
1. Push the repository to GitHub (public or private).  
   - In `manifest.json` the `codeowners` field contains `@DITT-USER` — replace this with your GitHub username if you publish.  
2. In Home Assistant: go to **HACS → three dots → Custom repositories**.  
   - Add your repo URL and select category **Integration**.  
3. In HACS → Integrations, find *Molnus* → click **Install**.  
4. Restart Home Assistant if prompted.  
5. Go to **Settings → Devices & Services → Add Integration → Molnus** and fill in login credentials and optional settings (camera_id, fetch interval, Influx settings).

### B — Manual installation
1. Copy the folder `custom_components/molnus` into your Home Assistant configuration directory:  
   `/config/custom_components/molnus/`  
2. Restart Home Assistant.  
3. Add the integration via **Settings → Devices & Services → Add Integration → Molnus**.

---

## Configuration (Config Flow)
When you add the integration through the UI you will see a form with these fields:

- **Email** (required) — your Molnus login email.  
- **Password** (required) — your Molnus password.  
- **Camera ID** (optional) — if you want the integration to auto-fetch images for a specific camera.  
- **Auto fetch interval (hours)** (optional, default 1) — how often automatic fetching runs.  
- **Influx URL** (optional) — e.g. `http://10.0.1.5:8086`  
- **Influx Token** (optional) — token with write permissions.  
- **Influx Org** (optional)  
- **Influx Bucket** (optional) — e.g. `molnus`

> The Influx fields are optional. If provided, the integration will write datapoints to InfluxDB (one point per image/top-prediction) using the `captureDate` as the timestamp.

---

## What the integration exposes in Home Assistant

1. **Label sensors**  
   - One sensor per known species/label (configured in `const.py` under `LABELS`). Sensors are numeric (0/1) and are set to `1` if at least one image in the most recent fetch contained that species; otherwise `0`.  
   - Example entity id: `sensor.molnus_<entry_id>_label_CAPREOLUS` (display name varies by entry).

2. **Latest URL sensor** (optional in some versions)  
   - Exposes the `url` of the most recent image. (The integration keeps `other_sensors` if present.)

3. **History in attributes**  
   - Each label sensor (and latest-url sensor) exposes an attribute `history`: a list of objects `{captureDate, url, label, accuracy}` (newest first). History is kept in-memory and trimmed to a maximum number of entries (default 500, configurable in code).

4. **Service**  
   - `molnus.fetch_images` — manual fetch. Service data:
     ```yaml
     entry_id: "<optional entry_id>"   # omit to target the first/only entry
     camera_id: "e80ef272-..."         # required if you didn't set camera_id in config
     offset: 0
     limit: 50
     wildlife_required: false
     ```

---

## InfluxDB quick start (Home Assistant OS / Supervisor)
### Install InfluxDB
- If you run Home Assistant OS: open **Supervisor → Add-on Store** and install the InfluxDB community add-on (or run InfluxDB in Docker/server).  
- Start the add-on and create in the Influx UI:
  - an **Organization**
  - a **Bucket** (e.g. `molnus`)
  - a **Token** with write permissions for that bucket

### Provide Influx config to the integration
- Fill `influx_url`, `influx_token`, `influx_org`, `influx_bucket` in the integration setup form in Home Assistant.

### What gets written to InfluxDB?
- Measurement: `molnus_image`  
- Tags: `species` (for example `SUS_SCROFA`), `camera_id`  
- Field: `accuracy` (float)  
- Timestamp: `captureDate` (from the API) — this ensures correct time-series placement in Influx.

---

## Grafana / Flux query — count detections by hour of day
Once points are written to Influx (bucket `molnus`) you can use Flux in Grafana to count detections per hour for a species. Example (last 30 days, species `SUS_SCROFA`):

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

- In Grafana: choose Bar chart or Time series and set the X-axis to `hour` and Y to `_value`.  
- Change the `species` filter to analyze other species.

---

## Testing & troubleshooting

### Quick manual test
1. Call the service `molnus.fetch_images` (Developer Tools → Services) with `camera_id`.  
2. Check Home Assistant logs: **Settings → System → Logs** or via SSH (`docker logs homeassistant`).  
3. In Influx UI → Data Explorer: verify that measurement `molnus_image` has new points.

### Enable debug logging for the integration
Add to your `configuration.yaml`:
```yaml
logger:
  default: warning
  logs:
    custom_components.molnus: debug
```
Restart HA and check the logs for debug messages.

### Common issues
- **401 / Authentication failed**: verify email/password and ensure Molnus does not require 2FA.  
- **429 / Rate-limited**: reduce frequency (increase `auto_fetch_interval_hours`) and implement backoff. I can help add retry/backoff logic to the client if needed.  
- **Influx write errors**: verify token/org/bucket/url, firewall/CORS, and that `influxdb-client` is installed (HACS/manifest should install dependencies).

---

## Security & legal
- Only use credentials that you own or have permission to use.  
- Check Molnus Terms of Service — automated scraping or reverse-engineering might be prohibited.  
- Home Assistant stores `entry.data` encrypted in `.storage` for UI-configured entries; avoid putting secrets in plain text files.

---

## Possible improvements & future work
- Add exponential backoff / retry on 429 or network failures.  
- Option to write all predictions (not only the top prediction) to Influx.  
- Option to filter by minimum accuracy before writing to Influx.  
- Export history to CSV via a service.  
- Prepare a HACS PR to publish the integration officially.

---

## License
There is no license file included. Add a `LICENSE` (MIT, Apache 2.0, or your choice) if you publish the project.

---

## Need help packaging or generating files?
I can generate ready-to-paste file blocks, or create a zip file you can download with all files prepared. I can also help build Grafana panels or Flux queries for multiple species.

---

Good luck — tell me if you want me to save this English README into a file in the workspace or to produce a zip with the full integration files.
