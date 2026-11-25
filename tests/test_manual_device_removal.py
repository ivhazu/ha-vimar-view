"""Eliminazione manuale: solo i dispositivi che Vimar non riporta più."""
import asyncio
from types import SimpleNamespace

import custom_components.vimar_cloud as integ
from custom_components.vimar_cloud.api import VimarCloudClient
from custom_components.vimar_cloud.const import DOMAIN


def _check(identifier, complete=True, loaded=True):
    client = VimarCloudClient("u", "p", "duid", "")
    client.devices[100] = {"idsf": 100, "device_type": "light"}
    client.discovery_complete = complete
    hass = SimpleNamespace(data={DOMAIN: {"e1": client} if loaded else {}})
    device = SimpleNamespace(identifiers={(DOMAIN, identifier)})
    return asyncio.run(integ.async_remove_config_entry_device(hass, SimpleNamespace(entry_id="e1"), device))


def test_device_gone_from_vimar_can_be_removed():
    assert _check("e1_200") is True


def test_present_device_cannot_be_removed():
    assert _check("e1_100") is False


def test_gateway_and_energy_manager_cannot_be_removed():
    assert _check("e1") is False
    assert _check("e1_energy_manager") is False


def test_not_without_a_complete_discovery():
    assert _check("e1_200", complete=False) is False
    assert _check("e1_200", loaded=False) is False


def test_other_entry_device_cannot_be_removed():
    assert _check("e2_200") is False
