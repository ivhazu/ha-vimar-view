"""PV / grid power sensors are created only when the energy meter exposes them."""
import asyncio
from types import SimpleNamespace

from custom_components.vimar_cloud import sensor
from custom_components.vimar_cloud.api import VimarCloudClient
from custom_components.vimar_cloud.const import (
    DOMAIN,
    SFE_STATE_GLOBAL_ACTIVE_EXCHANGE,
    SFE_STATE_GLOBAL_ACTIVE_POWER,
    SFE_STATE_GLOBAL_ACTIVE_PRODUCTION,
)

EM = 175128


def _setup(sfetypes, states=None):
    client = VimarCloudClient("u", "p", "duid", "")
    client.idsf_energy_manager = EM
    client.devices[EM] = {"idsf": EM, "name": "Energia", "device_type": "energy_manager",
                          "sfetypes": sfetypes, "sstype": "SS_Energy_LoadControl1P"}
    client.device_states[EM] = states or {}
    entry = SimpleNamespace(entry_id="e1")
    hass = SimpleNamespace(data={DOMAIN: {"e1": client}})
    added = []
    asyncio.run(sensor.async_setup_entry(hass, entry, lambda ents: added.extend(ents)))
    return {e._attr_name: e for e in added}


def test_consumption_only_meter_has_no_pv_sensors():
    names = _setup([SFE_STATE_GLOBAL_ACTIVE_POWER])
    assert "Scambio Rete" not in names
    assert "Produzione Fotovoltaica" not in names
    assert "Consumo Totale" in names


def test_pv_meter_gets_grid_and_production_sensors():
    names = _setup(
        [SFE_STATE_GLOBAL_ACTIVE_POWER, SFE_STATE_GLOBAL_ACTIVE_EXCHANGE, SFE_STATE_GLOBAL_ACTIVE_PRODUCTION],
        {SFE_STATE_GLOBAL_ACTIVE_POWER: "620", SFE_STATE_GLOBAL_ACTIVE_EXCHANGE: "-350",
         SFE_STATE_GLOBAL_ACTIVE_PRODUCTION: "970"},
    )
    assert names["Consumo Totale"].native_value == 620.0
    assert names["Scambio Rete"].native_value == -350.0  # negativo = immissione
    assert names["Produzione Fotovoltaica"].native_value == 970.0
    # unique_id compatibili con la PR #15
    assert names["Scambio Rete"].unique_id == f"{DOMAIN}_{EM}_grid_power"
    assert names["Produzione Fotovoltaica"].unique_id == f"{DOMAIN}_{EM}_solar_power"
