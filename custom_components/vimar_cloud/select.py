"""Vimar Cloud select platform — load control."""
from __future__ import annotations

import logging

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .api import VimarCloudClient
from .const import DOMAIN, LOAD_STATE_AUTO, LOAD_STATE_FORCED_OFF, LOAD_STATE_FORCED_ON, SFE_STATE_LOAD
from .device_info import device_info_for_idsf

_LOGGER = logging.getLogger(__name__)

# Modalità che l'utente può impostare. "Forced off" non è un comando valido:
# lo imposta solo il gateway quando il consumo supera la soglia di distacco.
SELECTABLE_OPTIONS = [LOAD_STATE_AUTO, LOAD_STATE_FORCED_ON]


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    client: VimarCloudClient = hass.data[DOMAIN][entry.entry_id]
    entities = []
    for idsf, device in client.devices.items():
        if device.get("device_type") == "load_control":
            entities.append(VimarLoadSelect(client, idsf, entry))
    async_add_entities(entities)


class VimarLoadSelect(SelectEntity):
    _attr_has_entity_name = True

    def __init__(self, client: VimarCloudClient, idsf: int, entry: ConfigEntry) -> None:
        self._client = client
        self._idsf = idsf
        self._attr_name = "Modalità"
        self._attr_unique_id = f"{DOMAIN}_{idsf}_load_select"
        self._attr_device_info = device_info_for_idsf(client, idsf, entry)

    async def async_added_to_hass(self) -> None:
        self._client.register_state_callback(self._on_update)

    async def async_will_remove_from_hass(self) -> None:
        self._client.unregister_state_callback(self._on_update)

    @callback
    def _on_update(self, updated):
        if self._idsf in updated:
            self.async_write_ha_state()

    @property
    def options(self) -> list[str]:
        # "Forced off" compare tra le opzioni solo mentre è attivo, così lo stato
        # viene mostrato correttamente ma non si può selezionare.
        if self.current_option == LOAD_STATE_FORCED_OFF:
            return [*SELECTABLE_OPTIONS, LOAD_STATE_FORCED_OFF]
        return SELECTABLE_OPTIONS

    @property
    def current_option(self):
        state = self._client.get_state(self._idsf, SFE_STATE_LOAD)
        if state is None:
            return None
        if state.startswith("Auto"):
            return LOAD_STATE_AUTO
        if state == "Forced on":
            return LOAD_STATE_FORCED_ON
        if state == "Forced off":
            return LOAD_STATE_FORCED_OFF
        return LOAD_STATE_AUTO

    async def async_select_option(self, option: str) -> None:
        if option not in SELECTABLE_OPTIONS:
            if option == self.current_option:
                return  # già attivo, niente da inviare
            raise ServiceValidationError(
                f"'{option}' cannot be selected: it is set automatically by the "
                "Vimar gateway when the disconnect threshold is exceeded"
            )
        await self._client.set_load(self._idsf, option)
