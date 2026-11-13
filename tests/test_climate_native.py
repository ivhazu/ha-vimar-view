"""Climate temperatures use the native_* API (HA 2026.11+) with a fallback for older HA."""
from homeassistant.components.climate import ClimateEntity
from homeassistant.const import UnitOfTemperature

from custom_components.vimar_cloud import climate
from custom_components.vimar_cloud.const import (
    SFE_STATE_AMBIENT_SETPOINT,
    SFE_STATE_AMBIENT_TEMPERATURE,
)


class FakeClient:
    def __init__(self, states):
        self.states = states

    def get_state(self, idsf, sfetype):
        return self.states.get(sfetype)


def _entity(states):
    ent = climate.VimarClimate.__new__(climate.VimarClimate)
    ent._client = FakeClient(states)
    ent._idsf = 1
    return ent


def test_native_values():
    ent = _entity({SFE_STATE_AMBIENT_TEMPERATURE: "20.5", SFE_STATE_AMBIENT_SETPOINT: "21"})
    assert ent.native_current_temperature == 20.5
    assert ent.native_target_temperature == 21.0
    assert climate.VimarClimate._attr_native_temperature_unit == UnitOfTemperature.CELSIUS


def test_invalid_values_are_none():
    ent = _entity({SFE_STATE_AMBIENT_TEMPERATURE: "n/a"})
    assert ent.native_current_temperature is None
    assert ent.native_target_temperature is None


def test_old_names_only_defined_on_old_home_assistant():
    has_native = hasattr(ClimateEntity, "native_current_temperature")
    defines_old = "current_temperature" in vars(climate.VimarClimate)
    assert defines_old is not has_native
    if defines_old:
        ent = _entity({SFE_STATE_AMBIENT_TEMPERATURE: "19", SFE_STATE_AMBIENT_SETPOINT: "22"})
        assert ent.current_temperature == 19.0
        assert ent.target_temperature == 22.0
