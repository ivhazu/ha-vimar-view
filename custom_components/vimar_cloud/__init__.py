"""Vimar Cloud integration for Home Assistant."""
from __future__ import annotations

import asyncio
import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME, Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers import device_registry as dr

from .api import VimarCloudClient
from .const import CONF_DUID, CONF_PLANT_UID, CONF_REFRESH_TOKEN, DOMAIN
from .device_info import gateway_device_info
from .gateway_log import GatewayLogWatcher
from .routines import RoutineTracker
from .services import async_register_services
from .telemetry import TelemetryManager

_LOGGER = logging.getLogger(__name__)

PLATFORMS = [Platform.CLIMATE, Platform.LIGHT, Platform.SENSOR,
             Platform.SELECT, Platform.BUTTON, Platform.NUMBER, Platform.COVER, Platform.SWITCH]



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

    connect_task = entry.async_create_background_task(
        hass, client.connect(), "vimar_cloud_connection")

    try:
        await asyncio.wait_for(discovery_done.wait(), timeout=30)
        _LOGGER.info("Vimar: discovery complete, %d devices found",
                     len(client.devices))
    except asyncio.TimeoutError as err:
        # Senza discovery le piattaforme non creerebbero nessuna entità.
        # Chiudiamo la connessione e lasciamo che HA riprovi da solo più tardi.
        connect_task.cancel()
        await client.disconnect()
        hass.data[DOMAIN].pop(entry.entry_id, None)
        raise ConfigEntryNotReady(
            "Vimar cloud did not complete device discovery within 30s"
        ) from err

    # Register gateway device first so via_device works for all children
    dev_reg = dr.async_get(hass)
    gateway_device = dev_reg.async_get_or_create(
        config_entry_id=entry.entry_id,
        **gateway_device_info(entry, client),
    )
    client.gateway_device_id = gateway_device.id

    # Routine: elenco, aggiornamento ogni 15 minuti e rilevamento delle esecuzioni.
    tracker = RoutineTracker(hass, client, entry.data[CONF_DUID])
    await tracker.async_start()
    client.routine_tracker = tracker

    # Registro eventi del gateway → eventi HA e sensore "Ultimo evento".
    gateway_log = GatewayLogWatcher(hass, client)
    await gateway_log.async_start()
    client.gateway_log = gateway_log

    # Telemetria energia BigData (solo piani a pagamento con serie non vuote).
    telemetry = TelemetryManager(hass, client)
    await telemetry.async_start()
    client.telemetry = telemetry

    async_register_services(hass)
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    client: VimarCloudClient = hass.data[DOMAIN][entry.entry_id]
    if client.routine_tracker is not None:
        client.routine_tracker.async_stop()
    if client.gateway_log is not None:
        client.gateway_log.async_stop()
    if client.telemetry is not None:
        client.telemetry.async_stop()
    await client.disconnect()
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)
    return unload_ok
