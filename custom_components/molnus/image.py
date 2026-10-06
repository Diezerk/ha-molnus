from __future__ import annotations

import logging

import aiohttp
from homeassistant.components.image import ImageEntity
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.util import dt as dt_util

from . import MolnusConfigEntry
from .coordinator import MolnusCoordinator
from .entity import MolnusCameraEntity, add_camera_entities

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant, entry: MolnusConfigEntry, async_add_entities: AddConfigEntryEntitiesCallback
) -> None:
    coordinator = entry.runtime_data
    entry.async_on_unload(
        add_camera_entities(coordinator, async_add_entities, lambda c, cid: [MolnusLastImage(hass, c, cid)])
    )


class MolnusLastImage(MolnusCameraEntity, ImageEntity):
    """Senaste bilden från kameran."""

    _attr_translation_key = "last_image"
    # Molnus CDN svarar med application/octet-stream, som HA:s image-plattform avvisar
    _attr_content_type = "image/jpeg"

    def __init__(self, hass: HomeAssistant, coordinator: MolnusCoordinator, camera_id: str) -> None:
        MolnusCameraEntity.__init__(self, coordinator, camera_id)
        ImageEntity.__init__(self, hass)
        self._attr_unique_id = f"{camera_id}_last_image"
        self._image_id: str | None = None
        self._attr_image_url = None  # HA:s standard är UNDEFINED, som räknas som sant
        self._fetched_url: str | None = None
        self._fetched_bytes: bytes | None = None
        self._update_from_data()

    def _update_from_data(self) -> None:
        data = self.state_data
        latest = data.latest if data else None
        if not latest or latest.id == self._image_id:
            return
        self._image_id = latest.id
        self._attr_image_url = latest.url
        # Entitetens tillstånd är image_last_updated, så den måste ändras för varje ny bild.
        # Fotodatumet används när det finns och är nyare, annars aktuell tid.
        current = self._attr_image_last_updated
        captured = latest.capture_date
        if captured is None or (current is not None and captured <= current):
            captured = dt_util.utcnow()
        self._attr_image_last_updated = captured

    @callback
    def _handle_coordinator_update(self) -> None:
        self._update_from_data()
        super()._handle_coordinator_update()

    async def async_image(self) -> bytes | None:
        url = self._attr_image_url
        if not url:
            return None
        if url != self._fetched_url:
            try:
                async with async_get_clientsession(self.hass).get(url, timeout=aiohttp.ClientTimeout(total=20)) as resp:
                    resp.raise_for_status()
                    self._fetched_bytes = await resp.read()
                self._fetched_url = url
            except (aiohttp.ClientError, TimeoutError) as exc:
                _LOGGER.warning("Molnus: kunde inte hämta bild %s: %s", self._image_id, type(exc).__name__)
                return None
        return self._fetched_bytes
