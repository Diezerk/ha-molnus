# custom_components/molnus/coordinator.py
from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

_LOGGER = logging.getLogger(__name__)


class MolnusCoordinator(DataUpdateCoordinator):
    """
    Simple DataUpdateCoordinator for Molnus integration.

    It will call client's login() on the first refresh (used for validating credentials).
    You can extend _async_update_data to fetch more state if needed.
    """

    def __init__(self, hass: HomeAssistant, client: Any, update_interval: int) -> None:
        """
        :param hass: Home Assistant instance
        :param client: instance of MolnusClient
        :param update_interval: seconds between automatic updates
        """
        self._client = client
        super().__init__(
            hass,
            _LOGGER,
            name="molnus_coordinator",
            update_interval=timedelta(seconds=update_interval),
        )

    async def _async_update_data(self) -> Any:
        """
        Perform a single update. We use this to validate credentials / connectivity.
        You may expand this to return useful status data for other parts of the integration.
        """
        try:
            # Simple connectivity check: ensure we can log in / refresh token
            await self._client.login()
            # Return a small status dict (could be expanded)
            return {"ok": True}
        except Exception as err:
            _LOGGER.exception("MolnusCoordinator update failed: %s", err)
            raise UpdateFailed(err)
