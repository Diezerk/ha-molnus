from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry, ConfigFlow, ConfigFlowResult, OptionsFlow, OptionsFlowWithReload
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import MolnusApi, MolnusAuthError, MolnusConnectionError
from .const import CONF_SCAN_INTERVAL_MINUTES, DEFAULT_SCAN_INTERVAL_MINUTES, DOMAIN

_LOGGER = logging.getLogger(__name__)

STEP_USER_DATA = vol.Schema({vol.Required("email"): str, vol.Required("password"): str})


class MolnusConfigFlow(ConfigFlow, domain=DOMAIN):
    """Config flow: bara e-post och lösenord, kamerorna hittas automatiskt."""

    VERSION = 2

    async def _validate(self, email: str, password: str) -> str | None:
        try:
            await MolnusApi(async_get_clientsession(self.hass), email, password).login()
        except MolnusAuthError:
            return "auth"
        except MolnusConnectionError:
            return "cannot_connect"
        except Exception:  # noqa: BLE001
            _LOGGER.exception("Molnus: oväntat fel vid inloggning")
            return "unknown"
        return None

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            email = user_input["email"].strip()
            await self.async_set_unique_id(email.lower())
            self._abort_if_unique_id_configured()
            if error := await self._validate(email, user_input["password"]):
                errors["base"] = error
            else:
                return self.async_create_entry(title=email, data={"email": email, "password": user_input["password"]})
        return self.async_show_form(step_id="user", data_schema=STEP_USER_DATA, errors=errors)

    async def async_step_reauth(self, entry_data: Mapping[str, Any]) -> ConfigFlowResult:
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        entry = self._get_reauth_entry()
        if user_input is not None:
            if error := await self._validate(entry.data["email"], user_input["password"]):
                errors["base"] = error
            else:
                return self.async_update_reload_and_abort(entry, data_updates={"password": user_input["password"]})
        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=vol.Schema({vol.Required("password"): str}),
            description_placeholders={"email": entry.data["email"]},
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        return MolnusOptionsFlow()


class MolnusOptionsFlow(OptionsFlowWithReload):
    """Laddar om integrationen när intervallet sparas (men inte vid reauth)."""

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(data=user_input)
        current = self.config_entry.options.get(CONF_SCAN_INTERVAL_MINUTES, DEFAULT_SCAN_INTERVAL_MINUTES)
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {vol.Required(CONF_SCAN_INTERVAL_MINUTES, default=current): vol.All(vol.Coerce(int), vol.Range(min=1, max=1440))}
            ),
        )
