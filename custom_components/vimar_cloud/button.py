"""Vimar Cloud button platform — restore loads and scene activators."""
from __future__ import annotations

import logging

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .api import VimarCloudClient
from .const import DOMAIN
from .device_info import device_info_for_idsf, energy_manager_device_info

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
        elif device.get("device_type") == "scene_activator":
            entities.append(VimarSceneActivatorButton(client, idsf, device, entry))

    if client.idsf_energy_manager is not None:
        entities.append(VimarRestoreAllLoadsButton(client, entry))

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


class VimarSceneActivatorButton(ButtonEntity):
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
        self._attr_name = device["name"]
        self._attr_unique_id = f"{DOMAIN}_{idsf}_scene_activator"
        self._attr_device_info = device_info_for_idsf(client, idsf, entry)

    async def async_press(self) -> None:
        await self._client.execute_scene_activator(self._idsf)
