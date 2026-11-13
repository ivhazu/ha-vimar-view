"""Vimar Cloud sensor platform."""
from __future__ import annotations

import json
import math
import logging
import time
from datetime import datetime, timezone

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
from homeassistant.util import dt as dt_util

from .api import VimarCloudClient
from .const import (
    DOMAIN,
    SFE_STATE_GLOBAL_ACTIVE_POWER,
    SFE_STATE_GLOBAL_ACTIVE_EXCHANGE,
    SFE_STATE_GLOBAL_ACTIVE_PRODUCT,
    SFE_STATE_GLOBAL_THRESHOLD,
    SFE_STATE_LOAD,
    MAX_ENERGY_SAMPLE_GAP,
    ENERGY_TELEMETRY_TYPES,
    SFE_STATE_TELEMETRY_G,
)
from .device_info import device_info_for_idsf, energy_manager_device_info
from .energy import integrate_power_delta_kwh

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

            entities.append(VimarPowerSensor(
                client, idsf, "Consumo Totale",
                em_info, f"{DOMAIN}_{idsf}_total_power"
            ))
            entities.append(VimarEnergySensor(
                client, idsf, "Consumo Totale kWh",
                em_info, f"{DOMAIN}_{idsf}_total_kwh"
            ))
            entities.append(VimarGridPowerSensor(
                client, idsf, "Scambio Rete",
                em_info, f"{DOMAIN}_{idsf}_grid_power"
            ))
            entities.append(VimarSolarPowerSensor(
                client, idsf, "Produzione Fotovoltaica",
                em_info, f"{DOMAIN}_{idsf}_solar_power"
            ))
            entities.append(VimarThresholdSensor(
                client, idsf, "Soglia Alert", 0,
                em_info, f"{DOMAIN}_{idsf}_threshold_alert"
            ))
            entities.append(VimarThresholdSensor(
                client, idsf, "Soglia Distacco", 1,
                em_info, f"{DOMAIN}_{idsf}_threshold_disconnect"
            ))
            for sstype, energy_name in ENERGY_TELEMETRY_TYPES.items():
                if sstype not in client.energy_telemetry_ids:
                    continue
                entities.append(VimarDailyTelemetryEnergySensor(
                    client, sstype, energy_name,
                    em_info, f"{DOMAIN}_{entry.entry_id}_{sstype}_daily_energy"
                ))
        elif dt == "load_control":
            dev_info = device_info_for_idsf(client, idsf, entry)
            entities.append(VimarPowerSensor(client, idsf, "Potenza", dev_info, f"{DOMAIN}_{idsf}_power"))
            entities.append(VimarEnergySensor(client, idsf, "Energia", dev_info, f"{DOMAIN}_{idsf}_kwh"))
            entities.append(VimarLoadStateSensor(client, idsf, dev_info, f"{DOMAIN}_{idsf}_load_state"))
        elif dt == "automation_switch":
            dev_info = device_info_for_idsf(client, idsf, entry)
            entities.append(VimarAutomationPowerSensor(client, idsf, dev_info, entry))
            entities.append(VimarAutomationEnergySensor(client, idsf, dev_info, entry))

    async_add_entities(entities)


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

    async def async_will_remove_from_hass(self) -> None:
        self._client.unregister_state_callback(self._on_update)

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


class VimarGridPowerSensor(VimarPowerSensor):
    """Potenza scambiata con la rete elettrica."""

    @property
    def native_value(self) -> float | None:
        value = self._client.get_state(self._idsf, SFE_STATE_GLOBAL_ACTIVE_EXCHANGE)
        try:
            return float(value) if value is not None else None
        except (ValueError, TypeError):
            return None


class VimarSolarPowerSensor(VimarPowerSensor):
    """Produzione fotovoltaica istantanea."""

    @property
    def native_value(self) -> float | None:
        value = self._client.get_state(self._idsf, SFE_STATE_GLOBAL_ACTIVE_PRODUCT)
        try:
            return float(value) if value is not None else None
        except (ValueError, TypeError):
            return None


class VimarEnergySensor(RestoreEntity, SensorEntity):
    """Energy sensor (kWh) — Riemann sum integral of power (W)."""

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
        last_state = await self.async_get_last_state()
        if last_state and last_state.state not in ("unknown", "unavailable", None):
            try:
                restored = float(last_state.state)
                if math.isfinite(restored) and 0.0 <= restored <= 1_000_000.0:
                    self._accumulated_kwh = restored
                    _LOGGER.debug("Vimar: restored %s = %.4f kWh", self._attr_unique_id, self._accumulated_kwh)
                else:
                    _LOGGER.warning("Vimar: discarded corrupted restore value %s = %s kWh, resetting to 0", self._attr_unique_id, restored)
                    self._accumulated_kwh = 0.0
            except (ValueError, TypeError):
                self._accumulated_kwh = 0.0
        self._last_ts = time.monotonic()
        self._client.register_state_callback(self._on_update)

    async def async_will_remove_from_hass(self) -> None:
        self._client.unregister_state_callback(self._on_update)

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
        if not math.isfinite(power_w) or power_w < 0:
            _LOGGER.warning("Vimar: ignoring invalid power value %r", power_w_raw)
            return
        now = time.monotonic()
        if self._last_power_w is not None and self._last_ts is not None:
            dt = now - self._last_ts
            if 0 < dt <= MAX_ENERGY_SAMPLE_GAP:
                self._accumulated_kwh += integrate_power_delta_kwh(
                    self._last_power_w, power_w, dt, MAX_ENERGY_SAMPLE_GAP
                )
            elif dt > MAX_ENERGY_SAMPLE_GAP:
                _LOGGER.debug("Vimar: energy sample gap %.0fs; skipping integration gap", dt)
        self._last_power_w = power_w
        self._last_ts = now
        self.async_write_ha_state()

    @property
    def native_value(self) -> float:
        return round(self._accumulated_kwh, 4)

    @property
    def extra_state_attributes(self) -> dict:
        return {
            "method": "trapezoidal",
            "source": "Vimar Cloud instantaneous power",
            "max_sample_gap_seconds": MAX_ENERGY_SAMPLE_GAP,
        }


class VimarDailyTelemetryEnergySensor(SensorEntity):
    """Energia giornaliera rilevata dalla telemetria oraria del cloud Vimar."""

    _attr_has_entity_name = True
    _attr_device_class = SensorDeviceClass.ENERGY
    _attr_state_class = SensorStateClass.TOTAL_INCREASING
    _attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR
    _attr_should_poll = False

    def __init__(self, client: VimarCloudClient, sstype: str, name: str, device_info, unique_id: str) -> None:
        self._client = client
        self._sstype = sstype
        self._attr_name = name
        self._attr_unique_id = unique_id
        self._attr_device_info = device_info

    @property
    def _idsf(self) -> int | None:
        """Risoluzione dinamica: valida anche dopo una riconnessione WebSocket."""
        return self._client.energy_telemetry_ids.get(self._sstype)

    async def async_added_to_hass(self) -> None:
        self._client.register_state_callback(self._on_update)

    async def async_will_remove_from_hass(self) -> None:
        self._client.unregister_state_callback(self._on_update)

    @callback
    def _on_update(self, updated: list[int]) -> None:
        if self._idsf is not None and self._idsf in updated:
            self.async_write_ha_state()

    @property
    def native_value(self) -> float | None:
        idsf = self._idsf
        if idsf is None:
            return None
        raw = self._client.get_state(idsf, SFE_STATE_TELEMETRY_G)
        received_at = self._client.energy_snapshot_received_at.get(idsf)
        if raw is None or received_at is None:
            return None
        now = dt_util.now()
        snapshot_time = dt_util.as_local(datetime.fromtimestamp(received_at, timezone.utc))
        if snapshot_time.date() != now.date():
            return None
        try:
            telemetry = json.loads(raw) if isinstance(raw, str) else raw
            values = telemetry["data"]
            if not isinstance(values, list):
                return None
            # G[0] e l'ora corrente, G[1] la precedente, ecc.
            count = snapshot_time.hour + 1
            today = values[:count]
            
            if len(today) != count:
                return None
            
            # Vimar può restituire None per l'ora corrente
            # finché la misura oraria non è disponibile.
            # Non consideriamo questo valore nella somma.
            if today[0] is None:
                today = today[1:]
            
            # I valori mancanti nelle ore precedenti
            # indicano invece dati incompleti.
            if any(v is None for v in today):
                return None
    
            numbers = [float(v) for v in today]
            if any(not math.isfinite(v) or v < 0 for v in numbers):
                return None
            return round(sum(numbers) / 1000, 3)
        except (ValueError, TypeError, KeyError, IndexError, AttributeError, OverflowError):
            return None

    @property
    def extra_state_attributes(self) -> dict:
        return {
            "source": "Vimar Cloud BigData",
            "telemetry_type": SFE_STATE_TELEMETRY_G,
            "bigdata_idsf": self._idsf,
            "bigdata_sstype": self._sstype,
            "calculation": "sum_hourly_values",
        }


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

    async def async_will_remove_from_hass(self) -> None:
        self._client.unregister_state_callback(self._on_update)

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

    async def async_will_remove_from_hass(self) -> None:
        self._client.unregister_state_callback(self._on_update)

    @callback
    def _on_update(self, updated: list[int]) -> None:
        if self._idsf in updated:
            self.async_write_ha_state()

    @property
    def native_value(self) -> str | None:
        return self._client.get_state(self._idsf, SFE_STATE_LOAD)


class VimarAutomationPowerSensor(SensorEntity):
    """Instantaneous power sensor for SS_Automation_OnOff devices."""

    _attr_has_entity_name = True
    _attr_name = "Potenza"
    _attr_native_unit_of_measurement = UnitOfPower.WATT
    _attr_device_class = SensorDeviceClass.POWER
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, client: VimarCloudClient, idsf: int, dev_info: dict, entry: ConfigEntry) -> None:
        self._client = client
        self._idsf = idsf
        self._attr_device_info = dev_info
        self._attr_unique_id = f"{DOMAIN}_{entry.entry_id}_{idsf}_automation_power"

    async def async_added_to_hass(self) -> None:
        self._client.register_state_callback(self._on_update)

    async def async_will_remove_from_hass(self) -> None:
        self._client.unregister_state_callback(self._on_update)

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


class VimarAutomationEnergySensor(RestoreEntity, SensorEntity):
    """Energy sensor (kWh) for SS_Automation_OnOff devices."""

    _attr_has_entity_name = True
    _attr_name = "Energia"
    _attr_device_class = SensorDeviceClass.ENERGY
    _attr_state_class = SensorStateClass.TOTAL_INCREASING
    _attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR

    def __init__(self, client: VimarCloudClient, idsf: int, dev_info: dict, entry: ConfigEntry) -> None:
        self._client = client
        self._idsf = idsf
        self._attr_device_info = dev_info
        self._attr_unique_id = f"{DOMAIN}_{entry.entry_id}_{idsf}_automation_kwh"
        self._accumulated_kwh: float = 0.0
        self._last_power_w: float | None = None
        self._last_ts: float | None = None

    async def async_added_to_hass(self) -> None:
        last_state = await self.async_get_last_state()
        if last_state and last_state.state not in ("unknown", "unavailable", None):
            try:
                restored = float(last_state.state)
                if math.isfinite(restored) and 0.0 <= restored <= 1_000_000.0:
                    self._accumulated_kwh = restored
                    _LOGGER.debug("Vimar: restored %s = %.4f kWh", self._attr_unique_id, self._accumulated_kwh)
                else:
                    _LOGGER.warning("Vimar: discarded corrupted restore value %s = %s kWh, resetting to 0", self._attr_unique_id, restored)
                    self._accumulated_kwh = 0.0
            except (ValueError, TypeError):
                self._accumulated_kwh = 0.0
        self._last_ts = time.monotonic()
        self._client.register_state_callback(self._on_update)

    async def async_will_remove_from_hass(self) -> None:
        self._client.unregister_state_callback(self._on_update)

    @callback
    def _on_update(self, updated: list[int]) -> None:
        if self._idsf not in updated:
            return
        value = self._client.get_state(self._idsf, SFE_STATE_GLOBAL_ACTIVE_POWER)
        if value is None:
            return
        try:
            power_w = float(value)
        except (ValueError, TypeError):
            return
        if not math.isfinite(power_w) or power_w < 0:
            _LOGGER.warning("Vimar: ignoring invalid power value %r", value)
            return
        now = time.monotonic()
        if self._last_power_w is not None and self._last_ts is not None:
            dt = now - self._last_ts
            if 0 < dt <= MAX_ENERGY_SAMPLE_GAP:
                self._accumulated_kwh += integrate_power_delta_kwh(
                    self._last_power_w, power_w, dt, MAX_ENERGY_SAMPLE_GAP
                )
            elif dt > MAX_ENERGY_SAMPLE_GAP:
                _LOGGER.debug("Vimar: automation energy sample gap %.0fs; skipping integration gap", dt)
        self._last_power_w = power_w
        self._last_ts = now
        self.async_write_ha_state()

    @property
    def native_value(self) -> float:
        return round(self._accumulated_kwh, 4)
