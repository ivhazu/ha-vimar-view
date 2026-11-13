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


# ─── Sensori di periodo (settimana / mese / anno) ───────────────────────────
# NOW = venerdì 13/11/2026 14:25 → settimana da lunedì 9, mese dall'1, anno dall'1/1.

def _daily_raw(last_day, data):
    ts = datetime(2026, 11, last_day, 0, 0, tzinfo=UTC).timestamp()
    return t.parse_telemetry(json.dumps({"last_update": int(ts), "data": data}))


def _hourly_today():
    return t.parse_telemetry(_raw(14, [100.0] * 15))  # oggi = 1.5 kWh


def test_period_start():
    today = NOW.date()
    assert t.period_start(today, t.PERIOD_WEEK).isoformat() == "2026-11-09"
    assert t.period_start(today, t.PERIOD_MONTH).isoformat() == "2026-11-01"
    assert t.period_start(today, t.PERIOD_YEAR).isoformat() == "2026-01-01"


def test_week_uses_completed_days_plus_today_without_double_count():
    # serie giornaliera aggiornata a oggi (slot 0 = oggi parziale, da ignorare)
    daily = t.daily_values(_daily_raw(13, [777.0, 1000.0, 2000.0, 3000.0, 4000.0, 9999.0]))
    # lun 9..gio 12 = 4+3+2+1 kWh, oggi 1.5 dalla serie oraria
    assert t.period_kwh(_hourly_today(), daily, t.PERIOD_WEEK, NOW) == 11.5


def test_daily_series_ending_yesterday():
    daily = t.daily_values(_daily_raw(12, [1000.0, 2000.0, 3000.0, 4000.0]))
    assert t.period_kwh(_hourly_today(), daily, t.PERIOD_WEEK, NOW) == 11.5


def test_null_days_count_as_zero():
    daily = t.daily_values(_daily_raw(12, [1000.0, None, None, 4000.0]))
    assert t.period_kwh(_hourly_today(), daily, t.PERIOD_WEEK, NOW) == 6.5


def test_missing_day_falls_back_to_hourly_or_unknown():
    # giornaliera ferma a mercoledì 11: giovedì 12 va preso dalla serie oraria
    daily = t.daily_values(_daily_raw(11, [2000.0, 3000.0, 4000.0]))
    hourly = t.parse_telemetry(_raw(14, [100.0] * 15 + [50.0] * 24))  # ieri 1.2 kWh
    assert t.period_kwh(hourly, daily, t.PERIOD_WEEK, NOW) == 11.7
    # la serie oraria non copre tutto ieri → sconosciuto
    assert t.period_kwh(_hourly_today(), daily, t.PERIOD_WEEK, NOW) is None


def test_month_and_year_need_full_coverage():
    daily = t.daily_values(_daily_raw(12, [1000.0] * 12))  # 1..12 novembre
    assert t.period_kwh(_hourly_today(), daily, t.PERIOD_MONTH, NOW) == 13.5
    assert t.period_kwh(_hourly_today(), daily, t.PERIOD_YEAR, NOW) is None
    year = t.daily_values(_daily_raw(12, [1000.0] * 316))  # 1/1..12/11
    assert t.period_kwh(_hourly_today(), year, t.PERIOD_YEAR, NOW) == 317.5


def test_manager_detects_periods(monkeypatch):
    monkeypatch.setattr(t, "async_track_time_interval", lambda *a: (lambda: None))
    states = {
        (90000, t.SFE_STATE_TELEMETRY_G): _raw(14, [100.0] * 15),
        (90000, t.SFE_STATE_TELEMETRY_S): json.dumps({"last_update": 1, "data": [1.0]}),
        (90000, t.SFE_STATE_TELEMETRY_M): json.dumps({"last_update": 1, "data": [None, None]}),
        (90001, t.SFE_STATE_TELEMETRY_G): _raw(14, [100.0]),
        (90001, t.SFE_STATE_TELEMETRY_M): json.dumps({"last_update": 1, "data": [1.0]}),
    }
    client = SimpleNamespace(
        bigdata_received=asyncio.Event(),
        bigdata_sfs=[
            {"idsf": 90000, "sftype": "SF_TelemetryEnergy", "sstype": "SS_EnergyConsumption_GL"},
            {"idsf": 90001, "sftype": "SF_TelemetryEnergy", "sstype": "SS_EnergyProduction_GL"},
        ],
        request_status=AsyncMock(),
        get_state=lambda idsf, sfe: states.get((idsf, sfe)),
    )
    client.bigdata_received.set()
    m = t.TelemetryManager(MagicMock(), client)
    asyncio.run(m.async_start())
    assert m.periods == {90000: ["week"], 90001: ["week", "month", "year"]}
    sent = client.request_status.await_args.args[0]
    assert sent[0]["sfetype"] == ["SFE_State_Telemetry_G", "SFE_State_Telemetry_S", "SFE_State_Telemetry_M"]
