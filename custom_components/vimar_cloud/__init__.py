"""Vimar Cloud integration for Home Assistant."""
from __future__ import annotations

import asyncio
import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME, Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers import device_registry as dr, entity_registry as er

from .api import VimarCloudClient
from .const import CONF_DUID, CONF_PLANT_UID, CONF_REFRESH_TOKEN, DOMAIN
from .device_info import gateway_device_info
from .gateway_log import GatewayLogWatcher
from .inventory import device_belongs_to_entry, is_conservative_cleanup, stale_device_ids
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

    dev_reg = dr.async_get(hass)
    if client.standalone_thermostat:
        # Termostato Wi-Fi con DUID proprio: è lui il dispositivo principale.
        # Niente gateway, registro eventi e routine: sono dell'entry del gateway (issue #19).
        _remove_duplicate_gateway_device(hass, entry)
    else:
        # Register gateway device first so via_device works for all children
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

        # Telemetria energia BigData (solo le serie con dati).
        telemetry = TelemetryManager(hass, client)
        await telemetry.async_start()
        client.telemetry = telemetry

    async_register_services(hass)
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # Remove devices deleted in the VIEW app, comparing the registry with the
    # discovery that setup has just received: no extra cloud calls. Additions
    # and renames are already picked up by every (re)load.
    if client.discovery_complete:
        _remove_missing_registry_devices(hass, entry, set(client.devices))
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


def _remove_duplicate_gateway_device(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Rimuove il gateway duplicato creato dalle versioni precedenti per un termostato."""
    dev_reg = dr.async_get(hass)
    device = dev_reg.async_get_device(identifiers={(DOMAIN, entry.entry_id)})
    if device is None:
        return
    ent_reg = er.async_get(hass)
    entities = [
        e for e in er.async_entries_for_config_entry(ent_reg, entry.entry_id)
        if e.device_id == device.id
    ]
    for ent in entities:
        ent_reg.async_remove(ent.entity_id)
    dev_reg.async_remove_device(device.id)
    _LOGGER.info(
        "Vimar: removed duplicate gateway device of thermostat entry %s (%d entities)",
        entry.title, len(entities),
    )


def _remove_missing_registry_devices(
    hass: HomeAssistant,
    entry: ConfigEntry,
    discovered_idsfs: set[int],
) -> None:
    """Remove this entry's physical devices that the cloud no longer reports.

    Never remove a gateway, the virtual energy manager or a device owned by
    another config entry, and never more than a few devices at once.
    """
    device_registry = dr.async_get(hass)
    entity_registry = er.async_get(hass)
    registered_devices = dr.async_entries_for_config_entry(
        device_registry, entry.entry_id
    )
    stale_ids = stale_device_ids(
        registered_devices,
        entry_id=entry.entry_id,
        discovered_idsfs=discovered_idsfs,
        domain=DOMAIN,
    )
    if not stale_ids:
        return

    prefix = f"{entry.entry_id}_"
    registered_count = sum(
        1 for device in registered_devices
        if any(
            domain == DOMAIN and identifier.startswith(prefix)
            and identifier[len(prefix):].isascii()
            and identifier[len(prefix):].isdecimal()
            for domain, identifier in device.identifiers
        )
    )
    # A partial cloud result must never wipe a substantial part of a home.
    if not is_conservative_cleanup(len(stale_ids), registered_count):
        _LOGGER.warning(
            "Vimar: refusing bulk registry cleanup (%d stale of %d physical devices). "
            "Remove them manually if they were really deleted in the VIEW app.",
            len(stale_ids), registered_count,
        )
        return

    for device_id in stale_ids:
        device = device_registry.async_get(device_id)
        if device is None or not device_belongs_to_entry(device, entry.entry_id):
            continue
        affected = [
            entity for entity in er.async_entries_for_config_entry(entity_registry, entry.entry_id)
            if entity.device_id == device_id
        ]
        for entity in affected:
            entity_registry.async_remove(entity.entity_id)
        device_registry.async_remove_device(device_id)
        _LOGGER.info(
            "Vimar: removed device %s deleted in VIEW (%d entities)",
            device.name, len(affected),
        )


async def async_remove_config_entry_device(
    hass: HomeAssistant, entry: ConfigEntry, device: dr.DeviceEntry
) -> bool:
    """Consente di eliminare a mano un dispositivo solo se Vimar non lo riporta più.

    Mai il gateway, mai la gestione carichi, mai un dispositivo ancora presente
    nell'impianto. Serve quando la pulizia automatica all'avvio si ferma per
    prudenza (impianti piccoli o più dispositivi rimossi insieme).
    """
    client: VimarCloudClient | None = hass.data.get(DOMAIN, {}).get(entry.entry_id)
    if client is None or not client.discovery_complete:
        return False
    prefix = f"{entry.entry_id}_"
    for domain, identifier in device.identifiers:
        if domain != DOMAIN or not identifier.startswith(prefix):
            continue
        suffix = identifier[len(prefix):]
        if suffix.isascii() and suffix.isdecimal():
            return int(suffix) not in client.devices
    return False
