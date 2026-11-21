"""Inventory helpers shared by discovery reconciliation and unit tests.

Only devices owned by this config entry are eligible for cleanup.
The gateway and the energy-manager virtual device have non-numeric identifiers
and are deliberately excluded.
"""
from __future__ import annotations

from collections.abc import Iterable
from typing import Any


def inventory_signature(devices: dict[int, dict[str, Any]]) -> dict[int, tuple]:
    """Capture the entity-relevant properties of a successful discovery."""
    return {
        idsf: (
            device.get("name"),
            device.get("device_type"),
            device.get("sstype"),
            tuple(device.get("sfetypes", ())),
        )
        for idsf, device in devices.items()
    }


def stale_device_ids(
    registered_devices: Iterable[Any],
    *,
    entry_id: str,
    discovered_idsfs: Iterable[int],
    domain: str = "vimar_cloud",
) -> list[str]:
    """Find orphaned physical devices without touching unrelated entries."""
    present = set(discovered_idsfs)
    prefix = f"{entry_id}_"
    stale: list[str] = []

    for device in registered_devices:
        if device.config_entry_id != entry_id:
            continue
        for identifier_domain, identifier in device.identifiers:
            if identifier_domain != domain or not identifier.startswith(prefix):
                continue
            suffix = identifier[len(prefix):]
            if suffix.isascii() and suffix.isdecimal() and int(suffix) not in present:
                stale.append(device.id)
                break

    return sorted(set(stale))

def is_conservative_cleanup(stale_count: int, registered_count: int) -> bool:
    """Allow at most two removals and no more than 10% of registered devices.

    Protect against accidentally treating a cloud-side partial inventory
    as a deletion event. Bulk removals require explicit manual inspection.
    """
    return (
        0 < stale_count <= 2
        and registered_count > 0
        and stale_count * 10 <= registered_count
    )
