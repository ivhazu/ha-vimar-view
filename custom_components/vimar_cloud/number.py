"""Vimar Cloud number platform — editable thresholds."""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass

from homeassistant.components.number import NumberDeviceClass, NumberEntity, NumberMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfPower, UnitOfTemperature
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .api import VimarCloudClient
from .const import (
    DOMAIN,
    FUNC_DOACTION,
    SFE_CMD_COOL_ABSENCE_SETPOINT,
    SFE_CMD_COOL_REDUCTION_SETPOINT,
    SFE_CMD_GLOBAL_THRESHOLD,
    SFE_CMD_HEAT_ABSENCE_SETPOINT,
    SFE_CMD_HEAT_PROTECTION_SETPOINT,
    SFE_CMD_HEAT_REDUCTION_SETPOINT,
    SFE_STATE_COOL_ABSENCE_SETPOINT,
    SFE_STATE_COOL_REDUCTION_SETPOINT,
    SFE_STATE_GLOBAL_THRESHOLD,
    SFE_STATE_HEAT_ABSENCE_SETPOINT,
    SFE_STATE_HEAT_PROTECTION_SETPOINT,
    SFE_STATE_HEAT_REDUCTION_SETPOINT,
)
from .device_info import device_info_for_idsf, energy_manager_device_info

_LOGGER = logging.getLogger(__name__)


@dataclass
class ClimateSetpointConfig:
    """Descrittore di un setpoint avanzato del termostato."""
    name: str
    state_sfe: str
    cmd_sfe: str
    min_temp: float
    max_temp: float
    unique_suffix: str


CLIMATE_SETPOINTS: list[ClimateSetpointConfig] = [
    ClimateSetpointConfig(
        name="Riscaldamento — Riduzione",
        state_sfe=SFE_STATE_HEAT_REDUCTION_SETPOINT,
        cmd_sfe=SFE_CMD_HEAT_REDUCTION_SETPOINT,
        min_temp=5.0,
        max_temp=25.0,
        unique_suffix="heat_reduction",
    ),
    ClimateSetpointConfig(
        name="Riscaldamento — Assenza",
        state_sfe=SFE_STATE_HEAT_ABSENCE_SETPOINT,
        cmd_sfe=SFE_CMD_HEAT_ABSENCE_SETPOINT,
        min_temp=5.0,
        max_temp=20.0,
        unique_suffix="heat_absence",
    ),
    ClimateSetpointConfig(
        name="Riscaldamento — Protezione Antigelo",
        state_sfe=SFE_STATE_HEAT_PROTECTION_SETPOINT,
        cmd_sfe=SFE_CMD_HEAT_PROTECTION_SETPOINT,
        min_temp=3.0,
        max_temp=10.0,
        unique_suffix="heat_protection",
    ),
    ClimateSetpointConfig(
        name="Raffreddamento — Riduzione",
        state_sfe=SFE_STATE_COOL_REDUCTION_SETPOINT,
        cmd_sfe=SFE_CMD_COOL_REDUCTION_SETPOINT,
        min_temp=20.0,
        max_temp=35.0,
        unique_suffix="cool_reduction",
    ),
    ClimateSetpointConfig(
        name="Raffreddamento — Assenza",
        state_sfe=SFE_STATE_COOL_ABSENCE_SETPOINT,
        cmd_sfe=SFE_CMD_COOL_ABSENCE_SETPOINT,
        min_temp=25.0,
        max_temp=35.0,
        unique_suffix="cool_absence",
    ),
]


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    client: VimarCloudClient = hass.data[DOMAIN][entry.entry_id]
    entities: list[NumberEntity] = []

    # Energy manager — soglie di potenza
    idsf = client.idsf_energy_manager
    if idsf is not None:
        em_info = energy_manager_device_info(entry, client)
        entities.append(VimarThresholdNumber(
            client, idsf, "Imposta Soglia Alert", 0, em_info, f"{DOMAIN}_{idsf}_set_alert"))
        entities.append(VimarThresholdNumber(
            client, idsf, "Imposta Soglia Distacco", 1, em_info, f"{DOMAIN}_{idsf}_set_disconnect"))

    # Termostati — setpoint avanzati di temperatura
    for idsf, device in client.devices.items():
        if device.get("device_type") == "thermostat":
            dev_info = device_info_for_idsf(client, idsf, entry)
            for cfg in CLIMATE_SETPOINTS:
                entities.append(
                    VimarClimateSetpointNumber(
                        client, idsf, cfg, dev_info, entry.entry_id)
                )

    async_add_entities(entities)


# ─── Energy manager thresholds ────────────────────────────────────────────────

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


# ─── Thermostat advanced setpoints ───────────────────────────────────────────

class VimarClimateSetpointNumber(NumberEntity):
    """Numero editabile per i setpoint avanzati del termostato Vimar."""

    _attr_has_entity_name = True
    _attr_device_class = NumberDeviceClass.TEMPERATURE
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
    _attr_mode = NumberMode.BOX
    _attr_native_step = 0.5

    def __init__(
        self,
        client: VimarCloudClient,
        idsf: int,
        cfg: ClimateSetpointConfig,
        device_info,
        entry_id: str,
    ) -> None:
        self._client = client
        self._idsf = idsf
        self._cfg = cfg
        self._attr_name = cfg.name
        self._attr_unique_id = f"{entry_id}_{idsf}_{cfg.unique_suffix}"
        self._attr_device_info = device_info
        self._attr_native_min_value = cfg.min_temp
        self._attr_native_max_value = cfg.max_temp

    async def async_added_to_hass(self) -> None:
        self._client.register_state_callback(self._on_update)

    @callback
    def _on_update(self, updated: list[int]) -> None:
        if self._idsf in updated:
            self.async_write_ha_state()

    @property
    def native_value(self) -> float | None:
        value = self._client.get_state(self._idsf, self._cfg.state_sfe)
        try:
            return float(value) if value is not None else None
        except (ValueError, TypeError):
            return None

    async def async_set_native_value(self, value: float) -> None:
        await self._client.set_climate_setpoint(self._idsf, self._cfg.cmd_sfe, value)
