from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import timedelta
from typing import Optional

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import Camera, ImageItem, MolnusApi, MolnusAuthError, MolnusError
from .const import DOMAIN, IMAGES_PER_CAMERA

_LOGGER = logging.getLogger(__name__)


@dataclass
class CameraState:
    camera: Camera
    latest: Optional[ImageItem] = None
    image_count: int = 0


class MolnusCoordinator(DataUpdateCoordinator[dict[str, CameraState]]):
    """Håller alla kameror och senaste bild per kamera."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, api: MolnusApi, interval_minutes: int) -> None:
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=DOMAIN,
            update_interval=timedelta(minutes=interval_minutes),
        )
        self.api = api
        self._ws_task: Optional[asyncio.Task] = None

    async def _fetch_camera(self, camera: Camera) -> CameraState:
        previous = (self.data or {}).get(camera.id)
        try:
            images = await self.api.get_images(camera.id, IMAGES_PER_CAMERA)
        except MolnusAuthError:
            raise
        except MolnusError as exc:
            _LOGGER.warning("Molnus: kunde inte hämta bilder för %s: %s", camera.name, exc)
            return CameraState(camera, previous.latest if previous else None, previous.image_count if previous else 0)
        return CameraState(camera, images[0] if images else None, len(images))

    async def _async_update_data(self) -> dict[str, CameraState]:
        try:
            cameras = await self.api.get_cameras()
            states = await asyncio.gather(*(self._fetch_camera(c) for c in cameras))
        except MolnusAuthError as exc:
            raise ConfigEntryAuthFailed from exc
        except MolnusError as exc:
            raise UpdateFailed(str(exc)) from exc
        return {s.camera.id: s for s in states}

    async def _on_image_upload(self, camera_id: Optional[str]) -> None:
        """Anropas från WebSocket när en ny bild laddats upp."""
        if not self.data or (camera_id and camera_id not in self.data):
            await self.async_request_refresh()  # okänd kamera -> hämta om allt
            return
        targets = [self.data[camera_id].camera] if camera_id else [s.camera for s in self.data.values()]
        try:
            states = await asyncio.gather(*(self._fetch_camera(c) for c in targets))
        except MolnusAuthError:
            self.config_entry.async_start_reauth(self.hass)
            return
        self.async_set_updated_data({**self.data, **{s.camera.id: s for s in states}})

    def start_listening(self) -> None:
        if self._ws_task is None:
            self._ws_task = self.config_entry.async_create_background_task(
                self.hass,
                self.api.listen(self._on_image_upload, self._on_reconnected, self._on_auth_failed),
                name="molnus_websocket",
            )

    async def _on_reconnected(self) -> None:
        await self.async_request_refresh()

    def _on_auth_failed(self) -> None:
        self.config_entry.async_start_reauth(self.hass)

    def stop_listening(self) -> None:
        if self._ws_task:
            self._ws_task.cancel()
            self._ws_task = None
