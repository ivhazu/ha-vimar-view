"""Vimar Cloud number platform — editable thresholds."""
from __future__ import annotations

import json
import logging

from homeassistant.components.number import NumberDeviceClass, NumberEntity, NumberMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfPower
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .api import VimarCloudClient
from .const import DOMAIN, FUNC_DOACTION, SFE_CMD_GLOBAL_THRESHOLD, SFE_STATE_GLOBAL_THRESHOLD
from .device_info import energy_manager_device_info

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    client: VimarCloudClient = hass.data[DOMAIN][entry.entry_id]
    entities = []
    idsf = client.idsf_energy_manager
    if idsf is not None:
        em_info = energy_manager_device_info(entry, client)
        entities.append(VimarThresholdNumber(client, idsf, "Imposta Soglia Alert", 0, em_info, f"{DOMAIN}_{idsf}_set_alert"))
        entities.append(VimarThresholdNumber(client, idsf, "Imposta Soglia Distacco", 1, em_info, f"{DOMAIN}_{idsf}_set_disconnect"))
    async_add_entities(entities)


class VimarThresholdNumber(NumberEntity):
    _attr_has_entity_name = True
    _attr_device_class = NumberDeviceClass.POWER
    _attr_native_unit_of_measurement = UnitOfPower.WATT
    _attr_mode = NumberMode.BOX
    _attr_native_min_value = 100
    _attr_native_max_value = 10000
    _attr_native_step = 100

    def __init__(self, client, idsf, name, index, device_info, unique_id) -> None:
        self._client = client
        self._idsf = idsf
        self._index = index
        self._attr_name = name
        self._attr_unique_id = unique_id
        self._attr_device_info = device_info

    async def async_added_to_hass(self) -> None:
        self._client.register_state_callback(self._on_update)

    @callback
    def _on_update(self, updated):
        if self._idsf in updated:
            self.async_write_ha_state()

    def _get_thresholds(self) -> list[float]:
        value = self._client.get_state(self._idsf, SFE_STATE_GLOBAL_THRESHOLD)
        if value is None:
            return [3000.0, 3500.0]
        try:
            thresholds = json.loads(value) if isinstance(value, str) else value
            return [float(t) for t in thresholds]
        except (ValueError, TypeError, json.JSONDecodeError):
            return [3000.0, 3500.0]

    @property
    def native_value(self) -> float:
        return self._get_thresholds()[self._index]

    async def async_set_native_value(self, value: float) -> None:
        thresholds = self._get_thresholds()
        thresholds[self._index] = value
        if thresholds[0] >= thresholds[1]:
            if self._index == 0:
                thresholds[1] = thresholds[0] + 100
            else:
                thresholds[0] = thresholds[1] - 100
        new_value = json.dumps([int(t) for t in thresholds])
        await self._client._send_request(
            FUNC_DOACTION,
            [{"idsf": self._idsf, "sfetype": SFE_CMD_GLOBAL_THRESHOLD, "value": new_value}],
        )
