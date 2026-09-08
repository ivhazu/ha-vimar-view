"""Vimar Cloud switch platform — automation on/off (SS_Automation_OnOff)."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.switch import SwitchDeviceClass, SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .api import VimarCloudClient
from .const import DOMAIN, SFE_STATE_ONOFF
from .device_info import device_info_for_idsf

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    client: VimarCloudClient = hass.data[DOMAIN][entry.entry_id]
    entities = [
        VimarAutomationSwitch(client, idsf, device, entry)
        for idsf, device in client.devices.items()
        if device.get("device_type") == "automation_switch"
    ]
    async_add_entities(entities)


class VimarAutomationSwitch(SwitchEntity):
    _attr_has_entity_name = True
    _attr_name = None  # usa solo il nome del device, evita duplicazione
    _attr_device_class = SwitchDeviceClass.OUTLET

    def __init__(
        self,
        client: VimarCloudClient,
        idsf: int,
        device: dict,
        entry: ConfigEntry,
    ) -> None:
        self._client = client
        self._idsf = idsf
        self._attr_unique_id = f"{DOMAIN}_{entry.entry_id}_{idsf}_switch"
        self._attr_device_info = device_info_for_idsf(client, idsf, entry)

    async def async_added_to_hass(self) -> None:
        self._client.register_state_callback(self._on_update)

    @callback
    def _on_update(self, updated: list[int]) -> None:
        if self._idsf in updated:
            self.async_write_ha_state()

    @property
    def is_on(self) -> bool | None:
        value = self._client.get_state(self._idsf, SFE_STATE_ONOFF)
        if value is None:
            return None
        return value == "On"

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self._client.turn_on_automation(self._idsf)

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self._client.turn_off_automation(self._idsf)
