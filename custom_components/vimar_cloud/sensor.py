"""Vimar Cloud sensor platform."""
from __future__ import annotations

import json
import math
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
from homeassistant.util import dt as dt_util

from .api import VimarCloudClient
from .const import (
    DOMAIN,
    SFE_STATE_GLOBAL_ACTIVE_EXCHANGE,
    SFE_STATE_GLOBAL_ACTIVE_POWER,
    SFE_STATE_GLOBAL_ACTIVE_PRODUCTION,
    SFE_STATE_GLOBAL_THRESHOLD,
    SFE_STATE_LOAD,
    MAX_ENERGY_SAMPLE_GAP,
)
from .device_info import device_info_for_idsf, energy_manager_device_info, gateway_device_info
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
            entities.append(VimarPowerSensor(client, idsf, "Consumo Totale", em_info, f"{DOMAIN}_{idsf}_total_power"))
            entities.append(VimarEnergySensor(client, idsf, "Consumo Totale kWh", em_info, f"{DOMAIN}_{idsf}_total_kwh"))
            # Fotovoltaico: solo se il gateway espone questi valori (02963 su scambio/produzione).
            em_sfetypes = device.get("sfetypes", [])
            if SFE_STATE_GLOBAL_ACTIVE_EXCHANGE in em_sfetypes:
                entities.append(VimarPowerSensor(
                    client, idsf, "Scambio Rete", em_info, f"{DOMAIN}_{idsf}_grid_power",
                    sfetype=SFE_STATE_GLOBAL_ACTIVE_EXCHANGE,
                ))
            if SFE_STATE_GLOBAL_ACTIVE_PRODUCTION in em_sfetypes:
                entities.append(VimarPowerSensor(
                    client, idsf, "Produzione Fotovoltaica", em_info, f"{DOMAIN}_{idsf}_solar_power",
                    sfetype=SFE_STATE_GLOBAL_ACTIVE_PRODUCTION,
                ))
            entities.append(VimarThresholdSensor(client, idsf, "Soglia Alert", 0, em_info, f"{DOMAIN}_{idsf}_threshold_alert"))
            entities.append(VimarThresholdSensor(client, idsf, "Soglia Distacco", 1, em_info, f"{DOMAIN}_{idsf}_threshold_disconnect"))

        elif dt == "load_control":
            dev_info = device_info_for_idsf(client, idsf, entry)
            entities.append(VimarPowerSensor(client, idsf, "Potenza", dev_info, f"{DOMAIN}_{idsf}_power"))
            entities.append(VimarEnergySensor(client, idsf, "Energia", dev_info, f"{DOMAIN}_{idsf}_kwh"))
            entities.append(VimarLoadStateSensor(client, idsf, dev_info, f"{DOMAIN}_{idsf}_load_state"))

        elif dt == "automation_switch":
            dev_info = device_info_for_idsf(client, idsf, entry)
            entities.append(VimarAutomationPowerSensor(client, idsf, dev_info, entry))
            entities.append(VimarAutomationEnergySensor(client, idsf, dev_info, entry))

    if client.gateway_log is not None:
        entities.append(VimarGatewayEventSensor(client, entry))

    # kWh di oggi dalla telemetria Vimar (piano a pagamento).
    if client.telemetry is not None and client.telemetry.series:
        from .telemetry import PERIOD_SUFFIX, SERIES_BASE_NAMES, SERIES_NAMES

        tele_info = (
            energy_manager_device_info(entry, client)
            if client.idsf_energy_manager is not None
            else gateway_device_info(entry, client)
        )
        for sstype, idsf in client.telemetry.series.items():
            entities.append(VimarTelemetryEnergySensor(
                client, idsf, SERIES_NAMES[sstype], tele_info,
                f"{DOMAIN}_{entry.entry_id}_{idsf}_daily_energy",
            ))
            for period in client.telemetry.periods.get(idsf, []):
                entities.append(VimarTelemetryEnergySensor(
                    client, idsf,
                    f"{SERIES_BASE_NAMES[sstype]} {PERIOD_SUFFIX[period]}", tele_info,
                    f"{DOMAIN}_{entry.entry_id}_{idsf}_{period}_energy",
                    period=period,
                ))

    # Ultima esecuzione di ogni routine (rilevata o avviata da HA).
    if client.routine_tracker is not None:
        for routine in client.routine_tracker.routines.values():
            entities.append(VimarRoutineLastRunSensor(client, routine.ruid, routine.name, entry))

    async_add_entities(entities)


# ─── Sensor entities ─────────────────────────────────────────────────────────

class VimarPowerSensor(SensorEntity):
    """Instantaneous power sensor (W)."""

    _attr_has_entity_name = True
    _attr_device_class = SensorDeviceClass.POWER
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = UnitOfPower.WATT

    def __init__(
        self,
        client: VimarCloudClient,
        idsf: int,
        name: str,
        device_info,
        unique_id: str,
        sfetype: str = SFE_STATE_GLOBAL_ACTIVE_POWER,
    ) -> None:
        self._client = client
        self._idsf = idsf
        self._sfetype = sfetype
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
        value = self._client.get_state(self._idsf, self._sfetype)
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

    def __init__(
        self, client: VimarCloudClient, idsf: int, name: str, device_info, unique_id: str,
        period: str | None = None,
    ) -> None:
        self._client = client
        self._idsf = idsf
        self._period = period
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
                # Sanity check: reset if value is clearly corrupted (>1 million kWh)
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

        # Vimar exposes instantaneous power only. We integrate locally, but never
        # invent consumption across long cloud/WebSocket gaps.
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
                _LOGGER.debug(
                    "Vimar: energy sample gap %.0fs; skipping integration gap", dt
                )

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
                _LOGGER.debug(
                    "Vimar: automation energy sample gap %.0fs; skipping integration gap", dt
                )
        self._last_power_w = power_w
        self._last_ts = now
        self.async_write_ha_state()

    @property
    def native_value(self) -> float:
        return round(self._accumulated_kwh, 4)


class VimarRoutineLastRunSensor(RestoreEntity, SensorEntity):
    """Data e ora dell'ultima esecuzione di una routine (dedotta per quelle programmate)."""

    _attr_has_entity_name = True
    _attr_device_class = SensorDeviceClass.TIMESTAMP
    _attr_icon = "mdi:robot-happy-outline"

    def __init__(self, client: VimarCloudClient, ruid: str, name: str, entry: ConfigEntry) -> None:
        self._client = client
        self._ruid = ruid
        self._attr_name = f"{name} ultima esecuzione"
        self._attr_unique_id = f"{DOMAIN}_{entry.entry_id}_routine_{ruid}_last_run"
        self._attr_device_info = gateway_device_info(entry, client)
        self._attr_native_value = None

    async def async_added_to_hass(self) -> None:
        last = await self.async_get_last_state()
        if last is not None and last.state not in ("unknown", "unavailable", None):
            restored = dt_util.parse_datetime(last.state)
            if restored is not None:
                self._attr_native_value = restored
        tracker = self._client.routine_tracker
        if tracker is not None:
            self.async_on_remove(tracker.add_listener(self._on_tracker_update))

    @callback
    def _on_tracker_update(self) -> None:
        when = self._client.routine_tracker.last_run.get(self._ruid)
        if when is not None and when != self._attr_native_value:
            self._attr_native_value = when
            self.async_write_ha_state()


class VimarGatewayEventSensor(SensorEntity):
    """Ultima voce del registro eventi del gateway (sezione "Eventi" dell'app)."""

    _attr_has_entity_name = True
    _attr_name = "Ultimo evento"
    _attr_icon = "mdi:history"

    def __init__(self, client: VimarCloudClient, entry: ConfigEntry) -> None:
        self._client = client
        self._attr_unique_id = f"{DOMAIN}_{entry.entry_id}_gateway_last_event"
        self._attr_device_info = gateway_device_info(entry, client)

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(self._client.gateway_log.add_listener(self.async_write_ha_state))

    @property
    def native_value(self) -> str | None:
        last = self._client.gateway_log.last
        return last["message"][:255] if last else None

    @property
    def extra_state_attributes(self) -> dict:
        last = self._client.gateway_log.last or {}
        return {k: v for k, v in last.items() if k != "message"}


class VimarTelemetryEnergySensor(SensorEntity):
    """kWh misurati da Vimar (telemetria BigData): oggi, oppure settimana/mese/anno in corso."""

    _attr_has_entity_name = True
    _attr_device_class = SensorDeviceClass.ENERGY
    _attr_state_class = SensorStateClass.TOTAL_INCREASING
    _attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR
    _attr_suggested_display_precision = 2

    def __init__(
        self, client: VimarCloudClient, idsf: int, name: str, device_info, unique_id: str,
        period: str | None = None,
    ) -> None:
        self._client = client
        self._idsf = idsf
        self._period = period
        self._attr_name = name
        self._attr_unique_id = unique_id
        self._attr_device_info = device_info

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(self._client.telemetry.add_listener(self.async_write_ha_state))

    @property
    def native_value(self) -> float | None:
        if self._period is None:
            return self._client.telemetry.value(self._idsf)
        return self._client.telemetry.period_value(self._idsf, self._period)

    @property
    def extra_state_attributes(self) -> dict:
        if self._period is None:
            return {"source": "Vimar BigData (Telemetry_G)", "bigdata_idsf": self._idsf}
        return {
            "source": "Vimar BigData (Telemetry_G + S/M)",
            "bigdata_idsf": self._idsf,
            "period": self._period,
        }
