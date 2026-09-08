"""Vimar Cloud select platform — load control."""
from __future__ import annotations

import logging

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .api import VimarCloudClient
from .const import DOMAIN, LOAD_STATE_AUTO, LOAD_STATE_FORCED_OFF, LOAD_STATE_FORCED_ON, SFE_STATE_LOAD
from .device_info import device_info_for_idsf

_LOGGER = logging.getLogger(__name__)

LOAD_OPTIONS = [LOAD_STATE_AUTO, LOAD_STATE_FORCED_ON, LOAD_STATE_FORCED_OFF]


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
    _attr_options = LOAD_OPTIONS

    def __init__(self, client: VimarCloudClient, idsf: int, entry: ConfigEntry) -> None:
        self._client = client
        self._idsf = idsf
        self._attr_name = "Modalità"
        self._attr_unique_id = f"{DOMAIN}_{idsf}_load_select"
        self._attr_device_info = device_info_for_idsf(client, idsf, entry, hass)

    async def async_added_to_hass(self) -> None:
        self._client.register_state_callback(self._on_update)

    @callback
    def _on_update(self, updated):
        if self._idsf in updated:
            self.async_write_ha_state()

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
        await self._client.set_load(self._idsf, option)
