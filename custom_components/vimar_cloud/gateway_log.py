"""Registro eventi del gateway Vimar (sezione "Eventi" dell'app VIEW).

Il registro viene letto periodicamente con la funzione WebSocket `getlog`; ogni
voce nuova genera l'evento HA `vimar_cloud_gateway_event` e aggiorna il sensore
"Ultimo evento". Esempi: distacco e ripristino dei carichi, forzature, perdita e
ripristino della connessione a internet o al cloud.
"""
from __future__ import annotations

from datetime import datetime, timedelta
import logging
from typing import Any, Callable

from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.event import async_call_later, async_track_time_interval
from homeassistant.util import dt as dt_util

from .api import VimarCloudClient
from .const import SFE_STATE_LOAD

_LOGGER = logging.getLogger(__name__)

EVENT_GATEWAY_EVENT = "vimar_cloud_gateway_event"
POLL_INTERVAL = timedelta(minutes=2)
# Dopo un cambio di stato di un carico il registro viene riletto subito (con un piccolo ritardo).
LOAD_CHANGE_POLL_DELAY = 5

# Testi in italiano per le voci note; per le altre si usa la chiave così com'è.
MESSAGES = {
    "BLEG_LOG_LOAD_CUT_OFF": "Carico {load} staccato",
    "BLEG_LOG_LOAD_RESTORE": "Carico {load} ripristinato",
    "BLEG_LOG_LOAD_ON_FORCED": "Carico {load} forzato acceso",
    "BLEG_LOG_LOAD_OFF_FORCED": "Carico {load} forzato spento",
    "BLEG_LOG_LOAD_FORCED_SETTING_DELETED": "Forzatura del carico {load} annullata",
    "GW_LOG_CLOUD_CONNECTION_UP": "Connessione al cloud ripristinata",
    "GW_LOG_CLOUD_CONNECTION_DOWN": "Connessione al cloud persa",
    "GW_LOG_INTERNET_CONNECTION_UP": "Connessione a internet ripristinata",
    "GW_LOG_INTERNET_CONNECTION_DOWN": "Connessione a internet persa",
}


def _clean(value: Any) -> str:
    """I parametri arrivano con le virgolette incluse: '"140"' → '140'."""
    return str(value).strip().strip('"')


def describe(entry: dict) -> dict:
    """Trasforma una voce grezza del registro nei dati dell'evento HA."""
    key = str(entry.get("dictkey", ""))
    params = entry.get("params") if isinstance(entry.get("params"), dict) else {}
    params = {k: _clean(v) for k, v in params.items()}
    ts = entry.get("timestamp")
    when = dt_util.utc_from_timestamp(ts) if isinstance(ts, (int, float)) else None
    data: dict[str, Any] = {
        "key": key,
        "level": entry.get("level"),
        "category": entry.get("category"),
        "time": when.isoformat() if when else None,
        "params": params,
    }
    load = None
    if key.startswith("BLEG_LOG_LOAD"):
        load = params.get("P2")
        data["load"] = load
        if params.get("P1", "").isdigit():
            data["load_id"] = int(params["P1"])
    template = MESSAGES.get(key)
    data["message"] = template.format(load=load or "?") if template else key
    return data


class GatewayLogWatcher:
    """Legge periodicamente il registro e genera un evento per ogni voce nuova."""

    def __init__(self, hass: HomeAssistant, client: VimarCloudClient) -> None:
        self.hass = hass
        self.client = client
        self.last: dict | None = None  # dati dell'ultimo evento (per il sensore)
        self._since: int | None = None  # timestamp dell'ultima voce già vista
        self._seen_at_since: set[str] = set()
        self._listeners: list[Callable[[], None]] = []
        self._unsub: list[Callable[[], None]] = []
        self._pending_poll: Callable[[], None] | None = None
        self._loads: dict[int, Any] = {}

    def add_listener(self, listener: Callable[[], None]) -> Callable[[], None]:
        self._listeners.append(listener)
        return lambda: self._listeners.remove(listener)

    async def async_start(self) -> None:
        self._unsub.append(async_track_time_interval(self.hass, self._async_poll, POLL_INTERVAL))
        self.client.register_state_callback(self._on_states)
        self._unsub.append(lambda: self.client.unregister_state_callback(self._on_states))
        await self._async_poll(None)

    @callback
    def async_stop(self) -> None:
        for unsub in self._unsub:
            unsub()
        self._unsub.clear()
        if self._pending_poll:
            self._pending_poll()
            self._pending_poll = None

    @callback
    def _on_states(self, updated: list[int]) -> None:
        """Un carico ha cambiato stato: rileggi il registro tra qualche secondo."""
        for idsf in updated:
            value = self.client.get_state(idsf, SFE_STATE_LOAD)
            if value is None:
                continue
            if idsf in self._loads and self._loads[idsf] != value and self._pending_poll is None:
                self._pending_poll = async_call_later(
                    self.hass, LOAD_CHANGE_POLL_DELAY, self._async_delayed_poll
                )
            self._loads[idsf] = value

    async def _async_delayed_poll(self, _now: datetime) -> None:
        self._pending_poll = None
        await self._async_poll(None)

    @staticmethod
    def _entry_id(entry: dict) -> str:
        return f"{entry.get('timestamp')}|{entry.get('dictkey')}|{entry.get('params')}"

    async def _async_poll(self, _now: datetime | None) -> None:
        now_ts = int(dt_util.utcnow().timestamp())
        first_run = self._since is None
        from_ts = now_ts - 3600 if first_run else self._since
        try:
            entries = await self.client.get_log(from_ts, now_ts)
        except Exception as err:  # noqa: BLE001
            _LOGGER.debug("Vimar: gateway log not available: %s", err)
            return
        entries = sorted(
            (e for e in entries if isinstance(e.get("timestamp"), (int, float))),
            key=lambda e: e["timestamp"],
        )
        new = [
            e for e in entries
            if self._since is None
            or e["timestamp"] > self._since
            or (e["timestamp"] == self._since and self._entry_id(e) not in self._seen_at_since)
        ]
        if entries:
            newest = entries[-1]["timestamp"]
            if newest != self._since:
                self._seen_at_since = set()
            self._since = newest
            self._seen_at_since |= {self._entry_id(e) for e in entries if e["timestamp"] == newest}
        elif first_run:
            self._since = now_ts

        if first_run:
            # Al primo avvio niente eventi per il passato: solo il sensore.
            if new:
                self.last = describe(new[-1])
                self._notify()
            return

        for entry in new:
            data = describe(entry)
            _LOGGER.debug("Vimar: gateway event %s", data)
            self.hass.bus.async_fire(EVENT_GATEWAY_EVENT, data)
            self.last = data
        if new:
            self._notify()

    def _notify(self) -> None:
        for listener in tuple(self._listeners):
            listener()
