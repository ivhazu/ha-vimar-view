"""Vimar Cloud cover platform — roller shutters."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.cover import (
    ATTR_POSITION,
    CoverDeviceClass,
    CoverEntity,
    CoverEntityFeature,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .api import VimarCloudClient
from .const import DOMAIN, SFE_STATE_SHUTTER
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
        if device.get("device_type") == "shutter":
            entities.append(VimarCover(client, idsf, device, entry))
    async_add_entities(entities)


class VimarCover(CoverEntity):
    _attr_has_entity_name = True
    _attr_device_class = CoverDeviceClass.SHUTTER
    _attr_supported_features = (
        CoverEntityFeature.OPEN
        | CoverEntityFeature.CLOSE
        | CoverEntityFeature.STOP
        | CoverEntityFeature.SET_POSITION
    )

    def __init__(
        self,
        client: VimarCloudClient,
        idsf: int,
        device: dict,
        entry: ConfigEntry,
    ) -> None:
        self._client = client
        self._idsf = idsf
        self._last_cmd: str = ""
        self._attr_name = device["name"]
        self._attr_unique_id = f"{DOMAIN}_{idsf}_cover"
        self._attr_device_info = device_info_for_idsf(client, idsf, entry)

    async def async_added_to_hass(self) -> None:
        self._client.register_state_callback(self._on_update)

    @callback
    def _on_update(self, updated: list[int]) -> None:
        if self._idsf in updated:
            self.async_write_ha_state()

    def _raw_value(self) -> str | None:
        return self._client.get_state(self._idsf, SFE_STATE_SHUTTER)

    @property
    def current_cover_position(self) -> int | None:
        """Return position 0-100 where 100 = fully open.

        Vimar: 0 = open, 100 = closed — inverted vs HA convention.
        'Change to X' values are ignored (cover is moving).
        """
        value = self._raw_value()
        if value is None:
            return None
        if isinstance(value, str) and value.startswith("Change to"):
            return None  # moving, position unknown
        try:
            vimar_pos = int(value)
            return 100 - vimar_pos  # convert to HA convention
        except (ValueError, TypeError):
            return None

    @property
    def is_closed(self) -> bool | None:
        pos = self.current_cover_position
        if pos is None:
            return None
        return pos == 0

    @property
    def is_opening(self) -> bool:
        value = self._raw_value()
        return isinstance(value, str) and "Change to" in value and self._last_cmd == "open"

    @property
    def is_closing(self) -> bool:
        value = self._raw_value()
        return isinstance(value, str) and "Change to" in value and self._last_cmd == "close"

    async def async_open_cover(self, **kwargs: Any) -> None:
        self._last_cmd = "open"
        await self._client.open_cover(self._idsf)

    async def async_close_cover(self, **kwargs: Any) -> None:
        self._last_cmd = "close"
        await self._client.close_cover(self._idsf)

    async def async_stop_cover(self, **kwargs: Any) -> None:
        self._last_cmd = ""
        await self._client.stop_cover(self._idsf)

    async def async_set_cover_position(self, **kwargs: Any) -> None:
        ha_pos = kwargs[ATTR_POSITION]
        vimar_pos = 100 - ha_pos  # convert from HA to Vimar convention
        self._last_cmd = "open" if ha_pos > 50 else "close"
        await self._client.set_cover_position(self._idsf, vimar_pos)
