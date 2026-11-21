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
from .inventory import inventory_signature, stale_device_ids, is_conservative_cleanup
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

    # Telemetria energia BigData (solo le serie con dati).
    telemetry = TelemetryManager(hass, client)
    await telemetry.async_start()
    client.telemetry = telemetry

    async_register_services(hass)
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # A discovery can change while the integration is running (VIEW app or WS
    # reconnect). Verify fresh cloud snapshots before touching the HA registry.
    inventory_changed = asyncio.Event()
    client.set_inventory_change_callback(inventory_changed.set)
    entry.async_create_background_task(
        hass,
        _monitor_inventory(hass, entry, client, inventory_changed),
        "vimar_cloud_inventory_monitor",
    )
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    client: VimarCloudClient = hass.data[DOMAIN][entry.entry_id]
    client.set_inventory_change_callback(None)
    client.set_discovery_callback(None)
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


async def _request_confirmed_snapshot(client: VimarCloudClient) -> dict | None:
    """Ask the cloud for a fresh inventory; do not trust a cached snapshot."""
    received = asyncio.Event()
    client.set_discovery_callback(received.set)
    try:
        await client.request_plant_discovery()
        await asyncio.wait_for(received.wait(), timeout=20)
        return inventory_signature(client.devices)
    except (asyncio.TimeoutError, ConnectionError) as err:
        _LOGGER.warning("Vimar: inventory verification skipped: %s", err)
        return None
    except Exception:
        _LOGGER.exception("Vimar: inventory verification failed")
        return None
    finally:
        client.set_discovery_callback(None)


async def _remove_missing_registry_devices(
    hass: HomeAssistant,
    entry: ConfigEntry,
    discovered_idsfs: set[int],
) -> None:
    """Remove exclusively-owned devices absent from two cloud inventories.

    Never remove a gateway, a virtual energy manager or a device owned by
    another config entry. This includes user-disabled entities on removed
    physical devices, but preserves all user overrides on surviving IDs.
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

    # A partial cloud result must never wipe a substantial part of a home.
    registered_count = sum(
        1 for device in registered_devices
        if any(
            domain == DOMAIN and identifier.startswith(f"{entry.entry_id}_")
            and identifier[len(entry.entry_id) + 1:].isascii()
            and identifier[len(entry.entry_id) + 1:].isdecimal()
            for domain, identifier in device.identifiers
        )
    )
    if stale_ids and not is_conservative_cleanup(len(stale_ids), registered_count):
        _LOGGER.warning(
            "Vimar: refusing bulk registry cleanup (%d stale of %d physical devices). "
            "Review the cloud inventory before removing any devices.",
            len(stale_ids), registered_count,
        )
        return

    for device_id in stale_ids:
        # Re-check ownership immediately before the irreversible operation.
        device = device_registry.async_get(device_id)
        if device is None or device.config_entry_id != entry.entry_id:
            continue

        affected = [
            entity for entity in er.async_entries_for_config_entry(entity_registry, entry.entry_id)
            if entity.device_id == device_id
        ]
        for entity in affected:
            entity_registry.async_remove(entity.entity_id)
        device_registry.async_remove_device(device_id)
        _LOGGER.info(
            "Vimar: removed stale device %s and %d registry entities",
            device_id, len(affected),
        )


async def _monitor_inventory(
    hass: HomeAssistant,
    entry: ConfigEntry,
    client: VimarCloudClient,
    wake: asyncio.Event,
) -> None:
    """Check periodically and on reconnection; require consistent snapshots.

    First confirmation permits cleanup of entries left by prior versions.
    Subsequent additions/removals/renames cause a reload only after two
    matching fresh replies, preventing transient partial discoveries.
    """
    setup_snapshot = inventory_signature(client.devices)
    reconciled = False

    while True:
        snapshot = await _request_confirmed_snapshot(client)
        if snapshot is not None and snapshot:
            if snapshot == setup_snapshot:
                if not reconciled:
                    await _remove_missing_registry_devices(hass, entry, set(snapshot))
                    reconciled = True
            else:
                second = await _request_confirmed_snapshot(client)
                if second == snapshot:
                    _LOGGER.info("Vimar: verified cloud inventory change; reloading entry")
                    # Do not await a reload from this entry-owned background task:
                    # HA cancels entry tasks during unload.
                    hass.async_create_task(
                        hass.config_entries.async_reload(entry.entry_id),
                        f"vimar_cloud_inventory_reload_{entry.entry_id}",
                    )
                    return
                _LOGGER.warning(
                    "Vimar: inconsistent discovery snapshots, keeping existing registry"
                )

        wake.clear()
        try:
            await asyncio.wait_for(wake.wait(), timeout=300)
        except asyncio.TimeoutError:
            pass
