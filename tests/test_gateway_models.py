"""Regression tests for filtering unsupported Vimar cloud associations."""
import importlib.util
from pathlib import Path
import unittest

MODULE_PATH = Path(__file__).resolve().parents[1] / "custom_components/vimar_cloud/gateway_models.py"
spec = importlib.util.spec_from_file_location("vimar_gateway_models", MODULE_PATH)
gateway_models = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gateway_models)


class GatewayModelTests(unittest.TestCase):
    def test_tab_5s_is_excluded_but_gateway_and_thermostat_remain(self):
        associations = [
            {"duid": " 000000aaa00001 ", "model": "BLEG"},
            {"duid": "000000AAA00002", "model": "STW"},
            {"duid": "000000AAA00003", "model": "VPTW5"},
        ]
        result = gateway_models.supported_gateways(associations)
        self.assertEqual(set(result), {"000000AAA00001", "000000AAA00002"})

    def test_model_name_is_normalized(self):
        result = gateway_models.supported_gateways(
            [{"duid": "000000AAA00003", "model": " vptw5 "}]
        )
        self.assertEqual(result, {})

    def test_unknown_models_remain_available(self):
        result = gateway_models.supported_gateways(
            [{"duid": "000000AAA00004", "model": "FUTURE_MODEL"}]
        )
        self.assertEqual(list(result), ["000000AAA00004"])

    def test_bad_associations_are_ignored(self):
        result = gateway_models.supported_gateways(
            [None, {}, {"duid": " "}, {"duid": None, "model": "BLEG"}]
        )
        self.assertEqual(result, {})


if __name__ == "__main__":
    unittest.main()
