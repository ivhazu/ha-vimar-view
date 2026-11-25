"""PR #20: all'avvio si rimuovono i dispositivi cancellati in VIEW, con prudenza."""
import asyncio
from types import SimpleNamespace
from unittest.mock import MagicMock

import custom_components.vimar_cloud as integ
from custom_components.vimar_cloud import button
from custom_components.vimar_cloud.api import VimarCloudClient
from custom_components.vimar_cloud.const import DOMAIN

ENTRY = SimpleNamespace(entry_id="e1", title="Casa")


def _device(device_id, suffix, owner="e1"):
    return SimpleNamespace(
        id=device_id, name=device_id, config_entry_id=owner,
        identifiers={(DOMAIN, f"e1_{suffix}" if suffix is not None else "e1")},
    )


def _run(monkeypatch, devices, discovered):
    by_id = {d.id: d for d in devices}
    dev_reg = MagicMock()
    dev_reg.async_get.side_effect = by_id.get
    ent_reg = MagicMock()
    entities = [SimpleNamespace(entity_id=f"light.{d.id}", device_id=d.id) for d in devices]
    monkeypatch.setattr(integ.dr, "async_get", lambda hass: dev_reg)
    monkeypatch.setattr(integ.dr, "async_entries_for_config_entry", lambda reg, eid: devices)
    monkeypatch.setattr(integ.er, "async_get", lambda hass: ent_reg)
    monkeypatch.setattr(integ.er, "async_entries_for_config_entry", lambda reg, eid: entities)
    integ._remove_missing_registry_devices(None, ENTRY, discovered)
    return dev_reg, ent_reg


def _home(count):
    return [_device("gateway", None)] + [_device(f"d{i}", i) for i in range(1, count + 1)]


def test_device_deleted_in_view_is_removed(monkeypatch):
    dev_reg, ent_reg = _run(monkeypatch, _home(20), set(range(1, 20)))
    dev_reg.async_remove_device.assert_called_once_with("d20")
    ent_reg.async_remove.assert_called_once_with("light.d20")


def test_gateway_and_present_devices_are_kept(monkeypatch):
    dev_reg, _ = _run(monkeypatch, _home(20), set(range(1, 21)))
    dev_reg.async_remove_device.assert_not_called()


def test_bulk_removal_is_refused(monkeypatch):
    dev_reg, ent_reg = _run(monkeypatch, _home(20), set(range(1, 18)))
    dev_reg.async_remove_device.assert_not_called()
    ent_reg.async_remove.assert_not_called()


def test_device_of_another_entry_is_kept(monkeypatch):
    devices = _home(20)
    devices[-1].config_entry_id = "e2"
    dev_reg, _ = _run(monkeypatch, devices, set(range(1, 20)))
    dev_reg.async_remove_device.assert_not_called()


def test_gateway_entry_has_sync_button():
    client = VimarCloudClient("u", "p", "duid", "")
    client.devices[1] = {"idsf": 1, "name": "Luce", "device_type": "light", "sfetypes": [], "sstype": ""}
    client.load_routines = MagicMock()

    async def _no_routines():
        return []

    client.load_routines.side_effect = _no_routines
    hass = SimpleNamespace(data={DOMAIN: {"e1": client}})
    added = []
    asyncio.run(button.async_setup_entry(hass, ENTRY, lambda e: added.extend(e)))
    sync = [e for e in added if isinstance(e, button.VimarSyncDevicesButton)]
    assert len(sync) == 1
    assert sync[0].unique_id == f"{DOMAIN}_e1_sync_devices"

    sync[0].hass = SimpleNamespace(config_entries=MagicMock())
    asyncio.run(sync[0].async_press())
    sync[0].hass.config_entries.async_schedule_reload.assert_called_once_with("e1")
