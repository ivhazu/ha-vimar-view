"""Telemetria energia BigData: formato {"last_update", "data"} e kWh di oggi."""
import asyncio
from datetime import datetime, timezone
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

from homeassistant.util import dt as dt_util

from custom_components.vimar_cloud import telemetry as t

UTC = timezone.utc
NOW = datetime(2026, 11, 13, 14, 25, tzinfo=UTC)  # 14:25 (fuso di default nei test: UTC)


def _raw(last_hour, data, ms=False):
    ts = datetime(2026, 11, 13, last_hour, 0, tzinfo=UTC).timestamp()
    return json.dumps({"last_update": int(ts * 1000 if ms else ts), "data": data})


def test_parse_telemetry():
    assert t.parse_telemetry("") is None
    assert t.parse_telemetry("not json") is None
    assert t.parse_telemetry('{"data": []}') is None
    assert t.parse_telemetry(_raw(14, [1]))["data"] == [1]


def test_daily_sum_only_today():
    # ore 14..0 di oggi = 15 valori da 100 Wh, poi ore di ieri da ignorare
    data = [100.0] * 15 + [999.0] * 10
    assert t.daily_kwh(t.parse_telemetry(_raw(14, data)), NOW) == 1.5
    assert t.daily_kwh(t.parse_telemetry(_raw(14, data, ms=True)), NOW) == 1.5


def test_current_hour_null_is_ignored_older_gap_is_unknown():
    assert t.daily_kwh(t.parse_telemetry(_raw(14, [None] + [100.0] * 14)), NOW) == 1.4
    assert t.daily_kwh(t.parse_telemetry(_raw(14, [100.0, None] + [100.0] * 13)), NOW) is None


def test_new_day_before_update():
    yesterday = json.dumps({"last_update": int(datetime(2026, 11, 12, 23, tzinfo=UTC).timestamp()), "data": [5.0]})
    tel = t.parse_telemetry(yesterday)
    assert t.daily_kwh(tel, datetime(2026, 11, 13, 0, 20, tzinfo=UTC)) == 0.0
    assert t.daily_kwh(tel, datetime(2026, 11, 13, 3, 0, tzinfo=UTC)) is None


def _manager(bigdata, states):
    client = SimpleNamespace(
        bigdata_received=asyncio.Event(),
        bigdata_sfs=bigdata,
        request_status=AsyncMock(),
        get_state=lambda idsf, sfe: states.get(idsf),
    )
    client.bigdata_received.set()
    hass = MagicMock()
    return t.TelemetryManager(hass, client), client


def test_only_series_with_data_are_kept(monkeypatch):
    monkeypatch.setattr(t, "async_track_time_interval", lambda *a: (lambda: None))
    bigdata = [
        {"idsf": 90004, "sftype": "SF_TelemetryEnergy", "sstype": "SS_EnergyWithdrawal_GL"},
        {"idsf": 90002, "sftype": "SF_TelemetryEnergy", "sstype": "SS_EnergyProduction_GL"},
        {"idsf": 90009, "sftype": "SF_TelemetryEnergy", "sstype": "SS_Unknown"},
    ]
    m, client = _manager(bigdata, {90004: _raw(14, [100.0]), 90002: ""})
    asyncio.run(m.async_start())
    assert m.series == {"SS_EnergyWithdrawal_GL": 90004}
    sent = client.request_status.await_args.args[0]
    assert {i["idsf"] for i in sent} == {90004, 90002}


def test_free_plan_creates_nothing():
    m, _ = _manager([{"idsf": 90000, "sftype": "SF_TelemetryEnergy", "sstype": "SS_EnergyConsumption_GL"}], {90000: ""})
    asyncio.run(m.async_start())
    assert m.series == {}


def test_bigdata_discovery_is_stored():
    from custom_components.vimar_cloud.api import VimarCloudClient
    client = VimarCloudClient("u", "p", "duid", "")
    result = [{"idsf": 90004, "sftype": "SF_TelemetryEnergy", "sstype": "SS_EnergyWithdrawal_GL", "elements": []}]
    asyncio.run(client._handle_response("sfdiscovery", {"msgid": "1", "result": result}))
    assert client.bigdata_received.is_set()
    assert client.bigdata_sfs[0]["idsf"] == 90004
