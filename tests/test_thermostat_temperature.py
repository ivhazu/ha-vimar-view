"""Issue #18: la temperatura ambiente del termostato è anche un sensore."""
import asyncio
from types import SimpleNamespace

from custom_components.vimar_cloud import sensor
from custom_components.vimar_cloud.api import VimarCloudClient
from custom_components.vimar_cloud.const import DOMAIN, SFE_STATE_AMBIENT_TEMPERATURE

T = 12345


def _setup(value):
    client = VimarCloudClient("u", "p", "duid", "")
    client.devices[T] = {"idsf": T, "name": "Soggiorno", "device_type": "thermostat",
                         "sfetypes": [SFE_STATE_AMBIENT_TEMPERATURE], "sstype": "SS_Clima_Zone"}
    client.device_states[T] = {SFE_STATE_AMBIENT_TEMPERATURE: value}
    hass = SimpleNamespace(data={DOMAIN: {"e1": client}})
    added = []
    asyncio.run(sensor.async_setup_entry(hass, SimpleNamespace(entry_id="e1"), lambda e: added.extend(e)))
    return [e for e in added if isinstance(e, sensor.VimarThermostatTemperatureSensor)]


def test_temperature_sensor_created_with_value():
    (ent,) = _setup("19.3")
    assert ent.native_value == 19.3
    assert ent._attr_unique_id == "e1_12345_temperature"
    assert ent._attr_name == "Temperatura"


def test_invalid_value_is_unknown():
    (ent,) = _setup("n/a")
    assert ent.native_value is None
