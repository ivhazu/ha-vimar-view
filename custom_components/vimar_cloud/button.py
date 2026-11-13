"""Vimar Cloud button platform — restore loads and scene activators."""
from __future__ import annotations

import logging

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .api import VimarCloudClient, VimarConnectionError
from .routines import SOURCE_HOME_ASSISTANT
from .const import DOMAIN
from .device_info import device_info_for_idsf, energy_manager_device_info, gateway_device_info

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    client: VimarCloudClient = hass.data[DOMAIN][entry.entry_id]
    entities = []

    for idsf, device in client.devices.items():
        if device.get("device_type") == "load_control":
            entities.append(VimarRestoreLoadButton(client, idsf, entry))
        elif device.get("device_type") == "scene":
            entities.append(VimarSceneButton(client, idsf, device, entry))

    if client.idsf_energy_manager is not None:
        entities.append(VimarRestoreAllLoadsButton(client, entry))

    # Routine dell'app VIEW (API REST): un errore qui non deve bloccare il resto.
    try:
        routines = await client.load_routines()
    except Exception as err:  # noqa: BLE001
        _LOGGER.warning("Vimar: could not load routines: %s", err)
        routines = []
    _LOGGER.debug("Vimar: %d routines found", len(routines))
    for routine in routines:
        entities.append(VimarRoutineButton(client, routine, entry))

    async_add_entities(entities)


class VimarRestoreLoadButton(ButtonEntity):
    _attr_has_entity_name = True
    _attr_icon = "mdi:restore"

    def __init__(self, client: VimarCloudClient, idsf: int, entry: ConfigEntry) -> None:
        self._client = client
        self._idsf = idsf
        self._attr_name = "Ripristina"
        self._attr_unique_id = f"{DOMAIN}_{idsf}_restore"
        self._attr_device_info = device_info_for_idsf(client, idsf, entry)

    async def async_press(self) -> None:
        await self._client.restore_load(self._idsf)


class VimarRestoreAllLoadsButton(ButtonEntity):
    _attr_has_entity_name = True
    _attr_name = "Ripristina Tutti i Carichi"
    _attr_icon = "mdi:restore-alert"

    def __init__(self, client: VimarCloudClient, entry: ConfigEntry) -> None:
        self._client = client
        self._attr_unique_id = f"{DOMAIN}_{entry.entry_id}_restore_all"
        self._attr_device_info = energy_manager_device_info(entry, client)

    async def async_press(self) -> None:
        await self._client.restore_all_loads()


class VimarSceneButton(ButtonEntity):
    _attr_has_entity_name = True
    _attr_icon = "mdi:play-circle-outline"

    def __init__(
        self,
        client: VimarCloudClient,
        idsf: int,
        device: dict,
        entry: ConfigEntry,
    ) -> None:
        self._client = client
        self._idsf = idsf
        # The scene button is the main feature of the scene device.
        # With has_entity_name=True, None makes HA use the device name once,
        # avoiding names/entity_ids such as "Scene Scene" / "scene_scene".
        self._attr_name = None
        self._attr_unique_id = f"{DOMAIN}_{idsf}_scene"
        self._attr_device_info = device_info_for_idsf(client, idsf, entry)

    async def async_press(self) -> None:
        await self._client.execute_scene(self._idsf)


class VimarRoutineButton(ButtonEntity):
    """Esegue una routine creata nell'app Vimar VIEW."""

    _attr_has_entity_name = True
    _attr_icon = "mdi:robot"

    def __init__(self, client: VimarCloudClient, routine: dict, entry: ConfigEntry) -> None:
        self._client = client
        self._ruid: str = routine["ruid"]
        self._attr_name = routine.get("name") or "Routine"
        self._attr_unique_id = f"{DOMAIN}_{entry.entry_id}_routine_{self._ruid}"
        self._attr_device_info = gateway_device_info(entry, client)
        self._attr_extra_state_attributes = {"attiva": bool(routine.get("isActive", True))}

    async def async_press(self) -> None:
        try:
            await self._client.execute_routine(self._ruid)
        except (VimarConnectionError, TimeoutError) as err:
            raise HomeAssistantError(f"Vimar routine '{self.name}' failed: {err}") from err
        if self._client.routine_tracker is not None:
            self._client.routine_tracker.mark_executed(self._ruid, SOURCE_HOME_ASSISTANT)
