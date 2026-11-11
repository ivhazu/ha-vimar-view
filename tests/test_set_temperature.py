"""set_climate_temperature writes the setpoint of the active operating mode."""
import asyncio

from custom_components.vimar_cloud.api import VimarCloudClient
from custom_components.vimar_cloud.const import (
    CHANGE_OVER_COOLING,
    CHANGE_OVER_HEATING,
    HVAC_MODE_VIMAR_ABSENCE,
    HVAC_MODE_VIMAR_AUTO,
    HVAC_MODE_VIMAR_MANUAL,
    HVAC_MODE_VIMAR_PROTECTION,
    HVAC_MODE_VIMAR_REDUCTION,
    HVAC_MODE_VIMAR_TIMED_MANUAL,
    SFE_CMD_AMBIENT_SETPOINT,
    SFE_CMD_COOL_ABSENCE_SETPOINT,
    SFE_CMD_COOL_REDUCTION_SETPOINT,
    SFE_CMD_HEAT_ABSENCE_SETPOINT,
    SFE_CMD_HEAT_PROTECTION_SETPOINT,
    SFE_CMD_HEAT_REDUCTION_SETPOINT,
    SFE_CMD_HVAC_MODE,
    SFE_STATE_CHANGE_OVER_MODE,
    SFE_STATE_HVAC_MODE,
)

IDSF = 100


def make_client(mode: str, change_over: str = CHANGE_OVER_HEATING):
    client = VimarCloudClient("u", "p", "duid", "")
    client.device_states[IDSF] = {
        SFE_STATE_HVAC_MODE: mode,
        SFE_STATE_CHANGE_OVER_MODE: change_over,
    }
    sent: list[tuple[str, str]] = []

    async def record(args, timeout=None):
        sent.extend((a["sfetype"], a["value"]) for a in args)

    client._send_command = record
    return client, sent


def set_temperature(client, temp):
    asyncio.run(client.set_climate_temperature(IDSF, temp))


def test_manual_modes_write_the_ambient_setpoint():
    for mode in (HVAC_MODE_VIMAR_MANUAL, HVAC_MODE_VIMAR_TIMED_MANUAL):
        client, sent = make_client(mode)
        set_temperature(client, 21.5)
        assert sent == [(SFE_CMD_AMBIENT_SETPOINT, "21.5")], mode


def test_auto_switches_to_timed_manual_then_writes_the_ambient_setpoint():
    client, sent = make_client(HVAC_MODE_VIMAR_AUTO)
    set_temperature(client, 21.5)
    assert sent == [
        (SFE_CMD_HVAC_MODE, HVAC_MODE_VIMAR_TIMED_MANUAL),
        (SFE_CMD_AMBIENT_SETPOINT, "21.5"),
    ]


def test_heating_mode_setpoints_are_written_to_the_mode():
    for mode, sfe in (
        (HVAC_MODE_VIMAR_REDUCTION, SFE_CMD_HEAT_REDUCTION_SETPOINT),
        (HVAC_MODE_VIMAR_ABSENCE, SFE_CMD_HEAT_ABSENCE_SETPOINT),
        (HVAC_MODE_VIMAR_PROTECTION, SFE_CMD_HEAT_PROTECTION_SETPOINT),
    ):
        client, sent = make_client(mode, CHANGE_OVER_HEATING)
        set_temperature(client, 12)
        assert sent == [(sfe, "12")], mode


def test_cooling_mode_setpoints_are_written_to_the_cooling_mode():
    for mode, sfe in (
        (HVAC_MODE_VIMAR_REDUCTION, SFE_CMD_COOL_REDUCTION_SETPOINT),
        (HVAC_MODE_VIMAR_ABSENCE, SFE_CMD_COOL_ABSENCE_SETPOINT),
    ):
        client, sent = make_client(mode, CHANGE_OVER_COOLING)
        set_temperature(client, 28)
        assert sent == [(sfe, "28")], mode


def test_protection_has_no_cooling_setpoint_so_falls_back_to_ambient():
    client, sent = make_client(HVAC_MODE_VIMAR_PROTECTION, CHANGE_OVER_COOLING)
    set_temperature(client, 30)
    assert sent == [(SFE_CMD_AMBIENT_SETPOINT, "30")]
