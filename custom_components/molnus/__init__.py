from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.device_registry import DeviceEntry

from .api import MolnusApi
from .const import CONF_SCAN_INTERVAL_MINUTES, DEFAULT_SCAN_INTERVAL_MINUTES, DOMAIN, PLATFORMS
from .coordinator import MolnusCoordinator

MolnusConfigEntry = ConfigEntry[MolnusCoordinator]


async def async_setup_entry(hass: HomeAssistant, entry: MolnusConfigEntry) -> bool:
    api = MolnusApi(async_get_clientsession(hass), entry.data["email"], entry.data["password"])
    interval = entry.options.get(CONF_SCAN_INTERVAL_MINUTES, DEFAULT_SCAN_INTERVAL_MINUTES)
    coordinator = MolnusCoordinator(hass, entry, api, interval)
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    coordinator.start_listening()
    return True


async def async_unload_entry(hass: HomeAssistant, entry: MolnusConfigEntry) -> bool:
    entry.runtime_data.stop_listening()
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def async_remove_config_entry_device(
    hass: HomeAssistant, entry: MolnusConfigEntry, device_entry: DeviceEntry
) -> bool:
    """Tillåt att ta bort en kamera i UI:t om den inte längre finns på kontot."""
    return not any(
        domain == DOMAIN and camera_id in entry.runtime_data.data
        for domain, camera_id in device_entry.identifiers
    )


async def async_migrate_entry(hass: HomeAssistant, entry: MolnusConfigEntry) -> bool:
    """v1 (camera_id + Influx) -> v2: behåll bara inloggningen."""
    if entry.version < 2:
        hass.config_entries.async_update_entry(
            entry, data={"email": entry.data["email"], "password": entry.data["password"]}, version=2
        )
    return True
