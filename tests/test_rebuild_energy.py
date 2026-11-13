"""Ricalcolo dello storico energia dalla potenza (issue #10)."""
from datetime import datetime, timedelta, timezone

from custom_components.vimar_cloud import services as s

UTC = timezone.utc
H0 = datetime(2026, 10, 16, 0, tzinfo=UTC)


def test_power_unique_id_mapping():
    assert s.power_unique_id("vimar_cloud_9153544_kwh") == "vimar_cloud_9153544_power"
    assert s.power_unique_id("vimar_cloud_175128_total_kwh") == "vimar_cloud_175128_total_power"
    assert s.power_unique_id("vimar_cloud_e1_42_automation_kwh") == "vimar_cloud_e1_42_automation_power"
    assert s.power_unique_id("vimar_cloud_e1_90004_daily_energy") is None


def test_compute_rows_from_hourly_mean_power():
    hourly = {H0: 1000.0, H0 + timedelta(hours=1): 500.0, H0 + timedelta(hours=3): 2000.0}
    rows = s.compute_rows(hourly, H0, H0 + timedelta(hours=4), base_sum=10.0, base_state=3.0)
    assert [r["start"] for r in rows] == [H0 + timedelta(hours=i) for i in range(4)]
    assert [r["sum"] for r in rows] == [11.0, 11.5, 11.5, 13.5]  # ora 2 senza dati = 0
    assert rows[-1]["state"] == 6.5


def test_negative_or_missing_power_adds_nothing():
    rows = s.compute_rows({H0: -50.0}, H0, H0 + timedelta(hours=2), 0.0, 0.0)
    assert [r["sum"] for r in rows] == [0.0, 0.0]


def test_floor_hour_and_row_start():
    assert s.floor_hour(datetime(2026, 10, 16, 5, 42, 10, tzinfo=UTC)) == H0 + timedelta(hours=5)
    assert s._row_start({"start": H0.timestamp()}) == H0
