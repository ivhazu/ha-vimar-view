"""Servizi dell'integrazione.

`vimar_cloud.rebuild_energy_history` ricalcola lo storico a lungo termine (le
statistiche orarie usate dalla dashboard Energia) di un sensore kWh
dell'integrazione partendo dallo storico della potenza corrispondente: per ogni
ora, kWh = potenza media dell'ora (W) / 1000. Utile se lo storico dell'energia è
stato rovinato da un bug, mentre quello della potenza è corretto (issue #10).
"""
from __future__ import annotations

from datetime import datetime, timedelta
import logging
from typing import Any

import voluptuous as vol

from homeassistant.core import HomeAssistant, ServiceCall, ServiceResponse, SupportsResponse
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import config_validation as cv, entity_registry as er
from homeassistant.util import dt as dt_util

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

SERVICE_REBUILD_ENERGY_HISTORY = "rebuild_energy_history"
ATTR_START = "start"
ATTR_END = "end"

REBUILD_SCHEMA = vol.Schema({
    vol.Required("entity_id"): cv.entity_id,
    vol.Required(ATTR_START): cv.datetime,
    vol.Optional(ATTR_END): cv.datetime,
})

# unique_id del sensore kWh → unique_id del sensore di potenza da cui è calcolato
_ENERGY_TO_POWER_SUFFIX = (
    ("_total_kwh", "_total_power"),
    ("_automation_kwh", "_automation_power"),
    ("_kwh", "_power"),
)


def power_unique_id(energy_unique_id: str) -> str | None:
    for energy_suffix, power_suffix in _ENERGY_TO_POWER_SUFFIX:
        if energy_unique_id.endswith(energy_suffix):
            return energy_unique_id[: -len(energy_suffix)] + power_suffix
    return None


def _row_start(row: dict) -> datetime:
    start = row["start"]
    if isinstance(start, (int, float)):
        return dt_util.utc_from_timestamp(start)
    return dt_util.as_utc(start)


def floor_hour(when: datetime) -> datetime:
    return dt_util.as_utc(when).replace(minute=0, second=0, microsecond=0)


def compute_rows(
    hourly_mean_w: dict[datetime, float | None],
    start: datetime,
    end: datetime,
    base_sum: float,
    base_state: float,
) -> list[dict]:
    """Righe orarie {start, state, sum} da `start` (incluso) a `end` (escluso)."""
    rows: list[dict] = []
    total = 0.0
    hour = start
    while hour < end:
        mean = hourly_mean_w.get(hour)
        if mean is not None and mean > 0:
            total += mean / 1000.0  # W medi su un'ora → kWh
        rows.append({
            "start": hour,
            "state": round(base_state + total, 4),
            "sum": round(base_sum + total, 4),
        })
        hour += timedelta(hours=1)
    return rows


async def _async_rebuild(hass: HomeAssistant, call: ServiceCall) -> ServiceResponse:
    from homeassistant.components.recorder import get_instance
    from homeassistant.components.recorder.statistics import (
        async_import_statistics,
        get_metadata,
        statistics_during_period,
    )

    energy_id: str = call.data["entity_id"]
    registry = er.async_get(hass)
    energy_entry = registry.async_get(energy_id)
    if energy_entry is None or energy_entry.platform != DOMAIN:
        raise ServiceValidationError(f"{energy_id} is not a Vimar View Cloud sensor")
    power_uid = power_unique_id(energy_entry.unique_id or "")
    power_id = registry.async_get_entity_id("sensor", DOMAIN, power_uid) if power_uid else None
    if power_id is None:
        raise ServiceValidationError(f"{energy_id} is not an energy (kWh) sensor computed from power")

    now_hour = floor_hour(dt_util.utcnow())
    start = floor_hour(call.data[ATTR_START])
    end = min(floor_hour(call.data.get(ATTR_END) or now_hour), now_hour)
    if start >= end:
        raise ServiceValidationError("The start must be at least one full hour in the past")

    instance = get_instance(hass)

    def _read() -> tuple[dict, dict, dict]:
        meta = get_metadata(hass, statistic_ids={energy_id})
        power = statistics_during_period(hass, start, end, {power_id}, "hour", None, {"mean"})
        before = statistics_during_period(
            hass, start - timedelta(days=31), start, {energy_id}, "hour", None, {"sum", "state"}
        )
        at_end = statistics_during_period(
            hass, end - timedelta(hours=1), end, {energy_id}, "hour", None, {"sum"}
        )
        return meta, power, {"before": before.get(energy_id, []), "end": at_end.get(energy_id, [])}

    meta, power, energy = await instance.async_add_executor_job(_read)
    if energy_id not in meta:
        raise ServiceValidationError(f"{energy_id} has no long-term statistics yet")
    metadata = dict(meta[energy_id][1])

    hourly = {_row_start(r): r.get("mean") for r in power.get(power_id, [])}
    last_before = energy["before"][-1] if energy["before"] else {}
    base_sum = float(last_before.get("sum") or 0.0)
    base_state = float(last_before.get("state") or 0.0)
    rows = compute_rows(hourly, start, end, base_sum, base_state)

    async_import_statistics(hass, metadata, rows)

    # Le ore successive a `end` restano come sono, spostate dello stesso delta,
    # così il grafico non mostra salti al confine.
    old_end_sum = energy["end"][-1].get("sum") if energy["end"] else None
    delta = round(rows[-1]["sum"] - float(old_end_sum), 4) if old_end_sum is not None else 0.0
    if delta:
        instance.async_adjust_statistics(energy_id, end, delta, metadata.get("unit_of_measurement") or "kWh")

    rebuilt_kwh = round(rows[-1]["sum"] - base_sum, 3)
    _LOGGER.info(
        "Vimar: rebuilt %s from %s, %d hours, %.3f kWh (adjustment after end: %+.3f kWh)",
        energy_id, power_id, len(rows), rebuilt_kwh, delta,
    )
    return {
        "entity_id": energy_id,
        "power_entity_id": power_id,
        "hours": len(rows),
        "hours_without_power_data": sum(1 for r in rows if hourly.get(r["start"]) is None),
        "energy_kwh": rebuilt_kwh,
        "adjustment_after_end_kwh": delta,
    }


def async_register_services(hass: HomeAssistant) -> None:
    if hass.services.has_service(DOMAIN, SERVICE_REBUILD_ENERGY_HISTORY):
        return

    async def _handler(call: ServiceCall) -> ServiceResponse:
        return await _async_rebuild(hass, call)

    hass.services.async_register(
        DOMAIN,
        SERVICE_REBUILD_ENERGY_HISTORY,
        _handler,
        schema=REBUILD_SCHEMA,
        supports_response=SupportsResponse.OPTIONAL,
    )
