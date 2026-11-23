"""Issue #19: un termostato con DUID proprio non crea un gateway duplicato."""
import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import custom_components.vimar_cloud as integ
from custom_components.vimar_cloud import button, switch
from custom_components.vimar_cloud.api import VimarCloudClient
from custom_components.vimar_cloud.const import DOMAIN


def _client(types):
    client = VimarCloudClient("u", "p", "duid", "")
    for i, t in enumerate(types, start=1):
        client.devices[i] = {"idsf": i, "name": f"D{i}", "device_type": t, "sfetypes": [], "sstype": ""}
    return client


def test_standalone_thermostat_detection():
    assert _client(["thermostat"]).standalone_thermostat
    assert _client(["thermostat", "thermostat"]).standalone_thermostat
    assert not _client(["thermostat", "light"]).standalone_thermostat
    assert not _client(["light"]).standalone_thermostat
    assert not _client([]).standalone_thermostat


def test_thermostat_entry_loads_no_routines():
    client = _client(["thermostat"])
    client.load_routines = AsyncMock(return_value=[{"ruid": "r1", "name": "R"}])
    hass = SimpleNamespace(data={DOMAIN: {"e1": client}})
    entry = SimpleNamespace(entry_id="e1")
    added = []
    asyncio.run(button.async_setup_entry(hass, entry, lambda e: added.extend(e)))
    asyncio.run(switch.async_setup_entry(hass, entry, lambda e: added.extend(e)))
    client.load_routines.assert_not_awaited()
    assert added == []


def test_duplicate_gateway_device_is_removed(monkeypatch):
    gateway = SimpleNamespace(id="gw")
    dev_reg = MagicMock()
    dev_reg.async_get_device.return_value = gateway
    ent_reg = MagicMock()
    entities = [SimpleNamespace(entity_id="sensor.ultimo_evento", device_id="gw"),
                SimpleNamespace(entity_id="climate.zona", device_id="th")]
    monkeypatch.setattr(integ.dr, "async_get", lambda hass: dev_reg)
    monkeypatch.setattr(integ.er, "async_get", lambda hass: ent_reg)
    monkeypatch.setattr(integ.er, "async_entries_for_config_entry", lambda reg, eid: entities)
    integ._remove_duplicate_gateway_device(None, SimpleNamespace(entry_id="e1", title="Zona"))
    dev_reg.async_get_device.assert_called_once_with(identifiers={(DOMAIN, "e1")})
    ent_reg.async_remove.assert_called_once_with("sensor.ultimo_evento")
    dev_reg.async_remove_device.assert_called_once_with("gw")


def test_nothing_to_remove(monkeypatch):
    dev_reg = MagicMock()
    dev_reg.async_get_device.return_value = None
    monkeypatch.setattr(integ.dr, "async_get", lambda hass: dev_reg)
    integ._remove_duplicate_gateway_device(None, SimpleNamespace(entry_id="e1", title="Zona"))
    dev_reg.async_remove_device.assert_not_called()
