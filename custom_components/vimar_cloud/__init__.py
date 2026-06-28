"""Vimar Cloud integration for Home Assistant."""
from __future__ import annotations

import asyncio
import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME, Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr

from .api import VimarCloudClient
from .const import CONF_DUID, CONF_PLANT_UID, DOMAIN
from .device_info import gateway_device_info

_LOGGER = logging.getLogger(__name__)

PLATFORMS = [Platform.CLIMATE, Platform.LIGHT, Platform.SENSOR,
             Platform.SELECT, Platform.BUTTON, Platform.NUMBER, Platform.COVER]

CONF_REFRESH_TOKEN = "refresh_token"


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Vimar Cloud from a config entry."""

    # Load saved refresh token if available (avoids full login on restart)
    saved_refresh_token: str | None = entry.data.get(CONF_REFRESH_TOKEN)

    client = VimarCloudClient(
        username=entry.data[CONF_USERNAME],
        password=entry.data[CONF_PASSWORD],
        duid=entry.data[CONF_DUID],
        plant_uid=entry.data.get(CONF_PLANT_UID, ""),
        refresh_token=saved_refresh_token,
    )

    # Persist refresh token whenever it changes
    def _on_token_update(new_refresh_token: str) -> None:
        if new_refresh_token != entry.data.get(CONF_REFRESH_TOKEN):
            hass.config_entries.async_update_entry(
                entry,
                data={**entry.data, CONF_REFRESH_TOKEN: new_refresh_token},
            )
            _LOGGER.debug("Vimar: refresh token saved to config entry")

    client.set_token_update_callback(_on_token_update)

    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = client

    discovery_done = asyncio.Event()
    client.set_discovery_callback(lambda: discovery_done.set())

    entry.async_create_background_task(
        hass, client.connect(), "vimar_cloud_connection")

    try:
        await asyncio.wait_for(discovery_done.wait(), timeout=30)
        _LOGGER.info("Vimar: discovery complete, %d devices found",
                     len(client.devices))
    except asyncio.TimeoutError:
        _LOGGER.warning("Vimar: discovery timeout after 30s")

    # Register gateway device first so via_device works for all children
    dev_reg = dr.async_get(hass)
    dev_reg.async_get_or_create(
        config_entry_id=entry.entry_id,
        **gateway_device_info(entry, client),
    )

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    client: VimarCloudClient = hass.data[DOMAIN][entry.entry_id]
    await client.disconnect()
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)
    return unload_ok
