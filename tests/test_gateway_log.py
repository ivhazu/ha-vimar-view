"""Registro eventi del gateway → eventi HA."""
import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.vimar_cloud import gateway_log as gl
from custom_components.vimar_cloud.api import VimarCloudClient, VimarConnectionError


def _e(ts, key, p1=None, p2=None, level="info"):
    params = {} if p1 is None else {"P1": f'"{p1}"', "P2": f'"{p2}"'}
    return {"timestamp": ts, "level": level, "role": "Administrator", "category": "info",
            "dictkey": key, "params": params}


def test_describe_load_event():
    d = gl.describe(_e(1794402880, "BLEG_LOG_LOAD_CUT_OFF", 105, "Ferro"))
    assert d["message"] == "Carico Ferro staccato"
    assert d["load"] == "Ferro" and d["load_id"] == 105
    assert d["params"] == {"P1": "105", "P2": "Ferro"}
    assert d["time"].startswith("2026-11-")


def test_describe_unknown_key_uses_key():
    d = gl.describe(_e(1, "GW_LOG_SOMETHING_NEW"))
    assert d["message"] == "GW_LOG_SOMETHING_NEW" and "load" not in d


def _watcher(batches):
    hass = MagicMock()
    client = SimpleNamespace(get_log=AsyncMock(side_effect=batches))
    return gl.GatewayLogWatcher(hass, client), hass


def test_first_poll_sets_sensor_without_events_then_new_entries_fire():
    w, hass = _watcher([
        [_e(100, "GW_LOG_CLOUD_CONNECTION_UP"), _e(90, "GW_LOG_CLOUD_CONNECTION_DOWN")],
        [_e(100, "GW_LOG_CLOUD_CONNECTION_UP"), _e(150, "BLEG_LOG_LOAD_CUT_OFF", 105, "Ferro")],
        [_e(150, "BLEG_LOG_LOAD_CUT_OFF", 105, "Ferro"), _e(150, "BLEG_LOG_LOAD_CUT_OFF", 140, "Cappa")],
    ])
    asyncio.run(w._async_poll(None))
    hass.bus.async_fire.assert_not_called()
    assert w.last["message"] == "Connessione al cloud ripristinata"

    asyncio.run(w._async_poll(None))
    hass.bus.async_fire.assert_called_once()
    assert hass.bus.async_fire.call_args.args[1]["load"] == "Ferro"

    asyncio.run(w._async_poll(None))  # stesso timestamp, voce diversa: solo Cappa
    assert hass.bus.async_fire.call_count == 2
    assert hass.bus.async_fire.call_args.args[1]["load"] == "Cappa"


def test_poll_errors_are_ignored():
    w, hass = _watcher([VimarConnectionError("not ready")])
    asyncio.run(w._async_poll(None))
    hass.bus.async_fire.assert_not_called()


def test_get_log_request_and_result():
    client = VimarCloudClient("u", "p", "duid", "")
    client._ws = SimpleNamespace(closed=False)
    client._session_token = "t"
    client._send_request = AsyncMock(return_value={"result": [_e(1, "X"), "junk"]})
    out = asyncio.run(client.get_log(0, 10))
    assert out == [_e(1, "X")]
    func, args = client._send_request.await_args.args
    assert func == "getlog" and args[0]["from"] == 0 and args[0]["to"] == 10
    assert client._send_request.await_args.kwargs == {"wait_response": True}


def test_get_log_needs_session():
    client = VimarCloudClient("u", "p", "duid", "")
    with pytest.raises(VimarConnectionError):
        asyncio.run(client.get_log(0, 10))
