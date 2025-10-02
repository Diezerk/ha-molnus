from __future__ import annotations
from datetime import timedelta
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.core import HomeAssistant
from .client import MolnusClient

class MolnusCoordinator(DataUpdateCoordinator):
    def __init__(self, hass: HomeAssistant, client: MolnusClient, interval: int):
        super().__init__(
            hass,
            hass.helpers.logger.logger,
            name="molnus",
            update_interval=timedelta(seconds=interval),
        )
        self.client = client

    async def _async_update_data(self):
        try:
            return await self.client.get_status()
        except Exception as err:
            raise UpdateFailed(err) from err
