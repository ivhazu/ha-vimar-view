"""Routine dell'app Vimar VIEW: elenco, aggiornamento periodico e rilevamento delle esecuzioni.

Il cloud Vimar non segnala quando una routine parte da sola: arrivano solo i
`changestatus` dei dispositivi. L'esecuzione viene quindi DEDOTTA:
intorno all'orario previsto (ora fissa, alba o tramonto) si controlla che i
dispositivi coinvolti raggiungano gli stati previsti dalle azioni immediate
della routine. Le esecuzioni avviate dal pulsante in HA invece sono certe.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
import logging
from typing import Any, Callable

from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.util import dt as dt_util

from .api import VimarCloudClient

_LOGGER = logging.getLogger(__name__)

EVENT_ROUTINE_EXECUTED = "vimar_cloud_routine_executed"
REFRESH_INTERVAL = timedelta(minutes=15)

TIME_REF_CLOCK = 0
TIME_REF_SUNRISE = 1
TIME_REF_SUNSET = 2

# Finestra di osservazione intorno all'orario previsto.
CLOCK_WINDOW = (timedelta(minutes=-1), timedelta(minutes=3))
SUN_WINDOW = (timedelta(minutes=-15), timedelta(minutes=15))
# Un'esecuzione già registrata in questo intervallo non viene contata due volte.
DEDUP_INTERVAL = timedelta(minutes=10)

SOURCE_SCHEDULE = "schedule"
SOURCE_HOME_ASSISTANT = "home_assistant"


@dataclass
class Schedule:
    """Trigger "schedule": ["schedule", minuti, ore, [giorni ISO 1-7], riferimento, ...]."""

    minutes: int
    hours: int
    weekdays: list[int]
    time_ref: int

    @property
    def offset(self) -> timedelta:
        return timedelta(hours=self.hours, minutes=self.minutes)


@dataclass
class RoutineInfo:
    ruid: str
    name: str
    active: bool = True
    schedules: list[Schedule] = field(default_factory=list)
    # Azioni immediate attese: {(idsf, sfetype di stato): valore}
    expected: dict[tuple[int, str], str] = field(default_factory=dict)


def parse_schedules(triggers: Any) -> list[Schedule]:
    out: list[Schedule] = []
    if not isinstance(triggers, list):
        return out
    for trig in triggers:
        if not (isinstance(trig, list) and len(trig) >= 5 and trig[0] == "schedule"):
            continue
        try:
            days = [int(d) for d in trig[3]] if isinstance(trig[3], list) else []
            out.append(Schedule(int(trig[1]), int(trig[2]), days, int(trig[4])))
        except (TypeError, ValueError):
            continue
    return out


def parse_expected(actions: Any, duid: str) -> dict[tuple[int, str], str]:
    """Stati attesi dalle azioni senza ritardo: SFE_Cmd_X → SFE_State_X."""
    expected: dict[tuple[int, str], str] = {}
    if not isinstance(actions, list):
        return expected
    for step in actions:
        if not (isinstance(step, list) and len(step) == 2 and step[0] == 0):
            continue
        payload = step[1]
        if not (isinstance(payload, list) and len(payload) >= 3 and payload[0] == duid):
            continue
        for cmd in payload[2:]:
            if (
                isinstance(cmd, list) and len(cmd) == 3 and isinstance(cmd[0], int)
                and isinstance(cmd[1], str) and cmd[1].startswith("SFE_Cmd_")
            ):
                expected[(cmd[0], "SFE_State_" + cmd[1][len("SFE_Cmd_"):])] = str(cmd[2])
    return expected


def occurrences(
    schedule: Schedule,
    day: date,
    sun_time: Callable[[str, date], datetime | None],
) -> datetime | None:
    """Orario previsto di un trigger in un certo giorno (None se non si applica)."""
    if schedule.weekdays and day.isoweekday() not in schedule.weekdays:
        return None
    if schedule.time_ref == TIME_REF_CLOCK:
        return dt_util.start_of_local_day(day) + schedule.offset
    event = {TIME_REF_SUNRISE: "sunrise", TIME_REF_SUNSET: "sunset"}.get(schedule.time_ref)
    if event is None:
        return None
    base = sun_time(event, day)
    return None if base is None else base + schedule.offset


class RoutineTracker:
    """Tiene aggiornate le routine e ne rileva le esecuzioni."""

    def __init__(self, hass: HomeAssistant, client: VimarCloudClient, duid: str) -> None:
        self.hass = hass
        self.client = client
        self.duid = duid
        self.routines: dict[str, RoutineInfo] = {}
        self.last_run: dict[str, datetime] = {}
        self._listeners: list[Callable[[], None]] = []
        self._values: dict[tuple[int, str], str] = {}
        self._changed_at: dict[tuple[int, str], datetime] = {}
        self._unsub: list[Callable[[], None]] = []

    # ─── ciclo di vita ───────────────────────────────────────────────────────

    async def async_start(self) -> None:
        try:
            await self.async_refresh()
        except Exception as err:  # noqa: BLE001
            _LOGGER.warning("Vimar: could not load routines: %s", err)
        self._snapshot_states()
        self.client.register_state_callback(self._on_states)
        self._unsub.append(lambda: self.client.unregister_state_callback(self._on_states))
        self._unsub.append(
            async_track_time_interval(self.hass, self._async_periodic_refresh, REFRESH_INTERVAL)
        )

    @callback
    def async_stop(self) -> None:
        for unsub in self._unsub:
            unsub()
        self._unsub.clear()

    def add_listener(self, listener: Callable[[], None]) -> Callable[[], None]:
        self._listeners.append(listener)
        return lambda: self._listeners.remove(listener)

    def _notify(self) -> None:
        for listener in tuple(self._listeners):
            listener()

    # ─── elenco e dettagli dal cloud ─────────────────────────────────────────

    async def _async_periodic_refresh(self, _now: datetime) -> None:
        try:
            await self.async_refresh()
        except Exception as err:  # noqa: BLE001
            _LOGGER.debug("Vimar: routine refresh failed: %s", err)

    async def async_refresh(self) -> None:
        listed = await self.client.get_routines()
        self.client.routines = listed
        fresh: dict[str, RoutineInfo] = {}
        for item in listed:
            ruid = item["ruid"]
            info = RoutineInfo(ruid, item.get("name") or "Routine", bool(item.get("isActive", True)))
            try:
                detail = await self.client.get_routine(ruid)
                info.schedules = parse_schedules(detail.get("triggers"))
                info.expected = parse_expected(detail.get("action"), self.duid)
            except Exception as err:  # noqa: BLE001
                _LOGGER.debug("Vimar: routine %s detail not available: %s", ruid, err)
                old = self.routines.get(ruid)
                if old:
                    info.schedules, info.expected = old.schedules, old.expected
            fresh[ruid] = info
        self.routines = fresh
        self._snapshot_states()
        self._notify()

    def is_active(self, ruid: str) -> bool | None:
        info = self.routines.get(ruid)
        return None if info is None else info.active

    def set_active(self, ruid: str, active: bool) -> None:
        if ruid in self.routines:
            self.routines[ruid].active = active

    # ─── rilevamento ─────────────────────────────────────────────────────────

    def _watched_keys(self) -> set[tuple[int, str]]:
        return {key for info in self.routines.values() for key in info.expected}

    def _snapshot_states(self) -> None:
        for idsf, sfetype in self._watched_keys():
            value = self.client.get_state(idsf, sfetype)
            if value is not None:
                self._values.setdefault((idsf, sfetype), str(value))

    def _sun_time(self, event: str, day: date) -> datetime | None:
        from homeassistant.helpers.sun import get_astral_event_date

        when = get_astral_event_date(self.hass, event, day)
        return None if when is None else dt_util.as_local(when)

    @callback
    def _on_states(self, updated: list[int]) -> None:
        now = dt_util.now()
        changed = False
        for key in self._watched_keys():
            if key[0] not in updated:
                continue
            value = self.client.get_state(*key)
            if value is None:
                continue
            value = str(value)
            if self._values.get(key) != value:
                self._values[key] = value
                self._changed_at[key] = now
                changed = True
        if changed:
            self.check(now)

    def check(self, now: datetime) -> None:
        """Verifica se qualche routine attiva è appena stata eseguita."""
        for info in self.routines.values():
            if not info.active or not info.expected or not info.schedules:
                continue
            scheduled = self._current_occurrence(info, now)
            if scheduled is None:
                continue
            if not all(self._values.get(k) == v for k, v in info.expected.items()):
                continue
            start = scheduled + self._window(info, scheduled)[0]
            if not any(
                self._changed_at.get(k) and self._changed_at[k] >= start
                for k in info.expected
            ):
                continue
            self.mark_executed(info.ruid, SOURCE_SCHEDULE, now, scheduled)

    def _window(self, info: RoutineInfo, _scheduled: datetime) -> tuple[timedelta, timedelta]:
        uses_sun = any(s.time_ref != TIME_REF_CLOCK for s in info.schedules)
        return SUN_WINDOW if uses_sun else CLOCK_WINDOW

    def _current_occurrence(self, info: RoutineInfo, now: datetime) -> datetime | None:
        for schedule in info.schedules:
            window = SUN_WINDOW if schedule.time_ref != TIME_REF_CLOCK else CLOCK_WINDOW
            for day in (now.date() - timedelta(days=1), now.date()):
                when = occurrences(schedule, day, self._sun_time)
                if when is not None and when + window[0] <= now <= when + window[1]:
                    return when
        return None

    def mark_executed(
        self, ruid: str, source: str, when: datetime | None = None, scheduled: datetime | None = None
    ) -> None:
        when = when or dt_util.now()
        last = self.last_run.get(ruid)
        if last is not None and abs(when - last) < DEDUP_INTERVAL:
            return
        self.last_run[ruid] = when
        info = self.routines.get(ruid)
        data = {
            "ruid": ruid,
            "name": info.name if info else ruid,
            "source": source,
            "time": when.isoformat(),
        }
        if scheduled is not None:
            data["scheduled"] = scheduled.isoformat()
        _LOGGER.debug("Vimar: routine executed %s", data)
        self.hass.bus.async_fire(EVENT_ROUTINE_EXECUTED, data)
        self._notify()
