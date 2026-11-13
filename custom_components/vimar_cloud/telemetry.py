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
from datetime import datetime, timedelta
import json
import logging
import math
from typing import Any, Callable

from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.util import dt as dt_util

from .api import VimarCloudClient

_LOGGER = logging.getLogger(__name__)

SFE_STATE_TELEMETRY_G = "SFE_State_Telemetry_G"
REFRESH_INTERVAL = timedelta(minutes=10)
BIGDATA_WAIT_SECONDS = 10

# sstype → nome del sensore giornaliero (kWh di oggi)
SERIES_NAMES = {
    "SS_EnergyConsumption_GL": "Consumo casa oggi",
    "SS_EnergyWithdrawal_GL": "Prelievo rete oggi",
    "SS_EnergyIntake_GL": "Immissione rete oggi",
    "SS_EnergyProduction_GL": "Produzione fotovoltaica oggi",
    "SS_EnergySelfConsumption_GL": "Autoconsumo oggi",
}


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


def daily_kwh(telemetry: dict, now: datetime) -> float | None:
    """kWh di oggi (ora locale di `now`) dalla serie oraria."""
    last = float(telemetry["last_update"])
    if last > 1e11:  # millisecondi
        last /= 1000
    last_hour = dt_util.as_local(dt_util.utc_from_timestamp(last)).replace(
        minute=0, second=0, microsecond=0
    )
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
        try:
            wh = float(value)
        except (TypeError, ValueError):
            return None
        if not math.isfinite(wh) or wh < 0:
            return None
        total += wh
    return round(total / 1000, 3)


class TelemetryManager:
    """Individua le serie di telemetria e le aggiorna ogni 10 minuti."""

    def __init__(self, hass: HomeAssistant, client: VimarCloudClient) -> None:
        self.hass = hass
        self.client = client
        self.series: dict[str, int] = {}  # sstype → idsf (solo serie con dati)
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
        _LOGGER.debug("Vimar: telemetry series with data: %s", self.series)
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
        items = [{"idsf": idsf, "sfetype": [SFE_STATE_TELEMETRY_G]} for idsf in idsfs]
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
