# custom_components/molnus/__init__.py
from __future__ import annotations
import logging
from datetime import timedelta, datetime
import voluptuous as vol

from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.util.dt import utcnow

from .const import DOMAIN, PLATFORMS, DEFAULT_SCAN_INTERVAL, LABELS
from .client import MolnusClient, ImagesResponseSimple
from .coordinator import MolnusCoordinator

_LOGGER = logging.getLogger(__name__)

# Optional influx imports — try/except to keep graceful failures if package missing
try:
    from influxdb_client import InfluxDBClient, Point, WritePrecision
    from influxdb_client.client.write_api import SYNCHRONOUS
    _INFLUX_AVAILABLE = True
except Exception:
    InfluxDBClient = None
    Point = None
    WritePrecision = None
    SYNCHRONOUS = None
    _INFLUX_AVAILABLE = False

# hur många historikposter vi sparar i sensor-attributen
MAX_HISTORY_ITEMS = 500

def _parse_iso_to_dt(iso: str) -> datetime | None:
    """Parse ISO string tolerant: handles trailing Z."""
    if not iso:
        return None
    try:
        if iso.endswith("Z"):
            iso2 = iso[:-1] + "+00:00"
        else:
            iso2 = iso
        return datetime.fromisoformat(iso2)
    except Exception:
        # sista fallback: try removing fractional seconds oddities
        try:
            # remove timezone and parse naive (not ideal)
            base = iso.split(".")[0].replace("Z", "")
            return datetime.fromisoformat(base)
        except Exception:
            return None

def _create_influx_client_if_configured(stored: dict, entry_data: dict):
    """
    Skapar och cache:ar en InfluxDBClient i stored om influx-konfig finns.
    Förväntar: entry_data innehåller 'influx_url','influx_token','influx_org','influx_bucket'
    Returnerar (client, write_api, bucket, org) eller (None, None, None, None)
    """
    if not _INFLUX_AVAILABLE:
        return None, None, None, None

    # cache i stored för entry
    if stored.get("_influx_client"):
        return stored.get("_influx_client"), stored.get("_influx_write_api"), stored.get("_influx_bucket"), stored.get("_influx_org")

    url = entry_data.get("influx_url")
    token = entry_data.get("influx_token")
    org = entry_data.get("influx_org")
    bucket = entry_data.get("influx_bucket")

    if not url or not token or not org or not bucket:
        return None, None, None, None

    try:
        client = InfluxDBClient(url=url, token=token, org=org)
        write_api = client.write_api(write_options=SYNCHRONOUS)
        stored["_influx_client"] = client
        stored["_influx_write_api"] = write_api
        stored["_influx_bucket"] = bucket
        stored["_influx_org"] = org
        _LOGGER.debug("Molnus: InfluxDB client created for bucket %s", bucket)
        return client, write_api, bucket, org
    except Exception:
        _LOGGER.exception("Molnus: Failed to create InfluxDB client")
        return None, None, None, None

async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    hass.data.setdefault(DOMAIN, {})
    return True

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    data = entry.data
    email = data["email"]
    password = data["password"]
    camera_id = data.get("camera_id", "") or ""
    interval_hours = int(data.get("auto_fetch_interval_hours", 1))
    interval_seconds = max(60, interval_hours * 3600)

    client = MolnusClient(email=email, password=password)
    coordinator = MolnusCoordinator(hass, client, DEFAULT_SCAN_INTERVAL)

    # Validera inloggning
    await coordinator.async_config_entry_first_refresh()

    hass.data[DOMAIN].setdefault(entry.entry_id, {})
    stored = hass.data[DOMAIN][entry.entry_id]
    stored["client"] = client
    stored["coordinator"] = coordinator
    stored["last_images"] = None
    stored["last_images_count"] = 0
    stored["history"] = []  # lista av {captureDate, url, label, accuracy}
    stored["label_counts"] = {label: 0 for label in LABELS.keys()}
    stored["label_sensors"] = []
    stored["other_sensors"] = []

    # cache entry data for influx access
    stored["_entry_data"] = data

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # Registrera service (en gång per integration)
    if not hass.data[DOMAIN].get("service_registered"):
        schema = vol.Schema({
            vol.Optional("entry_id"): str,
            vol.Required("camera_id"): str,
            vol.Optional("offset", default=0): int,
            vol.Optional("limit", default=50): int,
            vol.Optional("wildlife_required", default=False): bool,
        })

        async def handle_fetch_images(call: ServiceCall) -> None:
            _entry_id = call.data.get("entry_id")
            if _entry_id and _entry_id in hass.data[DOMAIN]:
                target_entry_id = _entry_id
            else:
                entries = [k for k in hass.data[DOMAIN].keys() if k != "service_registered"]
                if not entries:
                    _LOGGER.error("No Molnus entries found when calling service")
                    return
                target_entry_id = entries[0]

            stored_local = hass.data[DOMAIN].get(target_entry_id)
            if not stored_local:
                _LOGGER.error("Entry %s not found", target_entry_id)
                return
            client_local: MolnusClient = stored_local.get("client")
            if not client_local:
                _LOGGER.error("No client for entry %s", target_entry_id)
                return

            camera_id_local = call.data["camera_id"]
            offset = call.data.get("offset", 0)
            limit = call.data.get("limit", 50)
            wildlife_required = call.data.get("wildlife_required", False)

            try:
                images_resp: ImagesResponseSimple = await client_local.get_images(
                    camera_id=camera_id_local,
                    offset=offset,
                    limit=limit,
                    wildlife_required=wildlife_required
                )
            except Exception as e:
                _LOGGER.exception("Failed to fetch images: %s", e)
                return

            # Spara och bygg historik (senaste först)
            stored_local["last_images"] = images_resp
            stored_local["last_images_count"] = len(images_resp.images) if images_resp and images_resp.images else 0

            found_labels = set()

            # prepare influx client if configured
            influx_client, influx_write_api, influx_bucket, influx_org = _create_influx_client_if_configured(stored_local, stored_local.get("_entry_data", {}))

            for img in images_resp.images:
                top_label = None
                top_accuracy = None
                if img.predictions:
                    sorted_preds = sorted(
                        [p for p in img.predictions if p and p.label is not None],
                        key=lambda x: (x.accuracy if x.accuracy is not None else -1),
                        reverse=True
                    )
                    if sorted_preds:
                        top_label = sorted_preds[0].label
                        top_accuracy = sorted_preds[0].accuracy

                entry_obj = {
                    "captureDate": img.captureDate.isoformat() if img.captureDate else None,
                    "url": img.url,
                    "label": top_label,
                    "accuracy": top_accuracy,
                }
                # undvik dubbletter
                if entry_obj["captureDate"] not in [h.get("captureDate") for h in stored_local["history"]]:
                    stored_local["history"].insert(0, entry_obj)

                if top_label:
                    found_labels.add(top_label)

                # Write to Influx if configured (one point per image/top_label)
                if influx_write_api and influx_bucket and influx_org and top_label:
                    try:
                        ts = _parse_iso_to_dt(entry_obj["captureDate"]) if entry_obj["captureDate"] else None
                        p = Point("molnus_image").tag("species", top_label).tag("camera_id", camera_id_local).field("accuracy", float(top_accuracy) if top_accuracy is not None else 0.0)
                        if ts:
                            p = p.time(ts, WritePrecision.NS)
                        influx_write_api.write(bucket=influx_bucket, org=influx_org, record=p)
                    except Exception:
                        _LOGGER.exception("Failed to write point to InfluxDB for image %s", entry_obj.get("captureDate"))

            # Trimma history
            if len(stored_local["history"]) > MAX_HISTORY_ITEMS:
                stored_local["history"] = stored_local["history"][:MAX_HISTORY_ITEMS]

            # Uppdatera label_counts
            for label in LABELS.keys():
                stored_local["label_counts"][label] = 1 if label in found_labels else 0

            # Uppdatera sensorer
            for sensor in stored_local.get("label_sensors", []):
                try:
                    sensor.async_write_ha_state()
                except Exception:
                    _LOGGER.exception("Failed to update label sensor state")
            for sensor in stored_local.get("other_sensors", []):
                try:
                    sensor.async_write_ha_state()
                except Exception:
                    _LOGGER.exception("Failed to update other sensor state")

            _LOGGER.info("Molnus: fetched %s images for camera %s", stored_local.get("last_images_count"), camera_id_local)

        hass.services.async_register(DOMAIN, "fetch_images", handle_fetch_images, schema=schema)
        hass.data[DOMAIN]["service_registered"] = True

    # Auto-fetch scheduling
    if camera_id:
        async def _auto_fetch(now):
            try:
                stored_local = hass.data[DOMAIN].get(entry.entry_id)
                if not stored_local:
                    _LOGGER.error("Auto-fetch: entry not found %s", entry.entry_id)
                    return
                client_local: MolnusClient = stored_local.get("client")
                if not client_local:
                    _LOGGER.error("Auto-fetch: no client for entry %s", entry.entry_id)
                    return

                _LOGGER.debug("Auto-fetch: fetching images for camera %s", camera_id)
                images_resp = await client_local.get_images(camera_id=camera_id, offset=0, limit=50, wildlife_required=False)
                stored_local["last_images"] = images_resp
                stored_local["last_images_count"] = len(images_resp.images) if images_resp and images_resp.images else 0

                found_labels = set()

                # influx client
                influx_client, influx_write_api, influx_bucket, influx_org = _create_influx_client_if_configured(stored_local, stored_local.get("_entry_data", {}))

                for img in images_resp.images:
                    top_label = None
                    top_accuracy = None
                    if img.predictions:
                        sorted_preds = sorted(
                            [p for p in img.predictions if p and p.label is not None],
                            key=lambda x: (x.accuracy if x.accuracy is not None else -1),
                            reverse=True
                        )
                        if sorted_preds:
                            top_label = sorted_preds[0].label
                            top_accuracy = sorted_preds[0].accuracy

                    entry_obj = {
                        "captureDate": img.captureDate.isoformat() if img.captureDate else None,
                        "url": img.url,
                        "label": top_label,
                        "accuracy": top_accuracy,
                    }
                    if entry_obj["captureDate"] not in [h.get("captureDate") for h in stored_local["history"]]:
                        stored_local["history"].insert(0, entry_obj)

                    if top_label:
                        found_labels.add(top_label)

                    # Write to influx
                    if influx_write_api and influx_bucket and influx_org and top_label:
                        try:
                            ts = _parse_iso_to_dt(entry_obj["captureDate"]) if entry_obj["captureDate"] else None
                            p = Point("molnus_image").tag("species", top_label).tag("camera_id", camera_id).field("accuracy", float(top_accuracy) if top_accuracy is not None else 0.0)
                            if ts:
                                p = p.time(ts, WritePrecision.NS)
                            influx_write_api.write(bucket=influx_bucket, org=influx_org, record=p)
                        except Exception:
                            _LOGGER.exception("Failed to write point to InfluxDB for image %s", entry_obj.get("captureDate"))

                if len(stored_local["history"]) > MAX_HISTORY_ITEMS:
                    stored_local["history"] = stored_local["history"][:MAX_HISTORY_ITEMS]

                for label in LABELS.keys():
                    stored_local["label_counts"][label] = 1 if label in found_labels else 0

                for sensor in stored_local.get("label_sensors", []):
                    try:
                        sensor.async_write_ha_state()
                    except Exception:
                        _LOGGER.exception("Failed to update label sensor state")
                for sensor in stored_local.get("other_sensors", []):
                    try:
                        sensor.async_write_ha_state()
                    except Exception:
                        _LOGGER.exception("Failed to update other sensor state")

                _LOGGER.info("Molnus: auto-fetched %s images for camera %s", stored_local.get("last_images_count"), camera_id)
            except Exception:
                _LOGGER.exception("Auto-fetch failed")

        # kör första gång direkt i bakgrunden
        hass.async_create_task(_auto_fetch(utcnow()))
        hass.data[DOMAIN][entry.entry_id]["_auto_fetch_unsub"] = async_track_time_interval(
            hass, _auto_fetch, timedelta(seconds=interval_seconds)
        )

    return True

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    # Avregistrera schemaläggning om den finns
    stored = hass.data[DOMAIN].get(entry.entry_id, {})
    unsub = stored.get("_auto_fetch_unsub")
    if unsub:
        try:
            unsub()
        except Exception:
            _LOGGER.exception("Failed to unsubscribe auto fetch")

    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        stored = hass.data[DOMAIN].pop(entry.entry_id, None)
        if stored:
            # stäng Influx client om den skapats
            influx_client = stored.get("_influx_client")
            try:
                if influx_client:
                    influx_client.close()
            except Exception:
                _LOGGER.exception("Failed to close Influx client")
            client = stored.get("client")
            if client:
                await client.close()
    return unload_ok
