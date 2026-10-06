from __future__ import annotations

from homeassistant.components.event import EventEntity
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import MolnusConfigEntry
from .const import EVENT_NEW_IMAGE
from .coordinator import MolnusCoordinator
from .entity import MolnusCameraEntity, add_camera_entities
from .sensor import readable_label


async def async_setup_entry(hass: HomeAssistant, entry: MolnusConfigEntry, async_add_entities: AddConfigEntryEntitiesCallback) -> None:
    entry.async_on_unload(
        add_camera_entities(entry.runtime_data, async_add_entities, lambda c, cid: [MolnusNewImageEvent(c, cid)])
    )


class MolnusNewImageEvent(MolnusCameraEntity, EventEntity):
    """Avfyras en gång för varje ny bild på kameran (för automationer)."""

    _attr_translation_key = "new_image"
    _attr_event_types = [EVENT_NEW_IMAGE]

    def __init__(self, coordinator: MolnusCoordinator, camera_id: str) -> None:
        super().__init__(coordinator, camera_id)
        self._attr_unique_id = f"{camera_id}_new_image"
        data = self.state_data
        # Första uppdateringen räknas inte som "ny" bild
        self._last_image_id = data.latest.id if data and data.latest else None

    def _is_new(self, image_id: str) -> bool:
        if self._last_image_id is None:
            # Ingen bild känd sedan start (t.ex. misslyckad första hämtning): ta den som
            # utgångsläge i stället för att larma för en gammal bild
            self._last_image_id = image_id
            return False
        try:
            # Molnus bild-id ökar; ett lägre id betyder att senaste bilden raderats
            return int(image_id) > int(self._last_image_id)
        except ValueError:
            return image_id != self._last_image_id

    @callback
    def _handle_coordinator_update(self) -> None:
        data = self.state_data
        latest = data.latest if data else None
        if latest and latest.id and self._is_new(latest.id):
            self._last_image_id = latest.id
            top = latest.top_prediction
            self._trigger_event(
                EVENT_NEW_IMAGE,
                {
                    "label": top.label if top else None,
                    "label_name": readable_label(top.label) if top else None,
                    "accuracy": top.accuracy if top else None,
                    "image_id": latest.id,
                    "image_url": latest.url,
                    "capture_date": latest.capture_date.isoformat() if latest.capture_date else None,
                },
            )
        super()._handle_coordinator_update()
