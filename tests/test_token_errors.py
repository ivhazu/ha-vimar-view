"""Temporary cloud errors must not trigger a full login or stop the integration."""
import asyncio
import logging
from unittest.mock import AsyncMock

import pytest

from custom_components.vimar_cloud import api
from custom_components.vimar_cloud.api import (
    VimarAuthError,
    VimarCloudClient,
    VimarConnectionError,
)


def _client() -> VimarCloudClient:
    return VimarCloudClient("u", "p", "duid", "", refresh_token="saved-refresh")


@pytest.mark.parametrize("status", [500, 502, 503, 504, 429])
def test_temporary_http_status(status):
    assert api._is_temporary_http_error(status)


@pytest.mark.parametrize("status", [400, 401, 403, 404])
def test_auth_http_status(status):
    assert not api._is_temporary_http_error(status)


def test_refresh_unavailable_does_not_do_full_login():
    client = _client()
    client._refresh_access_token = AsyncMock(side_effect=VimarConnectionError("504"))
    client._login = AsyncMock()

    with pytest.raises(VimarConnectionError):
        asyncio.run(client._get_token())
    client._login.assert_not_called()


def test_refresh_timeout_does_not_do_full_login():
    client = _client()
    client._refresh_access_token = AsyncMock(side_effect=asyncio.TimeoutError())
    client._login = AsyncMock()

    with pytest.raises(VimarConnectionError):
        asyncio.run(client._get_token())
    client._login.assert_not_called()


def test_rejected_refresh_token_falls_back_to_full_login():
    client = _client()
    client._refresh_access_token = AsyncMock(side_effect=VimarAuthError("400"))
    client._login = AsyncMock(return_value="new-token")

    assert asyncio.run(client._get_token()) == "new-token"
    client._login.assert_awaited_once()


def test_redact_hides_token_and_duid():
    msg = "504, url='wss://prod.vimar.cloud/wssmqtt/deviceproxy?duid=012345ABC00001&access_token=eyJabc.def'"
    out = api._redact(msg)
    assert "012345ABC00001" not in out
    assert "eyJabc" not in out
    assert "duid=***" in out and "access_token=***" in out
