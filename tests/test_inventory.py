"""Regression tests for physical-device registry reconciliation."""
import importlib.util
from pathlib import Path
from types import SimpleNamespace
import unittest

MODULE_PATH = Path(__file__).resolve().parents[1] / "custom_components/vimar_cloud/inventory.py"
spec = importlib.util.spec_from_file_location("vimar_inventory_helpers", MODULE_PATH)
inventory = importlib.util.module_from_spec(spec)
spec.loader.exec_module(inventory)


def make_device(device_id, identifiers, config_entry_id="entry1"):
    return SimpleNamespace(
        id=device_id,
        identifiers=set(identifiers),
        config_entry_id=config_entry_id,
    )


class InventoryTests(unittest.TestCase):
    def test_only_orphaned_physical_device_is_removed(self):
        devices = [
            make_device("keep", {("vimar_cloud", "entry1_42")}),
            make_device("removed", {("vimar_cloud", "entry1_11")}),
            make_device("gateway", {("vimar_cloud", "entry1")}),
            make_device("energy_manager", {("vimar_cloud", "entry1_energy_manager")}),
            make_device("other_entry", {("vimar_cloud", "entry2_11")}, "entry2"),
            make_device("wrong_owner", {("vimar_cloud", "entry1_11")}, "entry2"),
            make_device("homekit", {("homekit_controller", "entry1_11")}),
        ]
        self.assertEqual(
            inventory.stale_device_ids(
                devices, entry_id="entry1", discovered_idsfs={42}
            ),
            ["removed"],
        )

    def test_replacement_idsf_is_a_new_device(self):
        devices = [
            make_device("old", {("vimar_cloud", "entry1_10134792")}),
            make_device("new", {("vimar_cloud", "entry1_13083912")}),
        ]
        self.assertEqual(
            inventory.stale_device_ids(
                devices, entry_id="entry1", discovered_idsfs={13083912}
            ),
            ["old"],
        )

    def test_identifier_prefix_and_numeric_suffix_are_required(self):
        devices = [
            make_device("bad_prefix", {("vimar_cloud", "entry12_100")}),
            make_device("nonnumeric", {("vimar_cloud", "entry1_routine_123")}),
            make_device("unicode", {("vimar_cloud", "entry1_１２３")}),
            make_device("absent", {("vimar_cloud", "entry1_100")}),
        ]
        self.assertEqual(
            inventory.stale_device_ids(
                devices, entry_id="entry1", discovered_idsfs={9}
            ),
            ["absent"],
        )

    def test_bulk_cleanup_guard(self):
        self.assertTrue(inventory.is_conservative_cleanup(1, 38))
        self.assertTrue(inventory.is_conservative_cleanup(2, 38))
        self.assertFalse(inventory.is_conservative_cleanup(3, 38))
        self.assertFalse(inventory.is_conservative_cleanup(1, 5))
        self.assertFalse(inventory.is_conservative_cleanup(12, 38))
        self.assertFalse(inventory.is_conservative_cleanup(0, 38))
        self.assertFalse(inventory.is_conservative_cleanup(1, 0))

    def test_signature_detects_name_type_and_feature_changes(self):
        devices = {42: {
            "name": "Presa Ext", "device_type": "automation_switch",
            "sstype": "SS_Automation_OnOff", "sfetypes": ["SFE_State_OnOff"],
        }}
        before = inventory.inventory_signature(devices)
        devices[42]["name"] = "Presa Esterna"
        self.assertNotEqual(before, inventory.inventory_signature(devices))
        devices[42]["name"] = "Presa Ext"
        self.assertEqual(before, inventory.inventory_signature(devices))
        devices[42]["device_type"] = "light"
        self.assertNotEqual(before, inventory.inventory_signature(devices))


if __name__ == "__main__":
    unittest.main()
