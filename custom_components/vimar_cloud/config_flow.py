"""Config flow for Vimar Cloud integration."""
from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.data_entry_flow import FlowResult

from .api import VimarAuthError, VimarCloudClient
from .const import CONF_DUID, CONF_PLANT_NAME, CONF_PLANT_UID, DOMAIN

_LOGGER = logging.getLogger(__name__)


class VimarCloudConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Vimar Cloud."""

    VERSION = 1

    def __init__(self) -> None:
        self._username: str = ""
        self._password: str = ""

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Step 1: credentials + DUID."""
        errors: dict[str, str] = {}

        if user_input is not None:
            self._username = user_input[CONF_USERNAME]
            self._password = user_input[CONF_PASSWORD]
            duid = user_input[CONF_DUID].strip().upper()

            try:
                plant_name = await self._validate(duid)
            except VimarAuthError:
                errors["base"] = "invalid_auth"
            except Exception:
                _LOGGER.exception("Unexpected error during config flow")
                errors["base"] = "cannot_connect"
            else:
                await self.async_set_unique_id(duid)
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title=plant_name or "Vimar View",
                    data={
                        CONF_USERNAME: self._username,
                        CONF_PASSWORD: self._password,
                        CONF_DUID: duid,
                        CONF_PLANT_UID: "",
                        CONF_PLANT_NAME: plant_name,
                    },
                )

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({
                vol.Required(CONF_USERNAME): str,
                vol.Required(CONF_PASSWORD): str,
                vol.Required(CONF_DUID): str,
            }),
            errors=errors,
            description_placeholders={},
        )

    async def _validate(self, duid: str) -> str:
        """Login and verify DUID by connecting to WebSocket."""
        client = VimarCloudClient(
            username=self._username,
            password=self._password,
            duid=duid,
            plant_uid="",
        )
        await client._login()
        return "Vimar View"
