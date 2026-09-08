"""Vimar Cloud climate platform — termostati (SS_Clima_Zone)."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.climate import (
    ClimateEntity,
    ClimateEntityFeature,
    HVACAction,
    HVACMode,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import ATTR_TEMPERATURE, UnitOfTemperature
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .api import VimarCloudClient
from .const import (
    CHANGE_OVER_COOLING,
    CHANGE_OVER_HEATING,
    DOMAIN,
    HVAC_MODE_VIMAR_AUTO,
    HVAC_MODE_VIMAR_OFF,
    HVAC_MODE_VIMAR_TIMED_MANUAL,
    OUT_STATUS_COOL,
    OUT_STATUS_HEAT,
    SFE_STATE_AMBIENT_SETPOINT,
    SFE_STATE_AMBIENT_TEMPERATURE,
    SFE_STATE_CHANGE_OVER_MODE,
    SFE_STATE_HVAC_MODE,
    SFE_STATE_OUT_STATUS,
)
from .device_info import device_info_for_idsf

_LOGGER = logging.getLogger(__name__)

PRESET_SCHEDULE = "Programma"
PRESET_MANUAL = "Manuale"
PRESET_MODES = [PRESET_SCHEDULE, PRESET_MANUAL]


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Vimar climate entities from a config entry."""
    client: VimarCloudClient = hass.data[DOMAIN][entry.entry_id]
    entities = []
    # _LOGGER.warning(
    #     "VIMAR-DEBUG: climate setup called, %d devices in client", len(client.devices))
    for idsf, device in client.devices.items():
        # _LOGGER.warning("VIMAR-DEBUG: climate sees idsf=%s type=%s name=%r",
        #                 idsf, device.get("device_type"), device.get("name"))
        if device.get("device_type") == "thermostat":
            entities.append(VimarClimate(client, idsf, device, entry))
    # _LOGGER.warning("VIMAR-DEBUG: climate adding %d entities", len(entities))
    async_add_entities(entities)


class VimarClimate(ClimateEntity):
    """Rappresenta una zona clima Vimar (SS_Clima_Zone)."""

    _attr_has_entity_name = True
    _attr_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_hvac_modes = [HVACMode.OFF, HVACMode.HEAT, HVACMode.COOL]
    _attr_supported_features = (
        ClimateEntityFeature.TARGET_TEMPERATURE
        | ClimateEntityFeature.PRESET_MODE
    )
    _attr_preset_modes = PRESET_MODES
    _attr_target_temperature_step = 0.5
    _attr_min_temp = 5.0
    _attr_max_temp = 35.0

    def __init__(
        self,
        client: VimarCloudClient,
        idsf: int,
        device: dict,
        entry: ConfigEntry,
    ) -> None:
        self._client = client
        self._idsf = idsf
        self._attr_name = device["name"]
        self._attr_unique_id = f"{entry.entry_id}_{idsf}_climate"
        self._attr_device_info = device_info_for_idsf(client, idsf, entry, hass)

    async def async_added_to_hass(self) -> None:
        self._client.register_state_callback(self._on_update)

    @callback
    def _on_update(self, updated: list[int]) -> None:
        if self._idsf in updated:
            self.async_write_ha_state()

    # ─── Lettura stato ────────────────────────────────────────────────────────

    @property
    def current_temperature(self) -> float | None:
        """Temperatura ambiente misurata dal sensore."""
        value = self._client.get_state(
            self._idsf, SFE_STATE_AMBIENT_TEMPERATURE)
        try:
            return float(value) if value is not None else None
        except (ValueError, TypeError):
            return None

    @property
    def target_temperature(self) -> float | None:
        """Setpoint temperatura impostato."""
        value = self._client.get_state(self._idsf, SFE_STATE_AMBIENT_SETPOINT)
        try:
            return float(value) if value is not None else None
        except (ValueError, TypeError):
            return None

    @property
    def hvac_mode(self) -> HVACMode:
        """Modalità HVAC attiva.

        Logica:
        - SFE_State_HVACMode = "Off"  → HVACMode.OFF
        - SFE_State_HVACMode = "Auto" o "Timed manual" + ChangeOverMode = "Heating" → HVACMode.HEAT
        - SFE_State_HVACMode = "Auto" o "Timed manual" + ChangeOverMode = "Cooling" → HVACMode.COOL
        """
        mode = self._client.get_state(self._idsf, SFE_STATE_HVAC_MODE)
        if mode == HVAC_MODE_VIMAR_OFF:
            return HVACMode.OFF
        change_over = self._client.get_state(
            self._idsf, SFE_STATE_CHANGE_OVER_MODE)
        if change_over == CHANGE_OVER_COOLING:
            return HVACMode.COOL
        return HVACMode.HEAT

    @property
    def hvac_action(self) -> HVACAction | None:
        """Azione HVAC corrente (cosa sta fisicamente facendo il termostato).

        Deriva da SFE_State_OutStatus: Off / Heat / Cool.
        """
        mode = self._client.get_state(self._idsf, SFE_STATE_HVAC_MODE)
        if mode == HVAC_MODE_VIMAR_OFF:
            return HVACAction.OFF
        out_status = self._client.get_state(self._idsf, SFE_STATE_OUT_STATUS)
        if out_status == OUT_STATUS_HEAT:
            return HVACAction.HEATING
        if out_status == OUT_STATUS_COOL:
            return HVACAction.COOLING
        return HVACAction.IDLE

    @property
    def preset_mode(self) -> str | None:
        """Preset attivo: 'Programma' (settimanale) o 'Manuale' (temporaneo)."""
        mode = self._client.get_state(self._idsf, SFE_STATE_HVAC_MODE)
        if mode == HVAC_MODE_VIMAR_TIMED_MANUAL:
            return PRESET_MANUAL
        return PRESET_SCHEDULE

    # ─── Comandi ─────────────────────────────────────────────────────────────

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        """Imposta la modalità HVAC.

        - OFF  → SFE_Cmd_HVACMode = "Off"
        - HEAT → SFE_Cmd_ChangeOverMode = "Heating" + SFE_Cmd_HVACMode = "Auto"
        - COOL → SFE_Cmd_ChangeOverMode = "Cooling" + SFE_Cmd_HVACMode = "Auto"
        """
        if hvac_mode == HVACMode.OFF:
            await self._client.set_climate_hvac_mode(self._idsf, HVAC_MODE_VIMAR_OFF)
        elif hvac_mode == HVACMode.HEAT:
            await self._client.set_climate_change_over(self._idsf, CHANGE_OVER_HEATING)
            await self._client.set_climate_hvac_mode(self._idsf, HVAC_MODE_VIMAR_AUTO)
        elif hvac_mode == HVACMode.COOL:
            await self._client.set_climate_change_over(self._idsf, CHANGE_OVER_COOLING)
            await self._client.set_climate_hvac_mode(self._idsf, HVAC_MODE_VIMAR_AUTO)

    async def async_set_temperature(self, **kwargs: Any) -> None:
        """Imposta la temperatura target.

        Se il termostato è in modalità 'Programma' (Auto), passa automaticamente
        a 'Manuale temporaneo' (Timed manual) come fa l'app ufficiale Vimar.
        """
        temp = kwargs.get(ATTR_TEMPERATURE)
        if temp is None:
            return
        await self._client.set_climate_temperature(self._idsf, temp)

    async def async_set_preset_mode(self, preset_mode: str) -> None:
        """Imposta il preset.

        - 'Programma' → SFE_Cmd_HVACMode = "Auto"  (segue il programma settimanale)
        - 'Manuale'   → SFE_Cmd_HVACMode = "Timed manual"
        """
        if preset_mode == PRESET_MANUAL:
            await self._client.set_climate_hvac_mode(self._idsf, HVAC_MODE_VIMAR_TIMED_MANUAL)
        else:
            await self._client.set_climate_hvac_mode(self._idsf, HVAC_MODE_VIMAR_AUTO)
