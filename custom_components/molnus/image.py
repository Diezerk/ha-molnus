from __future__ import annotations

import logging
from datetime import datetime

import aiohttp
from homeassistant.components.image import ImageEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import MolnusConfigEntry
from .coordinator import MolnusCoordinator
from .entity import MolnusCameraEntity, add_camera_entities

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass: HomeAssistant, entry: MolnusConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
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
        self._fetched_url: str | None = None
        self._fetched_bytes: bytes | None = None

    async def async_image(self) -> bytes | None:
        url = self.image_url
        if not url:
            return None
        if url != self._fetched_url:
            try:
                async with async_get_clientsession(self.hass).get(url, timeout=aiohttp.ClientTimeout(total=20)) as resp:
                    resp.raise_for_status()
                    self._fetched_bytes = await resp.read()
                self._fetched_url = url
            except (aiohttp.ClientError, TimeoutError) as exc:
                _LOGGER.warning("Molnus: kunde inte hämta bild %s: %s", url, exc)
                return None
        return self._fetched_bytes

    @property
    def image_url(self) -> str | None:
        data = self.state_data
        return data.latest.url if data and data.latest else None

    @property
    def image_last_updated(self) -> datetime | None:
        data = self.state_data
        return data.latest.capture_date if data and data.latest else None
