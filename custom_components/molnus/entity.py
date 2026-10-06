from __future__ import annotations

from typing import Callable

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import CameraState, MolnusCoordinator


class MolnusCameraEntity(CoordinatorEntity[MolnusCoordinator]):
    """Bas för alla entiteter: kopplar till kamerans enhet."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: MolnusCoordinator, camera_id: str) -> None:
        super().__init__(coordinator)
        self._camera_id = camera_id
        camera = coordinator.data[camera_id].camera
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, camera_id)},
            name=camera.name,
            manufacturer="Molnus",
            model=camera.model,
            serial_number=camera.imei,
        )

    @property
    def state_data(self) -> CameraState | None:
        return self.coordinator.data.get(self._camera_id)

    @property
    def available(self) -> bool:
        return super().available and self.state_data is not None


def add_camera_entities(
    coordinator: MolnusCoordinator,
    async_add_entities: AddConfigEntryEntitiesCallback,
    factory: Callable[[MolnusCoordinator, str], list[MolnusCameraEntity]],
) -> Callable[[], None]:
    """Lägg till entiteter för alla kameror nu och för nya kameror som dyker upp senare."""
    known: set[str] = set()

    def _add_new() -> None:
        new_ids = set(coordinator.data) - known
        if not new_ids:
            return
        known.update(new_ids)
        async_add_entities([e for cid in new_ids for e in factory(coordinator, cid)])

    _add_new()
    return coordinator.async_add_listener(_add_new)
