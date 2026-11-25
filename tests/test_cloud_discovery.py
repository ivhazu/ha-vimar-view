"""Discovery regression tests; import the API without Home Assistant installed."""
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import AsyncMock, Mock

ROOT = Path(__file__).resolve().parents[1]
# Importing the integration package directly would load Home Assistant.
# The API itself depends only on aiohttp and the integration constants.
if "custom_components" not in sys.modules:
    package = types.ModuleType("custom_components")
    package.__path__ = [str(ROOT / "custom_components")]
    sys.modules["custom_components"] = package
if "custom_components.vimar_cloud" not in sys.modules:
    package = types.ModuleType("custom_components.vimar_cloud")
    package.__path__ = [str(ROOT / "custom_components/vimar_cloud")]
    sys.modules["custom_components.vimar_cloud"] = package

from custom_components.vimar_cloud.api import VimarCloudClient


def sf(idsf, name, sstype="SS_Light_Switch"):
    return {
        "idsf": idsf, "name": name, "sstype": sstype,
        "elements": [{"sfetype": "SFE_State_OnOff", "value": "Off"}],
    }


def plant(*devices):
    return [{"idambient": 1, "sf": list(devices)}]


class DiscoveryTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.client = VimarCloudClient(
            username="test", password="test", duid="test", plant_uid="test"
        )
        self.client._register_idsf = AsyncMock()
        self.client._send_request = AsyncMock(return_value="request-id")

    async def test_removed_devices_and_states_are_replaced(self):
        await self.client._process_plant_discovery(
            plant(sf(10134792, "Stufetta"), sf(13083912, "Stufetta"))
        )
        self.assertEqual(set(self.client.devices), {10134792, 13083912})
        self.client.device_states[10134792]["custom"] = "stale"
        await self.client._process_plant_discovery(plant(sf(13083912, "Stufetta")))
        self.assertEqual(set(self.client.devices), {13083912})
        self.assertNotIn(10134792, self.client.device_states)
        self.assertTrue(self.client.discovery_complete)

    async def test_rename_preserves_idsf(self):
        await self.client._process_plant_discovery(plant(sf(10, "Presa Ext")))
        await self.client._process_plant_discovery(plant(sf(10, "Presa Esterna")))
        self.assertEqual(self.client.devices[10]["name"], "Presa Esterna")

    async def test_empty_response_does_not_clear_inventory(self):
        await self.client._process_plant_discovery(plant(sf(10, "Presa Ext")))
        await self.client._process_plant_discovery([{"sf": []}])
        await self.client._process_plant_discovery(
            [{"sf": [{"name": "Partial without idsf"}]}]
        )
        self.assertEqual(set(self.client.devices), {10})
        self.assertTrue(self.client.discovery_complete)

    async def test_partial_discovery_is_used_but_not_trusted(self):
        await self.client._process_plant_discovery(
            [{"idambient": 1, "sf": [sf(10, "Luce"), {"name": "Senza idsf"}]}]
        )
        self.assertEqual(set(self.client.devices), {10})
        self.assertFalse(self.client.discovery_complete)

    async def test_bigdata_telemetry_states_are_kept(self):
        # The kWh sensors read the BigData series (idsf 9000x), which are not
        # part of the Plant discovery.
        self.client.bigdata_sfs = [{"idsf": 90001, "name": "Consumo"}]
        self.client.device_states[90001] = {"SFE_State_Telemetry_G": "{}"}
        await self.client._process_plant_discovery(plant(sf(10, "Luce")))
        self.assertIn(90001, self.client.device_states)

    async def test_energy_measure_pairings_are_recomputed(self):
        await self.client._process_plant_discovery(plant(
            sf(50, "Carico", "SS_Energy_Load"),
            sf(58, "Carico", "SS_Energy_Measure1P"),
        ))
        self.assertEqual(self.client.measure_to_load, {58: 50})
        await self.client._process_plant_discovery(plant(sf(99, "Lampada")))
        self.assertEqual(self.client.measure_to_load, {})
        self.assertEqual(self.client.automation_to_measure, {})
        self.assertNotIn(58, self.client.device_states)

    async def test_discovery_event_is_one_shot(self):
        event = Mock()
        self.client.set_discovery_callback(event)
        await self.client._process_plant_discovery(plant(sf(42, "Luce")))
        await self.client._process_plant_discovery(plant(sf(42, "Luce")))
        event.assert_called_once()


if __name__ == "__main__":
    unittest.main()
