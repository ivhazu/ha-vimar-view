"""Rilevamento (dedotto) delle esecuzioni delle routine."""
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

from custom_components.vimar_cloud import routines as r
from custom_components.vimar_cloud.api import VimarCloudClient

DUID = "000000AAA00001"
L1, L2 = 1001, 1002
UTC = timezone.utc
# Venerdì 13/11/2026 (isoweekday 5)
FRI = datetime(2026, 11, 13, tzinfo=UTC)


def test_parse_schedules_and_expected():
    trig = [["schedule", 30, 22, [5, 1], 0, None, None, False], ["other"]]
    s = r.parse_schedules(trig)
    assert len(s) == 1 and s[0].offset == timedelta(hours=22, minutes=30) and s[0].weekdays == [5, 1]
    actions = [[0, [DUID, "sfm", [L1, "SFE_Cmd_OnOff", "On"], [L2, "SFE_Cmd_Brightness", 50]]],
               [200, [DUID, "sfm", [L1, "SFE_Cmd_OnOff", "Off"]]],
               [0, ["OTHERDUID", "sfm", [9, "SFE_Cmd_OnOff", "On"]]]]
    assert r.parse_expected(actions, DUID) == {
        (L1, "SFE_State_OnOff"): "On", (L2, "SFE_State_Brightness"): "50"}


def _tracker(trigger, active=True):
    hass = MagicMock()
    client = VimarCloudClient("u", "p", DUID, "plant")
    for idsf in (L1, L2):
        client.device_states[idsf] = {"SFE_State_OnOff": "Off"}
    t = r.RoutineTracker(hass, client, DUID)
    t.routines = {"R": r.RoutineInfo(
        "R", "Luci", active, r.parse_schedules([trigger]),
        {(L1, "SFE_State_OnOff"): "On", (L2, "SFE_State_OnOff"): "On"})}
    t._sun_time = lambda event, day: datetime(day.year, day.month, day.day, 17, 0, tzinfo=UTC)
    t._snapshot_states()
    return t, client, hass


def _turn_on(t, client, when):
    for idsf in (L1, L2):
        client.device_states[idsf]["SFE_State_OnOff"] = "On"
    with_now = lambda: when  # noqa: E731
    orig = r.dt_util.now
    r.dt_util.now = with_now
    try:
        t._on_states([L1, L2])
    finally:
        r.dt_util.now = orig


def test_clock_routine_detected_once():
    t, client, hass = _tracker(["schedule", 30, 22, [5], 0])
    _turn_on(t, client, FRI.replace(hour=22, minute=30, second=20))
    hass.bus.async_fire.assert_called_once()
    event, data = hass.bus.async_fire.call_args.args
    assert event == r.EVENT_ROUTINE_EXECUTED and data["name"] == "Luci" and data["source"] == "schedule"
    t.check(FRI.replace(hour=22, minute=31))  # nessun doppione
    assert hass.bus.async_fire.call_count == 1


def test_outside_window_or_other_day_is_ignored():
    t, client, hass = _tracker(["schedule", 30, 22, [5], 0])
    _turn_on(t, client, FRI.replace(hour=20, minute=0))
    hass.bus.async_fire.assert_not_called()
    t, client, hass = _tracker(["schedule", 30, 22, [1], 0])  # solo lunedì
    _turn_on(t, client, FRI.replace(hour=22, minute=30, second=10))
    hass.bus.async_fire.assert_not_called()


def test_inactive_routine_is_ignored():
    t, client, hass = _tracker(["schedule", 30, 22, [5], 0], active=False)
    _turn_on(t, client, FRI.replace(hour=22, minute=30, second=10))
    hass.bus.async_fire.assert_not_called()


def test_sunset_with_offset_uses_wider_window():
    t, client, hass = _tracker(["schedule", 30, 0, [5], r.TIME_REF_SUNSET])  # tramonto 17:00 + 30'
    _turn_on(t, client, FRI.replace(hour=17, minute=40))
    hass.bus.async_fire.assert_called_once()


def test_manual_execution_from_home_assistant():
    t, client, hass = _tracker(["schedule", 30, 22, [5], 0])
    t.mark_executed("R", r.SOURCE_HOME_ASSISTANT, FRI.replace(hour=12))
    assert hass.bus.async_fire.call_args.args[1]["source"] == "home_assistant"
    assert t.last_run["R"] == FRI.replace(hour=12)
