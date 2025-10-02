# custom_components/molnus/config_flow.py
from __future__ import annotations

import voluptuous as vol
from homeassistant import config_entries

from .const import DOMAIN

STEP_USER_DATA = vol.Schema(
    {
        vol.Required("email"): str,
        vol.Required("password"): str,
        vol.Optional("camera_id", default=""): str,
        vol.Optional("auto_fetch_interval_hours", default=1): int,
        # Influx v2 (optional)
        #vol.Optional("influx_url", default=""): str,
        #vol.Optional("influx_token", default=""): str,
        #vol.Optional("influx_org", default=""): str,
        #vol.Optional("influx_bucket", default=""): str,
        # Influx v1 (legacy) (optional)
        vol.Optional("influx_version", default="2"): str,  # "1" or "2"
        vol.Optional("influx_db", default=""): str,
        vol.Optional("influx_user", default=""): str,
        vol.Optional("influx_password", default=""): str,
    }
)


class MolnusConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Config flow for Molnus integration."""

    VERSION = 1

    async def async_step_user(self, user_input=None):
        """Handle a flow initialized by the user."""
        errors = {}
        if user_input is None:
            return self.async_show_form(step_id="user", data_schema=STEP_USER_DATA)

        # Validate credentials by attempting to login
        from .client import MolnusClient, MolnusAuthError

        client = MolnusClient(user_input["email"], user_input["password"])
        try:
            await client.login()
        except MolnusAuthError:
            errors["base"] = "auth"
        except Exception:
            errors["base"] = "unknown"

        if errors:
            return self.async_show_form(step_id="user", data_schema=STEP_USER_DATA, errors=errors)

        entry_data = {
            "email": user_input["email"],
            "password": user_input["password"],
            "camera_id": user_input.get("camera_id", "") or "",
            "auto_fetch_interval_hours": int(user_input.get("auto_fetch_interval_hours", 1)),
            # influx v2
            "influx_url": user_input.get("influx_url", "") or "",
            "influx_token": user_input.get("influx_token", "") or "",
            "influx_org": user_input.get("influx_org", "") or "",
            "influx_bucket": user_input.get("influx_bucket", "") or "",
            # influx v1
            "influx_version": user_input.get("influx_version", "2"),
            "influx_db": user_input.get("influx_db", "") or "",
            "influx_user": user_input.get("influx_user", "") or "",
            "influx_password": user_input.get("influx_password", "") or "",
        }

        await self.async_set_unique_id(f"molnus_{user_input['email']}")
        self._abort_if_unique_id_configured()
        return self.async_create_entry(title=user_input["email"], data=entry_data)
