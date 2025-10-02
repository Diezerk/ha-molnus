# custom_components/molnus/config_flow.py
from __future__ import annotations
import voluptuous as vol
from homeassistant import config_entries
from .const import DOMAIN

STEP_USER_DATA = vol.Schema({
    vol.Required("email"): str,
    vol.Required("password"): str,
    vol.Optional("camera_id", default=""): str,
    vol.Optional("auto_fetch_interval_hours", default=1): int,
    # Influx settings (optional)
    vol.Optional("influx_url", default=""): str,
    vol.Optional("influx_token", default=""): str,
    vol.Optional("influx_org", default=""): str,
    vol.Optional("influx_bucket", default=""): str,
})

class MolnusConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input=None):
        errors = {}
        if user_input is None:
            return self.async_show_form(step_id="user", data_schema=STEP_USER_DATA)

        # Testa inloggning genom att initiera klient och anropa login()
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
            "influx_url": user_input.get("influx_url", "") or "",
            "influx_token": user_input.get("influx_token", "") or "",
            "influx_org": user_input.get("influx_org", "") or "",
            "influx_bucket": user_input.get("influx_bucket", "") or "",
        }

        await self.async_set_unique_id(f"molnus_{user_input['email']}")
        self._abort_if_unique_id_configured()
        return self.async_create_entry(title=user_input["email"], data=entry_data)
