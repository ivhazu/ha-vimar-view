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
    HVAC_MODE_VIMAR_ABSENCE,
    HVAC_MODE_VIMAR_AUTO,
    HVAC_MODE_VIMAR_MANUAL,
    HVAC_MODE_VIMAR_OFF,
    HVAC_MODE_VIMAR_PROTECTION,
    HVAC_MODE_VIMAR_REDUCTION,
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

PRESET_SCHEDULE = "Programma"     # Auto — segue il programma settimanale
PRESET_MANUAL = "Manuale"         # Timed manual — override temporaneo
PRESET_PERMANENT = "Permanente"   # Manual — override manuale permanente
PRESET_REDUCTION = "Riduzione"    # Reduction — setpoint di riduzione
PRESET_ABSENCE = "Assenza"        # Absence — setpoint di assenza ("Modalità Economy" nell'app View)
PRESET_PROTECTION = "Protezione"  # Protection — solo antigelo

# Preset HA ↔ modo di funzionamento Vimar (SFE_State/Cmd_HVACMode).
# "Off" non è un preset: è HVACMode.OFF.
PRESET_TO_VIMAR_MODE = {
    PRESET_SCHEDULE: HVAC_MODE_VIMAR_AUTO,
    PRESET_MANUAL: HVAC_MODE_VIMAR_TIMED_MANUAL,
    PRESET_PERMANENT: HVAC_MODE_VIMAR_MANUAL,
    PRESET_REDUCTION: HVAC_MODE_VIMAR_REDUCTION,
    PRESET_ABSENCE: HVAC_MODE_VIMAR_ABSENCE,
    PRESET_PROTECTION: HVAC_MODE_VIMAR_PROTECTION,
}
VIMAR_MODE_TO_PRESET = {mode: preset for preset, mode in PRESET_TO_VIMAR_MODE.items()}
PRESET_MODES = list(PRESET_TO_VIMAR_MODE)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Vimar climate entities from a config entry."""
    client: VimarCloudClient = hass.data[DOMAIN][entry.entry_id]
    entities = []
    for idsf, device in client.devices.items():
        if device.get("device_type") == "thermostat":
            entities.append(VimarClimate(client, idsf, device, entry))
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
        self._attr_name = None  # eredita il nome del device senza duplicarlo
        self._attr_unique_id = f"{entry.entry_id}_{idsf}_climate"
        self._attr_device_info = device_info_for_idsf(client, idsf, entry)

    async def async_added_to_hass(self) -> None:
        self._client.register_state_callback(self._on_update)

    async def async_will_remove_from_hass(self) -> None:
        self._client.unregister_state_callback(self._on_update)

    @callback
    def _on_update(self, updated: list[int]) -> None:
        if self._idsf in updated:
            self.async_write_ha_state()

    # ─── Lettura stato ────────────────────────────────────────────────────────

    @property
    def current_temperature(self) -> float | None:
        value = self._client.get_state(self._idsf, SFE_STATE_AMBIENT_TEMPERATURE)
        try:
            return float(value) if value is not None else None
        except (ValueError, TypeError):
            return None

    @property
    def target_temperature(self) -> float | None:
        value = self._client.get_state(self._idsf, SFE_STATE_AMBIENT_SETPOINT)
        try:
            return float(value) if value is not None else None
        except (ValueError, TypeError):
            return None

    @property
    def hvac_mode(self) -> HVACMode:
        """Modalità HVAC attiva.

        - Off                           → HVACMode.OFF
        - Auto / Timed manual / Manual  → HEAT o COOL in base a ChangeOverMode
        """
        mode = self._client.get_state(self._idsf, SFE_STATE_HVAC_MODE)
        if mode == HVAC_MODE_VIMAR_OFF:
            return HVACMode.OFF
        change_over = self._client.get_state(self._idsf, SFE_STATE_CHANGE_OVER_MODE)
        if change_over == CHANGE_OVER_COOLING:
            return HVACMode.COOL
        return HVACMode.HEAT

    @property
    def hvac_action(self) -> HVACAction | None:
        """Azione HVAC corrente derivata da SFE_State_OutStatus."""
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
        """Preset attivo, cioè il modo di funzionamento Vimar (vedi PRESET_TO_VIMAR_MODE).

        Con il termostato in Off, o con un modo sconosciuto, non c'è preset.
        """
        mode = self._client.get_state(self._idsf, SFE_STATE_HVAC_MODE)
        return VIMAR_MODE_TO_PRESET.get(mode)

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

        Se il termostato è in modalità Programma (Auto), passa automaticamente
        a Manuale temporaneo (Timed manual) come fa l'app ufficiale Vimar.
        """
        temp = kwargs.get(ATTR_TEMPERATURE)
        if temp is None:
            return
        await self._client.set_climate_temperature(self._idsf, temp)

    async def async_set_preset_mode(self, preset_mode: str) -> None:
        """Imposta il preset inviando il modo Vimar corrispondente (SFE_Cmd_HVACMode).

        La stagione (ChangeOverMode) non viene toccata: Riduzione e Assenza
        esistono anche in raffreddamento.
        """
        vimar_mode = PRESET_TO_VIMAR_MODE.get(preset_mode, HVAC_MODE_VIMAR_AUTO)
        await self._client.set_climate_hvac_mode(self._idsf, vimar_mode)
