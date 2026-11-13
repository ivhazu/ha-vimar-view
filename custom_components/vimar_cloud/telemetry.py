"""Telemetria energia (BigData) per gli impianti con piano MyVimar a pagamento.

La discovery con `sfcategory: "BigData"` restituisce le serie `SF_TelemetryEnergy`
(consumo, prelievo, immissione, produzione, autoconsumo). Il valore
`SFE_State_Telemetry_G` è un JSON `{"last_update": <epoch>, "data": [Wh, ...]}`
con i Wh ora per ora degli ultimi 7 giorni: `data[0]` è l'ora di `last_update`,
`data[1]` quella precedente e così via. Sul piano gratuito i valori sono vuoti
e i sensori non vengono creati.

Grazie a @afazio82-sudo per l'analisi (PR #15 / #17).
"""
from __future__ import annotations

import asyncio
from datetime import date, datetime, timedelta
import json
import logging
import math
from typing import Any, Callable

from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.util import dt as dt_util

from .api import VimarCloudClient

_LOGGER = logging.getLogger(__name__)

SFE_STATE_TELEMETRY_G = "SFE_State_Telemetry_G"  # orario, 168 valori
SFE_STATE_TELEMETRY_S = "SFE_State_Telemetry_S"  # giornaliero, 28 valori
SFE_STATE_TELEMETRY_M = "SFE_State_Telemetry_M"  # giornaliero, 366 valori
REFRESH_INTERVAL = timedelta(minutes=10)
BIGDATA_WAIT_SECONDS = 10

# sstype → nome del sensore giornaliero (kWh di oggi)
SERIES_NAMES = {
    "SS_EnergyConsumption_GL": "Consumo oggi",
    "SS_EnergyWithdrawal_GL": "Prelievo rete oggi",
    "SS_EnergyIntake_GL": "Immissione rete oggi",
    "SS_EnergyProduction_GL": "Produzione fotovoltaica oggi",
    "SS_EnergySelfConsumption_GL": "Autoconsumo oggi",
}

# sstype → nome base dei sensori di periodo ("Consumo settimana", ...)
SERIES_BASE_NAMES = {
    "SS_EnergyConsumption_GL": "Consumo",
    "SS_EnergyWithdrawal_GL": "Prelievo rete",
    "SS_EnergyIntake_GL": "Immissione rete",
    "SS_EnergyProduction_GL": "Produzione fotovoltaica",
    "SS_EnergySelfConsumption_GL": "Autoconsumo",
}

PERIOD_WEEK = "week"
PERIOD_MONTH = "month"
PERIOD_YEAR = "year"
PERIOD_SUFFIX = {PERIOD_WEEK: "settimana", PERIOD_MONTH: "mese", PERIOD_YEAR: "anno"}


def parse_telemetry(raw: Any) -> dict | None:
    """Decodifica il valore di SFE_State_Telemetry_G; None se vuoto o non valido."""
    if raw in (None, ""):
        return None
    try:
        obj = json.loads(raw) if isinstance(raw, str) else raw
    except (TypeError, ValueError):
        return None
    if not isinstance(obj, dict) or not isinstance(obj.get("data"), list):
        return None
    if not isinstance(obj.get("last_update"), (int, float)):
        return None
    return obj


def _last_update_local(telemetry: dict) -> datetime:
    last = float(telemetry["last_update"])
    if last > 1e11:  # millisecondi
        last /= 1000
    return dt_util.as_local(dt_util.utc_from_timestamp(last))


def _wh(value: Any) -> float | None:
    try:
        wh = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(wh) or wh < 0:
        return None
    return wh


def daily_values(telemetry: dict | None) -> dict[date, float]:
    """Wh per giorno da una serie giornaliera (S o M): data[i] = giorno di last_update − i.

    I giorni senza dati (null) valgono 0 Wh: Vimar li lascia vuoti quando non c'è stato
    consumo/produzione registrata.
    """
    if telemetry is None:
        return {}
    last_day = _last_update_local(telemetry).date()
    result: dict[date, float] = {}
    for index, value in enumerate(telemetry["data"]):
        wh = 0.0 if value is None else _wh(value)
        if wh is None:
            continue
        result[last_day - timedelta(days=index)] = wh
    return result


def hourly_day_wh(telemetry: dict | None, day: date) -> float | None:
    """Wh di un giorno già concluso dalla serie oraria (G), se la copre per intero."""
    if telemetry is None:
        return None
    last_hour = _last_update_local(telemetry).replace(minute=0, second=0, microsecond=0)
    data = telemetry["data"]
    oldest = last_hour - timedelta(hours=len(data) - 1)
    if (oldest.date(), oldest.hour) > (day, 0):
        return None  # la serie oraria non arriva all'inizio del giorno
    if (last_hour.date(), last_hour.hour) < (day, 23):
        return None  # il giorno non è ancora concluso nella serie
    total = 0.0
    for index, value in enumerate(data):
        slot = last_hour - timedelta(hours=index)
        if slot.date() < day:
            break
        if slot.date() != day or value is None:
            continue
        wh = _wh(value)
        if wh is None:
            return None
        total += wh
    return total


def period_start(today: date, period: str) -> date:
    if period == PERIOD_WEEK:
        return today - timedelta(days=today.weekday())  # lunedì
    if period == PERIOD_MONTH:
        return today.replace(day=1)
    return today.replace(month=1, day=1)


def period_kwh(
    hourly: dict | None, daily: dict[date, float], period: str, now: datetime
) -> float | None:
    """kWh dall'inizio del periodo: giorni conclusi dalla serie giornaliera + oggi dalla oraria.

    Così non si conta due volte il giorno in corso, che la serie giornaliera
    potrebbe già contenere in forma parziale. Un giorno concluso assente dalla
    serie giornaliera (aggiornamento in ritardo dopo mezzanotte) viene preso
    dalla serie oraria; se manca anche lì il valore è sconosciuto.
    """
    if hourly is None:
        return None
    today_kwh = daily_kwh(hourly, now)
    if today_kwh is None:
        return None
    today = now.date()
    total_wh = 0.0
    day = period_start(today, period)
    while day < today:
        wh = daily.get(day)
        if wh is None:
            wh = hourly_day_wh(hourly, day)
        if wh is None:
            return None
        total_wh += wh
        day += timedelta(days=1)
    return round(total_wh / 1000 + today_kwh, 3)


def daily_kwh(telemetry: dict, now: datetime) -> float | None:
    """kWh di oggi (ora locale di `now`) dalla serie oraria."""
    last_hour = _last_update_local(telemetry).replace(minute=0, second=0, microsecond=0)
    today = now.date()
    if last_hour.date() < today:
        # Nuovo giorno ma serie non ancora aggiornata: nella prima ora vale 0.
        return 0.0 if now.hour == 0 else None
    total = 0.0
    for index, value in enumerate(telemetry["data"]):
        slot = last_hour - timedelta(hours=index)
        if slot.date() != today:
            break
        if value is None:
            if index == 0:
                continue  # ora in corso non ancora consolidata
            return None  # buco nei dati: meglio "sconosciuto" che un totale sbagliato
        wh = _wh(value)
        if wh is None:
            return None
        total += wh
    return round(total / 1000, 3)


class TelemetryManager:
    """Individua le serie di telemetria e le aggiorna ogni 10 minuti."""

    def __init__(self, hass: HomeAssistant, client: VimarCloudClient) -> None:
        self.hass = hass
        self.client = client
        self.series: dict[str, int] = {}  # sstype → idsf (solo serie con dati)
        self.periods: dict[int, list[str]] = {}  # idsf → periodi disponibili
        self._listeners: list[Callable[[], None]] = []
        self._unsub: list[Callable[[], None]] = []

    async def async_start(self) -> None:
        try:
            await asyncio.wait_for(self.client.bigdata_received.wait(), BIGDATA_WAIT_SECONDS)
        except asyncio.TimeoutError:
            _LOGGER.debug("Vimar: no BigData discovery received")
            return
        candidates = {
            sf["sstype"]: sf["idsf"]
            for sf in self.client.bigdata_sfs
            if sf.get("sftype") == "SF_TelemetryEnergy" and sf.get("sstype") in SERIES_NAMES
        }
        if not candidates:
            return
        await self._async_fetch(candidates.values())
        self.series = {
            sstype: idsf for sstype, idsf in candidates.items()
            if parse_telemetry(self.client.get_state(idsf, SFE_STATE_TELEMETRY_G)) is not None
        }
        for idsf in self.series.values():
            has_s = self._daily_raw(idsf, SFE_STATE_TELEMETRY_S) is not None
            has_m = self._daily_raw(idsf, SFE_STATE_TELEMETRY_M) is not None
            periods = []
            if has_s or has_m:
                periods.append(PERIOD_WEEK)
            if has_m:
                periods += [PERIOD_MONTH, PERIOD_YEAR]
            self.periods[idsf] = periods
        _LOGGER.debug("Vimar: telemetry series with data: %s, periods: %s", self.series, self.periods)
        if self.series:
            self._unsub.append(
                async_track_time_interval(self.hass, self._async_refresh, REFRESH_INTERVAL)
            )

    @callback
    def async_stop(self) -> None:
        for unsub in self._unsub:
            unsub()
        self._unsub.clear()

    def add_listener(self, listener: Callable[[], None]) -> Callable[[], None]:
        self._listeners.append(listener)
        return lambda: self._listeners.remove(listener)

    async def _async_fetch(self, idsfs) -> None:
        items = [
            {"idsf": idsf, "sfetype": [SFE_STATE_TELEMETRY_G, SFE_STATE_TELEMETRY_S, SFE_STATE_TELEMETRY_M]}
            for idsf in idsfs
        ]
        try:
            await self.client.request_status(items)
        except Exception as err:  # noqa: BLE001
            _LOGGER.debug("Vimar: telemetry request failed: %s", err)

    async def _async_refresh(self, _now: datetime) -> None:
        await self._async_fetch(self.series.values())
        for listener in tuple(self._listeners):
            listener()

    def value(self, idsf: int) -> float | None:
        telemetry = parse_telemetry(self.client.get_state(idsf, SFE_STATE_TELEMETRY_G))
        if telemetry is None:
            return None
        return daily_kwh(telemetry, dt_util.now())

    def _daily_raw(self, idsf: int, sfetype: str) -> dict | None:
        telemetry = parse_telemetry(self.client.get_state(idsf, sfetype))
        if telemetry is None or not any(v is not None for v in telemetry["data"]):
            return None
        return telemetry

    def period_value(self, idsf: int, period: str) -> float | None:
        hourly = parse_telemetry(self.client.get_state(idsf, SFE_STATE_TELEMETRY_G))
        daily = daily_values(self._daily_raw(idsf, SFE_STATE_TELEMETRY_M))
        daily.update(daily_values(self._daily_raw(idsf, SFE_STATE_TELEMETRY_S)))
        return period_kwh(hourly, daily, period, dt_util.now())
