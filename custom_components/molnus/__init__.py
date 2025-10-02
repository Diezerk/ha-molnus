# custom_components/molnus/__init__.py
from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any, Dict, Optional, Tuple

import voluptuous as vol

from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.util.dt import utcnow

from .const import DOMAIN, PLATFORMS, DEFAULT_SCAN_INTERVAL, LABELS
from .client import MolnusClient, ImagesResponseSimple
from .coordinator import MolnusCoordinator

_LOGGER = logging.getLogger(__name__)

# Try optional influx v2 client
try:
    from influxdb_client import InfluxDBClient, Point, WritePrecision
    from influxdb_client.client.write_api import SYNCHRONOUS

    _INFLUX_V2_AVAILABLE = True
except Exception:
    InfluxDBClient = None
    Point = None
    WritePrecision = None
    SYNCHRONOUS = None
    _INFLUX_V2_AVAILABLE = False

# http client for Influx v1 writes
import httpx  # kept here intentionally

# max history items stored in memory (sensor attributes)
MAX_HISTORY_ITEMS = 500


def _parse_iso_to_dt(iso: Optional[str]) -> Optional[datetime]:
    """Parse ISO timestamp tolerant (handles trailing Z -> +00:00)."""
    if not iso:
        return None
    try:
        if iso.endswith("Z"):
            iso2 = iso[:-1] + "+00:00"
        else:
            iso2 = iso
        return datetime.fromisoformat(iso2)
    except Exception:
        try:
            base = iso.split(".")[0].replace("Z", "")
            return datetime.fromisoformat(base)
        except Exception:
            return None


def _create_influx_client_if_configured(
    stored: Dict[str, Any], entry_data: Dict[str, Any]
) -> Tuple[Optional[str], Optional[Any], Optional[Any], Optional[str], Optional[str]]:
    """
    Detect and create/cache Influx client/config for either v2 or v1.

    Returns a tuple indicating the method:
      ("v2", client, write_api, bucket, org) when v2 configured and client created
      ("v1", None, None, db, url) when v1 configured (params stored in stored["_influx_v1"])
      (None, None, None, None, None) when no Influx configured
    """
    # prefer explicit version in entry_data
    version = str(entry_data.get("influx_version", "2")).strip()

    # Try v2 if configured and available
    if version != "1":
        url = entry_data.get("influx_url")
        token = entry_data.get("influx_token")
        org = entry_data.get("influx_org")
        bucket = entry_data.get("influx_bucket")
        if url and token and org and bucket and _INFLUX_V2_AVAILABLE:
            # cache client in stored
            if stored.get("_influx_v2_client"):
                return ("v2", stored.get("_influx_v2_client"), stored.get("_influx_v2_write_api"), bucket, org)
            try:
                client = InfluxDBClient(url=url, token=token, org=org)
                write_api = client.write_api(write_options=SYNCHRONOUS)
                stored["_influx_v2_client"] = client
                stored["_influx_v2_write_api"] = write_api
                stored["_influx_v2_bucket"] = bucket
                stored["_influx_v2_org"] = org
                _LOGGER.debug("Molnus: created InfluxDB v2 client for bucket %s", bucket)
                return ("v2", client, write_api, bucket, org)
            except Exception:
                _LOGGER.exception("Molnus: failed to create InfluxDB v2 client")
                # fall through to v1 detection

    # Try v1 (legacy)
    url = entry_data.get("influx_url")
    db = entry_data.get("influx_db")
    user = entry_data.get("influx_user")
    password = entry_data.get("influx_password")
    if url and db and user is not None:
        # cache v1 params in stored for reuse
        stored["_influx_v1"] = {"url": url.rstrip("/"), "db": db, "user": user, "password": password or ""}
        _LOGGER.debug("Molnus: configured InfluxDB v1 -> %s db=%s", url, db)
        return ("v1", None, None, db, url.rstrip("/"))

    return (None, None, None, None, None)


async def _write_influx_v1(
    stored: Dict[str, Any],
    measurement: str,
    tags: Dict[str, Any],
    fields: Dict[str, Any],
    ts_dt: Optional[datetime],
) -> bool:
    """
    Write a single point to InfluxDB v1 via HTTP line-protocol.
    Returns True if success (HTTP 204/200), False otherwise.
    """
    params = stored.get("_influx_v1")
    if not params:
        return False

    url = params["url"]
    db = params["db"]
    user = params["user"]
    password = params["password"]

    def _escape_tag(v: str) -> str:
        return str(v).replace(" ", r"\ ").replace(",", r"\,").replace("=", r"\=")

    tag_parts = []
    for k, v in (tags or {}).items():
        if v is None:
            continue
        tag_parts.append(f"{k}={_escape_tag(v)}")
    tags_str = ",".join(tag_parts)

    field_parts = []
    for k, v in (fields or {}).items():
        if v is None:
            continue
        if isinstance(v, str):
            fv = v.replace('"', r'\"')
            field_parts.append(f'{k}="{fv}"')
        elif isinstance(v, bool):
            field_parts.append(f"{k}={'true' if v else 'false'}")
        else:
            # numeric
            try:
                field_parts.append(f"{k}={float(v)}")
            except Exception:
                field_parts.append(f'{k}="{str(v)}"')
    fields_str = ",".join(field_parts)
    if not fields_str:
        return False

    measurement_escaped = measurement.replace(" ", r"\ ")
    line = measurement_escaped
    if tags_str:
        line += f",{tags_str}"
    line += f" {fields_str}"

    if ts_dt:
        ts_ns = int(ts_dt.timestamp() * 1_000_000_000)
        line += f" {ts_ns}"

    write_url = f"{url}/write"
    params_qs = {"db": db}

    # Try reuse httpx.Client from MolnusClient if available
    http_client = None
    try:
        molnus_client: MolnusClient = stored.get("client")
        if molnus_client and hasattr(molnus_client, "_client"):
            http_client = molnus_client._client  # httpx.AsyncClient
    except Exception:
        http_client = None

    created_local = False
    if http_client is None:
        http_client = httpx.AsyncClient(timeout=10.0)
        created_local = True

    try:
        resp = await http_client.post(write_url, params=params_qs, content=line, auth=(user, password) if user else None)
        if resp.status_code in (204, 200):
            return True
        _LOGGER.debug("Influx v1 write failed: %s %s -- line: %s", resp.status_code, resp.text, line)
        return False
    except Exception:
        _LOGGER.exception("Failed to write to InfluxDB v1")
        return False
    finally:
        if created_local:
            await http_client.aclose()


async def _write_influx_point(
    stored: Dict[str, Any],
    method_tuple: Tuple[Optional[str], Optional[Any], Optional[Any], Optional[str], Optional[str]],
    top_label: str,
    top_accuracy: Optional[float],
    camera_id_local: str,
    ts_dt: Optional[datetime],
) -> None:
    """
    High-level writer that routes to v2 or v1 accordingly.
    method_tuple is returned by _create_influx_client_if_configured.
    """
    if not method_tuple or method_tuple[0] is None:
        return

    kind = method_tuple[0]
    if kind == "v2":
        # v2 usage
        _, client, write_api, bucket, org = method_tuple
        if not write_api:
            return
        try:
            p = Point("molnus_image").tag("species", top_label).tag("camera_id", camera_id_local).field(
                "accuracy", float(top_accuracy) if top_accuracy is not None else 0.0
            )
            if ts_dt:
                p = p.time(ts_dt, WritePrecision.NS)
            # Write synchronously (blocking small amount)
            write_api.write(bucket=bucket, org=org, record=p)
        except Exception:
            _LOGGER.exception("Failed to write point to InfluxDB v2")
    elif kind == "v1":
        # write via http
        try:
            await _write_influx_v1(stored, "molnus_image", {"species": top_label, "camera_id": camera_id_local}, {"accuracy": float(top_accuracy) if top_accuracy is not None else 0.0}, ts_dt)
        except Exception:
            _LOGGER.exception("Failed to write point to InfluxDB v1")


async def async_setup(hass: HomeAssistant, config: Dict[str, Any]) -> bool:
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

    # Validate login
    await coordinator.async_config_entry_first_refresh()

    hass.data[DOMAIN].setdefault(entry.entry_id, {})
    stored = hass.data[DOMAIN][entry.entry_id]
    stored["client"] = client
    stored["coordinator"] = coordinator
    stored["last_images"] = None
    stored["last_images_count"] = 0
    stored["history"] = []
    stored["label_counts"] = {label: 0 for label in LABELS.keys()}
    stored["label_sensors"] = []
    stored["other_sensors"] = []
    stored["_entry_data"] = data

    # Prepare influx config (v1 caching happens inside _create_influx_client_if_configured)
    _create_influx_client_if_configured(stored, data)

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # Register service (single registration per integration instance)
    if not hass.data[DOMAIN].get("service_registered"):
        schema = vol.Schema(
            {
                vol.Optional("entry_id"): str,
                vol.Required("camera_id"): str,
                vol.Optional("offset", default=0): int,
                vol.Optional("limit", default=50): int,
                vol.Optional("wildlife_required", default=False): bool,
            }
        )

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
                    camera_id=camera_id_local, offset=offset, limit=limit, wildlife_required=wildlife_required
                )
            except Exception as e:
                _LOGGER.exception("Failed to fetch images: %s", e)
                return

            stored_local["last_images"] = images_resp
            stored_local["last_images_count"] = len(images_resp.images) if images_resp and images_resp.images else 0

            found_labels = set()

            # determine method (v2 or v1)
            method_tuple = _create_influx_client_if_configured(stored_local, stored_local.get("_entry_data", {}))

            for img in images_resp.images:
                top_label = None
                top_accuracy = None
                if img.predictions:
                    sorted_preds = sorted(
                        [p for p in img.predictions if p and p.label is not None],
                        key=lambda x: (x.accuracy if x.accuracy is not None else -1),
                        reverse=True,
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

                # write to influx (v2 or v1) non-blocking in async context
                if method_tuple and method_tuple[0]:
                    ts = _parse_iso_to_dt(entry_obj["captureDate"]) if entry_obj.get("captureDate") else None
                    try:
                        await _write_influx_point(stored_local, method_tuple, top_label, top_accuracy, camera_id_local, ts)
                    except Exception:
                        _LOGGER.exception("Error while writing to Influx for image %s", entry_obj.get("captureDate"))

            # trim history
            if len(stored_local["history"]) > MAX_HISTORY_ITEMS:
                stored_local["history"] = stored_local["history"][:MAX_HISTORY_ITEMS]

            for label in LABELS.keys():
                stored_local["label_counts"][label] = 1 if label in found_labels else 0

            # update sensors
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

    # Auto-fetch
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
                method_tuple = _create_influx_client_if_configured(stored_local, stored_local.get("_entry_data", {}))

                for img in images_resp.images:
                    top_label = None
                    top_accuracy = None
                    if img.predictions:
                        sorted_preds = sorted(
                            [p for p in img.predictions if p and p.label is not None],
                            key=lambda x: (x.accuracy if x.accuracy is not None else -1),
                            reverse=True,
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

                    if method_tuple and method_tuple[0]:
                        ts = _parse_iso_to_dt(entry_obj["captureDate"]) if entry_obj.get("captureDate") else None
                        try:
                            await _write_influx_point(stored_local, method_tuple, top_label, top_accuracy, camera_id, ts)
                        except Exception:
                            _LOGGER.exception("Error while writing to Influx for image %s", entry_obj.get("captureDate"))

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

        # run first fetch immediately (in background) and schedule recurring
        hass.async_create_task(_auto_fetch(utcnow()))
        hass.data[DOMAIN][entry.entry_id]["_auto_fetch_unsub"] = async_track_time_interval(hass, _auto_fetch, timedelta(seconds=interval_seconds))

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
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
            # close influx v2 client if exists
            influx_client = stored.get("_influx_v2_client")
            try:
                if influx_client:
                    influx_client.close()
            except Exception:
                _LOGGER.exception("Failed to close Influx v2 client")
            client = stored.get("client")
            if client:
                await client.close()
    return unload_ok
