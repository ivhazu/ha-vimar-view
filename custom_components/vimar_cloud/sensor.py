"""Vimar Cloud sensor platform."""
from __future__ import annotations

import json
import logging
import time

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfEnergy, UnitOfPower
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity

from .api import VimarCloudClient
from .const import (
    DOMAIN,
    SFE_STATE_GLOBAL_ACTIVE_POWER,
    SFE_STATE_GLOBAL_THRESHOLD,
    SFE_STATE_LOAD,
)
from .device_info import device_info_for_idsf, energy_manager_device_info

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    client: VimarCloudClient = hass.data[DOMAIN][entry.entry_id]
    entities: list = []

    for idsf, device in client.devices.items():
        dt = device.get("device_type")

        if dt == "energy_manager":
            em_info = energy_manager_device_info(entry, client)
            entities.append(VimarPowerSensor(client, idsf, "Consumo Totale", em_info, f"{DOMAIN}_{idsf}_total_power"))
            entities.append(VimarEnergySensor(client, idsf, "Consumo Totale kWh", em_info, f"{DOMAIN}_{idsf}_total_kwh"))
            entities.append(VimarThresholdSensor(client, idsf, "Soglia Alert", 0, em_info, f"{DOMAIN}_{idsf}_threshold_alert"))
            entities.append(VimarThresholdSensor(client, idsf, "Soglia Distacco", 1, em_info, f"{DOMAIN}_{idsf}_threshold_disconnect"))

        elif dt == "load_control":
            dev_info = device_info_for_idsf(client, idsf, entry)
            entities.append(VimarPowerSensor(client, idsf, "Potenza", dev_info, f"{DOMAIN}_{idsf}_power"))
            entities.append(VimarEnergySensor(client, idsf, "Energia", dev_info, f"{DOMAIN}_{idsf}_kwh"))
            entities.append(VimarLoadStateSensor(client, idsf, dev_info, f"{DOMAIN}_{idsf}_load_state"))

    async_add_entities(entities)


# ─── Sensor entities ─────────────────────────────────────────────────────────

class VimarPowerSensor(SensorEntity):
    """Instantaneous power sensor (W)."""

    _attr_has_entity_name = True
    _attr_device_class = SensorDeviceClass.POWER
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = UnitOfPower.WATT

    def __init__(self, client: VimarCloudClient, idsf: int, name: str, device_info, unique_id: str) -> None:
        self._client = client
        self._idsf = idsf
        self._attr_name = name
        self._attr_unique_id = unique_id
        self._attr_device_info = device_info

    async def async_added_to_hass(self) -> None:
        self._client.register_state_callback(self._on_update)

    @callback
    def _on_update(self, updated: list[int]) -> None:
        if self._idsf in updated:
            self.async_write_ha_state()

    @property
    def native_value(self) -> float | None:
        value = self._client.get_state(self._idsf, SFE_STATE_GLOBAL_ACTIVE_POWER)
        try:
            return float(value) if value is not None else None
        except (ValueError, TypeError):
            return None


class VimarEnergySensor(RestoreEntity, SensorEntity):
    """Energy sensor (kWh) — Riemann sum integral of power (W).

    Uses the trapezoidal method to integrate power over time.
    The accumulated value persists across HA restarts via RestoreEntity.
    """

    _attr_has_entity_name = True
    _attr_device_class = SensorDeviceClass.ENERGY
    _attr_state_class = SensorStateClass.TOTAL_INCREASING
    _attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR

    def __init__(self, client: VimarCloudClient, idsf: int, name: str, device_info, unique_id: str) -> None:
        self._client = client
        self._idsf = idsf
        self._attr_name = name
        self._attr_unique_id = unique_id
        self._attr_device_info = device_info
        self._accumulated_kwh: float = 0.0
        self._last_power_w: float | None = None
        self._last_ts: float | None = None

    async def async_added_to_hass(self) -> None:
        """Restore accumulated value from recorder and subscribe to updates."""
        last_state = await self.async_get_last_state()
        if last_state and last_state.state not in ("unknown", "unavailable", None):
            try:
                self._accumulated_kwh = float(last_state.state)
                _LOGGER.debug("Vimar: restored %s = %.4f kWh", self._attr_unique_id, self._accumulated_kwh)
            except (ValueError, TypeError):
                self._accumulated_kwh = 0.0

        self._last_ts = time.monotonic()
        # Subscribe to state changes from our client
        self._client.register_state_callback(self._on_update)

    @callback
    def _on_update(self, updated: list[int]) -> None:
        if self._idsf not in updated:
            return

        power_w_raw = self._client.get_state(self._idsf, SFE_STATE_GLOBAL_ACTIVE_POWER)
        if power_w_raw is None:
            return

        try:
            power_w = float(power_w_raw)
        except (ValueError, TypeError):
            return

        now = time.monotonic()

        if self._last_power_w is not None and self._last_ts is not None:
            dt_hours = (now - self._last_ts) / 3600.0
            # Trapezoidal rule
            avg_w = (self._last_power_w + power_w) / 2.0
            delta_kwh = (avg_w * dt_hours) / 1000.0
            if delta_kwh >= 0:
                self._accumulated_kwh += delta_kwh

        self._last_power_w = power_w
        self._last_ts = now
        self.async_write_ha_state()

    @property
    def native_value(self) -> float:
        return round(self._accumulated_kwh, 4)

    @property
    def extra_state_attributes(self) -> dict:
        return {"method": "trapezoidal"}


class VimarThresholdSensor(SensorEntity):
    """Alert or disconnect threshold sensor (W) — read-only."""

    _attr_has_entity_name = True
    _attr_device_class = SensorDeviceClass.POWER
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = UnitOfPower.WATT

    def __init__(self, client: VimarCloudClient, idsf: int, name: str, index: int, device_info, unique_id: str) -> None:
        self._client = client
        self._idsf = idsf
        self._index = index
        self._attr_name = name
        self._attr_unique_id = unique_id
        self._attr_device_info = device_info

    async def async_added_to_hass(self) -> None:
        self._client.register_state_callback(self._on_update)

    @callback
    def _on_update(self, updated: list[int]) -> None:
        if self._idsf in updated:
            self.async_write_ha_state()

    @property
    def native_value(self) -> float | None:
        value = self._client.get_state(self._idsf, SFE_STATE_GLOBAL_THRESHOLD)
        if value is None:
            return None
        try:
            thresholds = json.loads(value) if isinstance(value, str) else value
            return float(thresholds[self._index])
        except (ValueError, TypeError, IndexError, json.JSONDecodeError):
            return None


class VimarLoadStateSensor(SensorEntity):
    """Load state sensor — Auto on / Forced on / etc."""

    _attr_has_entity_name = True

    def __init__(self, client: VimarCloudClient, idsf: int, device_info, unique_id: str) -> None:
        self._client = client
        self._idsf = idsf
        self._attr_name = "Stato"
        self._attr_unique_id = unique_id
        self._attr_device_info = device_info

    async def async_added_to_hass(self) -> None:
        self._client.register_state_callback(self._on_update)

    @callback
    def _on_update(self, updated: list[int]) -> None:
        if self._idsf in updated:
            self.async_write_ha_state()

    @property
    def native_value(self) -> str | None:
        return self._client.get_state(self._idsf, SFE_STATE_LOAD)
