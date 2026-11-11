"""Climate presets ↔ Vimar HVAC modes (Reduction / Absence / Protection)."""
import asyncio
from types import SimpleNamespace

from homeassistant.components.climate import HVACAction, HVACMode

from custom_components.vimar_cloud import climate
from custom_components.vimar_cloud.const import (
    CHANGE_OVER_HEATING,
    HVAC_MODE_VIMAR_ABSENCE,
    HVAC_MODE_VIMAR_AUTO,
    HVAC_MODE_VIMAR_MANUAL,
    HVAC_MODE_VIMAR_OFF,
    HVAC_MODE_VIMAR_PROTECTION,
    HVAC_MODE_VIMAR_REDUCTION,
    HVAC_MODE_VIMAR_TIMED_MANUAL,
    OUT_STATUS_HEAT,
    SFE_CMD_HVAC_MODE,
    SFE_STATE_CHANGE_OVER_MODE,
    SFE_STATE_HVAC_MODE,
    SFE_STATE_OUT_STATUS,
)

IDSF = 42


class FakeClient:
    """Minimal stand-in for VimarCloudClient: state dict + recorded commands."""

    def __init__(self, hvac_mode: str) -> None:
        self.devices = {IDSF: {"name": "Camera", "device_type": "thermostat"}}
        self.states = {
            SFE_STATE_HVAC_MODE: hvac_mode,
            SFE_STATE_CHANGE_OVER_MODE: CHANGE_OVER_HEATING,
            SFE_STATE_OUT_STATUS: OUT_STATUS_HEAT,
        }
        self.sent: list[tuple[str, str]] = []

    def get_state(self, idsf, sfetype):
        assert idsf == IDSF
        return self.states.get(sfetype)

    async def set_climate_hvac_mode(self, idsf, vimar_mode):
        self.sent.append((SFE_CMD_HVAC_MODE, vimar_mode))

    async def set_climate_change_over(self, idsf, change_over):
        self.sent.append(("SFE_Cmd_ChangeOverMode", change_over))


def make_entity(hvac_mode: str):
    client = FakeClient(hvac_mode)
    entry = SimpleNamespace(entry_id="entry")
    entity = climate.VimarClimate.__new__(climate.VimarClimate)
    entity._client = client
    entity._idsf = IDSF
    return entity, client


def test_all_six_vimar_modes_are_offered_as_presets():
    assert climate.PRESET_MODES == [
        "Programma", "Manuale", "Permanente", "Riduzione", "Assenza", "Protezione",
    ]


def test_preset_reflects_reduction_absence_protection():
    for vimar_mode, preset in (
        (HVAC_MODE_VIMAR_REDUCTION, "Riduzione"),
        (HVAC_MODE_VIMAR_ABSENCE, "Assenza"),
        (HVAC_MODE_VIMAR_PROTECTION, "Protezione"),
        (HVAC_MODE_VIMAR_AUTO, "Programma"),
        (HVAC_MODE_VIMAR_TIMED_MANUAL, "Manuale"),
        (HVAC_MODE_VIMAR_MANUAL, "Permanente"),
    ):
        entity, _ = make_entity(vimar_mode)
        assert entity.preset_mode == preset, vimar_mode


def test_unknown_vimar_mode_has_no_preset():
    entity, _ = make_entity("Something new")
    assert entity.preset_mode is None


def test_off_mode_has_no_preset():
    entity, _ = make_entity(HVAC_MODE_VIMAR_OFF)
    assert entity.preset_mode is None
    assert entity.hvac_mode == HVACMode.OFF
    assert entity.hvac_action == HVACAction.OFF


def test_protection_mode_is_still_heating():
    entity, _ = make_entity(HVAC_MODE_VIMAR_PROTECTION)
    assert entity.hvac_mode == HVACMode.HEAT
    assert entity.hvac_action == HVACAction.HEATING


def test_selecting_new_presets_sends_the_vimar_mode():
    for preset, vimar_mode in (
        ("Riduzione", HVAC_MODE_VIMAR_REDUCTION),
        ("Assenza", HVAC_MODE_VIMAR_ABSENCE),
        ("Protezione", HVAC_MODE_VIMAR_PROTECTION),
    ):
        entity, client = make_entity(HVAC_MODE_VIMAR_AUTO)
        asyncio.run(entity.async_set_preset_mode(preset))
        assert client.sent == [(SFE_CMD_HVAC_MODE, vimar_mode)], preset


def test_selecting_a_preset_while_off_only_sends_the_mode():
    """The season (ChangeOverMode) is left untouched: Assenza works in summer too."""
    entity, client = make_entity(HVAC_MODE_VIMAR_OFF)
    asyncio.run(entity.async_set_preset_mode("Assenza"))
    assert client.sent == [(SFE_CMD_HVAC_MODE, HVAC_MODE_VIMAR_ABSENCE)]
