"""Shared DeviceInfo helpers for Vimar Cloud."""
from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
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


def device_info_for_idsf(
    client: VimarCloudClient,
    idsf: int,
    entry: ConfigEntry,
) -> DeviceInfo:
    """DeviceInfo for a single Vimar device."""
    device = client.devices.get(idsf, {})
    name = device.get("name", f"Device {idsf}")
    sstype = device.get("sstype", "")
    model = SSTYPE_LABELS.get(sstype, sstype) if sstype else "Dispositivo Vimar"

    return DeviceInfo(
        identifiers={(DOMAIN, f"{entry.entry_id}_{idsf}")},
        name=name,
        manufacturer="Vimar",
        model=model,
        serial_number=str(idsf),
        via_device=(DOMAIN, entry.entry_id),
    )


def energy_manager_device_info(entry: ConfigEntry, client: VimarCloudClient) -> DeviceInfo:
    """DeviceInfo for the energy manager."""
    idsf = client.idsf_energy_manager
    return DeviceInfo(
        identifiers={(DOMAIN, f"{entry.entry_id}_energy_manager")},
        name="Gestione Carichi",
        manufacturer="Vimar",
        model=ENERGY_MANAGER_MODEL,
        serial_number=str(idsf) if idsf else None,
        via_device=(DOMAIN, entry.entry_id),
    )
