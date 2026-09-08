"""Shared DeviceInfo helpers for Vimar Cloud."""
from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.device_registry import DeviceInfo

from .api import VimarCloudClient
from .const import DOMAIN, ENERGY_MANAGER_MODEL, GATEWAY_MODEL, SSTYPE_LABELS


def gateway_device_info(entry: ConfigEntry, client: VimarCloudClient) -> DeviceInfo:
    """DeviceInfo for the Vimar gateway (root device)."""
    return DeviceInfo(
        identifiers={(DOMAIN, entry.entry_id)},
        name=client.plant_name or "Vimar View",
        manufacturer="Vimar",
        model=GATEWAY_MODEL,
        sw_version=client.gateway_sw_version or None,
        connections={("mac", client.gateway_mac)} if client.gateway_mac else set(),
    )


def _get_gateway_device_id(hass: HomeAssistant, entry: ConfigEntry) -> str | None:
    """Return the device registry ID of the gateway, if already registered."""
    registry = dr.async_get(hass)
    device = registry.async_get_device(identifiers={(DOMAIN, entry.entry_id)})
    return device.id if device else None


def device_info_for_idsf(
    client: VimarCloudClient,
    idsf: int,
    entry: ConfigEntry,
    hass: HomeAssistant | None = None,
) -> DeviceInfo:
    """DeviceInfo for a single Vimar device."""
    device = client.devices.get(idsf, {})
    name = device.get("name", f"Device {idsf}")
    sstype = device.get("sstype", "")
    model = SSTYPE_LABELS.get(sstype, sstype) if sstype else "Dispositivo Vimar"

    kwargs: dict = dict(
        identifiers={(DOMAIN, f"{entry.entry_id}_{idsf}")},
        name=name,
        manufacturer="Vimar",
        model=model,
        serial_number=str(idsf),
    )

    if hass is not None:
        gateway_id = _get_gateway_device_id(hass, entry)
        if gateway_id:
            kwargs["via_device_id"] = gateway_id
        else:
            kwargs["via_device"] = (DOMAIN, entry.entry_id)
    else:
        kwargs["via_device"] = (DOMAIN, entry.entry_id)

    return DeviceInfo(**kwargs)


def energy_manager_device_info(
    entry: ConfigEntry,
    client: VimarCloudClient,
    hass: HomeAssistant | None = None,
) -> DeviceInfo:
    """DeviceInfo for the energy manager."""
    idsf = client.idsf_energy_manager

    kwargs: dict = dict(
        identifiers={(DOMAIN, f"{entry.entry_id}_energy_manager")},
        name="Gestione Carichi",
        manufacturer="Vimar",
        model=ENERGY_MANAGER_MODEL,
        serial_number=str(idsf) if idsf else None,
    )

    if hass is not None:
        gateway_id = _get_gateway_device_id(hass, entry)
        if gateway_id:
            kwargs["via_device_id"] = gateway_id
        else:
            kwargs["via_device"] = (DOMAIN, entry.entry_id)
    else:
        kwargs["via_device"] = (DOMAIN, entry.entry_id)

    return DeviceInfo(**kwargs)
