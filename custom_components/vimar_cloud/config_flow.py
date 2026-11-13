"""Config flow for Vimar Cloud integration."""
from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.data_entry_flow import FlowResult

from .api import VimarAuthError, VimarCloudClient
from .const import CONF_DUID, CONF_PLANT_NAME, CONF_PLANT_UID, CONF_REFRESH_TOKEN, DOMAIN

_LOGGER = logging.getLogger(__name__)

# Modelli noti restituiti dal cloud (campo "model" delle associazioni).
MODEL_LABELS = {"BLEG": "Gateway", "STW": "Termostato"}


def gateway_label(gw: dict) -> str:
    """Etichetta leggibile per la scelta del gateway."""
    name = gw.get("displayname") or gw.get("plantname") or "Vimar View"
    model = gw.get("model", "")
    kind = MODEL_LABELS.get(model, model or "Dispositivo")
    offline = "" if gw.get("online", True) else " — offline"
    return f"{name} · {kind} ({gw['duid']}){offline}"


class VimarCloudConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Vimar Cloud."""

    VERSION = 1

    def __init__(self) -> None:
        self._username: str = ""
        self._password: str = ""
        self._refresh_token: str | None = None
        self._gateways: dict[str, dict] = {}

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Step 1: credenziali MyVimar, poi elenco dei gateway dell'account."""
        errors: dict[str, str] = {}

        if user_input is not None:
            self._username = user_input[CONF_USERNAME]
            self._password = user_input[CONF_PASSWORD]
            client = VimarCloudClient(
                username=self._username, password=self._password, duid="", plant_uid=""
            )
            try:
                await client._login()
            except VimarAuthError:
                errors["base"] = "invalid_auth"
            except Exception:  # noqa: BLE001
                _LOGGER.exception("Unexpected error during login")
                errors["base"] = "cannot_connect"
            else:
                self._refresh_token = client.refresh_token
                try:
                    gateways = await client.get_gateways()
                except Exception as err:  # noqa: BLE001
                    _LOGGER.warning("Vimar: could not list gateways, falling back to manual DUID: %s", err)
                    gateways = []
                return await self._async_after_login(gateways)

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({
                vol.Required(CONF_USERNAME): str,
                vol.Required(CONF_PASSWORD): str,
            }),
            errors=errors,
        )

    async def _async_after_login(self, gateways: list[dict]) -> FlowResult:
        if not gateways:
            return await self.async_step_manual()

        configured = self._async_current_ids()
        self._gateways = {
            str(gw["duid"]).upper(): gw for gw in gateways
            if str(gw["duid"]).upper() not in configured
        }
        if not self._gateways:
            return self.async_abort(reason="all_configured")
        if len(self._gateways) == 1:
            return await self._async_create_for(next(iter(self._gateways.values())))
        return await self.async_step_gateway()

    async def async_step_gateway(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Step 2: scelta del gateway (o termostato) da configurare."""
        if user_input is not None:
            return await self._async_create_for(self._gateways[user_input[CONF_DUID]])

        options = {duid: gateway_label(gw) for duid, gw in self._gateways.items()}
        return self.async_show_form(
            step_id="gateway",
            data_schema=vol.Schema({vol.Required(CONF_DUID): vol.In(options)}),
        )

    async def async_step_manual(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Alternativa: DUID inserito a mano (se l'elenco non è disponibile)."""
        if user_input is not None:
            duid = user_input[CONF_DUID].strip().upper()
            return await self._async_create_for({"duid": duid})

        return self.async_show_form(
            step_id="manual",
            data_schema=vol.Schema({vol.Required(CONF_DUID): str}),
        )

    async def _async_create_for(self, gw: dict) -> FlowResult:
        duid = str(gw["duid"]).strip().upper()
        await self.async_set_unique_id(duid)
        self._abort_if_unique_id_configured()
        data = {
            CONF_USERNAME: self._username,
            CONF_PASSWORD: self._password,
            CONF_DUID: duid,
            CONF_PLANT_UID: gw.get("plantuid", "") or "",
            CONF_PLANT_NAME: gw.get("plantname") or gw.get("displayname") or "Vimar View",
        }
        if self._refresh_token:
            # Evita un secondo login completo (e la relativa email) al primo avvio.
            data[CONF_REFRESH_TOKEN] = self._refresh_token
        title = gw.get("displayname") or gw.get("plantname") or "Vimar View"
        if gw.get("model") and gw["model"] != "BLEG":
            title = f"{title} ({MODEL_LABELS.get(gw['model'], gw['model'])})"
        return self.async_create_entry(title=title, data=data)
