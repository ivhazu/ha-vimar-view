"""Vimar Cloud light platform."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.light import ATTR_BRIGHTNESS, ColorMode, LightEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .api import VimarCloudClient
from .const import DOMAIN, SFE_STATE_BRIGHTNESS, SFE_STATE_ONOFF
from .device_info import device_info_for_idsf

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    client: VimarCloudClient = hass.data[DOMAIN][entry.entry_id]
    entities = []
    for idsf, device in client.devices.items():
        dt = device.get("device_type")
        if dt == "light":
            entities.append(VimarLight(client, idsf, device, entry))
        elif dt == "dimmer":
            entities.append(VimarDimmer(client, idsf, device, entry))
    async_add_entities(entities)


class VimarLight(LightEntity):
    _attr_has_entity_name = True
    _attr_color_mode = ColorMode.ONOFF
    _attr_supported_color_modes = {ColorMode.ONOFF}

    def __init__(self, client: VimarCloudClient, idsf: int, device: dict, entry: ConfigEntry) -> None:
        self._client = client
        self._idsf = idsf
        self._attr_name = device["name"]
        self._attr_unique_id = f"{DOMAIN}_{idsf}_light"
        self._attr_device_info = device_info_for_idsf(client, idsf, entry, hass)

    async def async_added_to_hass(self) -> None:
        self._client.register_state_callback(self._on_update)

    @callback
    def _on_update(self, updated: list[int]) -> None:
        if self._idsf in updated:
            self.async_write_ha_state()

    @property
    def is_on(self) -> bool:
        return self._client.get_state(self._idsf, SFE_STATE_ONOFF) == "On"

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self._client.turn_on(self._idsf)

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self._client.turn_off(self._idsf)


class VimarDimmer(VimarLight):
    _attr_color_mode = ColorMode.BRIGHTNESS
    _attr_supported_color_modes = {ColorMode.BRIGHTNESS}

    def __init__(self, client: VimarCloudClient, idsf: int, device: dict, entry: ConfigEntry) -> None:
        super().__init__(client, idsf, device, entry)
        self._attr_unique_id = f"{DOMAIN}_{idsf}_dimmer"

    @property
    def brightness(self) -> int | None:
        value = self._client.get_state(self._idsf, SFE_STATE_BRIGHTNESS)
        try:
            return round(int(value) * 255 / 100) if value is not None else None
        except (ValueError, TypeError):
            return None

    async def async_turn_on(self, **kwargs: Any) -> None:
        if ATTR_BRIGHTNESS in kwargs:
            vimar_brightness = round(kwargs[ATTR_BRIGHTNESS] * 100 / 255)
            await self._client.turn_on(self._idsf)
            await self._client.set_brightness(self._idsf, vimar_brightness)
        else:
            await self._client.turn_on(self._idsf)
