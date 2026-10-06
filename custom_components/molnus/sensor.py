from __future__ import annotations

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity, SensorStateClass
from homeassistant.const import UnitOfElectricPotential, UnitOfTemperature
from homeassistant.helpers.entity import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import MolnusConfigEntry
from .const import LABELS
from .coordinator import MolnusCoordinator
from .entity import MolnusCameraEntity, add_camera_entities


def _make_entities(coordinator: MolnusCoordinator, camera_id: str) -> list[MolnusCameraEntity]:
    return [
        MolnusLastAnimalSensor(coordinator, camera_id),
        *(MolnusStatusSensor(coordinator, camera_id, *spec) for spec in STATUS_SENSORS),
    ]


async def async_setup_entry(hass: HomeAssistant, entry: MolnusConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    entry.async_on_unload(add_camera_entities(entry.runtime_data, async_add_entities, _make_entities))


# (status-nyckel, translation_key, device_class, enhet)
STATUS_SENSORS = (
    ("Battery", "battery_voltage", SensorDeviceClass.VOLTAGE, UnitOfElectricPotential.VOLT),
    ("Signal", "signal_strength", None, None),
    ("TempC", "camera_temperature", SensorDeviceClass.TEMPERATURE, UnitOfTemperature.CELSIUS),
)


def readable_label(label: str | None) -> str | None:
    if not label:
        return None
    return LABELS.get(label.upper(), label.replace("_", " ").capitalize())


class MolnusLastAnimalSensor(MolnusCameraEntity, SensorEntity):
    """Vad som syns på senaste bilden (översta prediktionen)."""

    _attr_translation_key = "last_animal"

    def __init__(self, coordinator: MolnusCoordinator, camera_id: str) -> None:
        super().__init__(coordinator, camera_id)
        self._attr_unique_id = f"{camera_id}_last_animal"

    @property
    def native_value(self) -> str | None:
        data = self.state_data
        top = data.latest.top_prediction if data and data.latest else None
        return readable_label(top.label) if top else None

    @property
    def extra_state_attributes(self) -> dict:
        data = self.state_data
        latest = data.latest if data else None
        if not latest:
            return {}
        top = latest.top_prediction
        return {
            "label": top.label if top else None,
            "accuracy": top.accuracy if top else None,
            "capture_date": latest.capture_date.isoformat() if latest.capture_date else None,
            "image_id": latest.id,
            "image_url": latest.url,
            "thumbnail_url": latest.thumbnail_url,
            "shared_camera": data.camera.shared,
        }


class MolnusStatusSensor(MolnusCameraEntity, SensorEntity):
    """Batteri, signal och temperatur från kamerans senaste status."""

    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, coordinator: MolnusCoordinator, camera_id: str, key: str, translation_key: str, device_class, unit) -> None:
        super().__init__(coordinator, camera_id)
        self._key = key
        self._attr_translation_key = translation_key
        self._attr_device_class = device_class
        self._attr_native_unit_of_measurement = unit
        self._attr_unique_id = f"{camera_id}_{translation_key}"

    @property
    def native_value(self) -> float | None:
        data = self.state_data
        try:
            return float(data.camera.status[self._key]) if data else None
        except (KeyError, TypeError, ValueError):
            return None
