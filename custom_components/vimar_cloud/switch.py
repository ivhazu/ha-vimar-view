"""Vimar Cloud switch platform — automation on/off (SS_Automation_OnOff)."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.switch import SwitchDeviceClass, SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .api import VimarCloudClient, VimarConnectionError
from .const import DOMAIN, SFE_STATE_ONOFF
from .device_info import device_info_for_idsf, gateway_device_info

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

    # Interruttore "abilitata" per ogni routine dell'app VIEW.
    try:
        routines = await client.load_routines()
    except Exception as err:  # noqa: BLE001
        _LOGGER.warning("Vimar: could not load routines: %s", err)
        routines = []
    entities.extend(VimarRoutineActiveSwitch(client, r, entry) for r in routines)

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

    async def async_will_remove_from_hass(self) -> None:
        self._client.unregister_state_callback(self._on_update)

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


class VimarRoutineActiveSwitch(SwitchEntity):
    """Abilita o sospende una routine dell'app VIEW."""

    _attr_has_entity_name = True
    _attr_icon = "mdi:robot-outline"

    def __init__(self, client: VimarCloudClient, routine: dict, entry: ConfigEntry) -> None:
        self._client = client
        self._ruid: str = routine["ruid"]
        self._attr_name = f"{routine.get('name') or 'Routine'} abilitata"
        self._attr_unique_id = f"{DOMAIN}_{entry.entry_id}_routine_{self._ruid}_active"
        self._attr_device_info = gateway_device_info(entry, client)
        self._attr_is_on = bool(routine.get("isActive", True))

    async def async_added_to_hass(self) -> None:
        tracker = self._client.routine_tracker
        if tracker is not None:
            self.async_on_remove(tracker.add_listener(self._on_tracker_update))

    @callback
    def _on_tracker_update(self) -> None:
        active = self._client.routine_tracker.is_active(self._ruid)
        if active is not None and active != self._attr_is_on:
            self._attr_is_on = active
            self.async_write_ha_state()

    async def _set_active(self, active: bool) -> None:
        try:
            await self._client.set_routine_active(self._ruid, active)
        except (VimarConnectionError, TimeoutError) as err:
            raise HomeAssistantError(f"Vimar routine '{self.name}' update failed: {err}") from err
        self._attr_is_on = active
        if self._client.routine_tracker is not None:
            self._client.routine_tracker.set_active(self._ruid, active)
        self.async_write_ha_state()

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self._set_active(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self._set_active(False)
