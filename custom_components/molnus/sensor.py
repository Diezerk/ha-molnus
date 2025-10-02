from __future__ import annotations
from homeassistant.components.sensor import SensorEntity
from homeassistant.core import callback
from .const import DOMAIN, LABELS

async def async_setup_entry(hass, entry, async_add_entities):
    stored = hass.data[DOMAIN][entry.entry_id]

    sensors = []
    for label, readable in LABELS.items():
        sensors.append(MolnusLabelCountSensor(entry.entry_id, label, readable))

    # registrera dem i hass.data så de kan uppdateras från service/auto-fetch
    stored["label_sensors"] = sensors
    async_add_entities(sensors)

class MolnusLabelCountSensor(SensorEntity):
    _attr_has_entity_name = True

    def __init__(self, entry_id: str, label: str, readable_name: str):
        self._entry_id = entry_id
        self._label = label
        self._readable = readable_name
        self._attr_unique_id = f"molnus_{entry_id}_label_{label}"
        # namnge sensorn med label så det blir unikt i UI; du kan ändra displaynamn i integrationsinställningar
        self._attr_name = f"Molnus {label}"

    @property
    def native_value(self):
        hass = self.hass
        stored = hass.data[DOMAIN].get(self._entry_id, {})
        counts = stored.get("label_counts", {})
        # returnera 1 eller 0
        val = counts.get(self._label, 0)
        try:
            return int(val)
        except Exception:
            return 0

    @property
    def extra_state_attributes(self):
        # Exponera användarnamn/översättning och historiken (hela listan)
        hass = self.hass
        stored = hass.data[DOMAIN].get(self._entry_id, {})
        return {
            "label": self._label,
            "label_name": self._readable,
            "history": stored.get("history", []),
            "last_images_count": stored.get("last_images_count", 0),
        }

    @callback
    def _handle_coordinator_update(self) -> None:
        self.async_write_ha_state()
