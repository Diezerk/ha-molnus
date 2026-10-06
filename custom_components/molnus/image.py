from __future__ import annotations

from datetime import datetime

from homeassistant.components.image import ImageEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import MolnusConfigEntry
from .coordinator import MolnusCoordinator
from .entity import MolnusCameraEntity, add_camera_entities


async def async_setup_entry(hass: HomeAssistant, entry: MolnusConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    coordinator = entry.runtime_data
    entry.async_on_unload(
        add_camera_entities(coordinator, async_add_entities, lambda c, cid: [MolnusLastImage(hass, c, cid)])
    )


class MolnusLastImage(MolnusCameraEntity, ImageEntity):
    """Senaste bilden från kameran."""

    _attr_translation_key = "last_image"

    def __init__(self, hass: HomeAssistant, coordinator: MolnusCoordinator, camera_id: str) -> None:
        MolnusCameraEntity.__init__(self, coordinator, camera_id)
        ImageEntity.__init__(self, hass)
        self._attr_unique_id = f"{camera_id}_last_image"

    @property
    def image_url(self) -> str | None:
        data = self.state_data
        return data.latest.url if data and data.latest else None

    @property
    def image_last_updated(self) -> datetime | None:
        data = self.state_data
        return data.latest.capture_date if data and data.latest else None
