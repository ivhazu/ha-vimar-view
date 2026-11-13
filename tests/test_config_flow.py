"""Config flow: gateway list from the cloud, single/multiple choice, manual fallback."""
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from custom_components.vimar_cloud import config_flow
from custom_components.vimar_cloud.const import CONF_DUID, CONF_PLANT_UID, CONF_REFRESH_TOKEN

GW = {"duid": "000000AAA00001", "displayname": "Casa", "model": "BLEG", "plantname": "Casa",
      "plantuid": "00000000-0000-0000-0000-000000000001", "online": True}
TH = {"duid": "000000AAA00002", "displayname": "Zona Notte", "model": "STW", "plantname": "Zona Notte",
      "plantuid": "00000000-0000-0000-0000-000000000002", "online": True}
CREDS = {"username": "u@example.com", "password": "p"}


def _flow(configured=()):
    flow = config_flow.VimarCloudConfigFlow()
    flow.hass = MagicMock()
    flow.context = {"source": "user"}
    flow._async_current_ids = lambda include_ignore=True: set(configured)
    flow.async_set_unique_id = AsyncMock()
    flow._abort_if_unique_id_configured = MagicMock()
    flow.async_create_entry = lambda title, data: {"type": "create_entry", "title": title, "data": data}
    flow.async_show_form = lambda **kw: {"type": "form", **kw}
    flow.async_abort = lambda reason: {"type": "abort", "reason": reason}
    return flow


def _run(flow, gateways, user_input=CREDS, login_error=None):
    with patch.object(config_flow.VimarCloudClient, "_login", AsyncMock(side_effect=login_error)), \
         patch.object(config_flow.VimarCloudClient, "get_gateways", AsyncMock(return_value=gateways)), \
         patch.object(config_flow.VimarCloudClient, "refresh_token", "rt"):
        return asyncio.run(flow.async_step_user(user_input))


def test_single_gateway_is_created_directly():
    res = _run(_flow(), [GW])
    assert res["type"] == "create_entry"
    assert res["data"][CONF_DUID] == GW["duid"]
    assert res["data"][CONF_PLANT_UID] == GW["plantuid"]
    assert res["data"][CONF_REFRESH_TOKEN] == "rt"


def test_multiple_devices_show_choice_and_thermostat_title():
    flow = _flow()
    res = _run(flow, [GW, TH])
    assert res["type"] == "form" and res["step_id"] == "gateway"
    res = asyncio.run(flow.async_step_gateway({CONF_DUID: TH["duid"]}))
    assert res["title"] == "Zona Notte (Termostato)"


def test_already_configured_are_hidden():
    res = _run(_flow(configured={GW["duid"]}), [GW, TH])
    assert res["type"] == "create_entry" and res["data"][CONF_DUID] == TH["duid"]
    res = _run(_flow(configured={GW["duid"], TH["duid"]}), [GW, TH])
    assert res == {"type": "abort", "reason": "all_configured"}


def test_empty_list_falls_back_to_manual():
    flow = _flow()
    res = _run(flow, [])
    assert res["type"] == "form" and res["step_id"] == "manual"
    res = asyncio.run(flow.async_step_manual({CONF_DUID: " 000000aaa00009 "}))
    assert res["data"][CONF_DUID] == "000000AAA00009"


def test_invalid_credentials():
    from custom_components.vimar_cloud.api import VimarAuthError
    res = _run(_flow(), [GW], login_error=VimarAuthError("bad"))
    assert res["type"] == "form" and res["errors"] == {"base": "invalid_auth"}


def test_get_gateways_uses_ngvcloud():
    from custom_components.vimar_cloud.api import VimarCloudClient
    from custom_components.vimar_cloud.const import VIMAR_NGV_URL
    client = VimarCloudClient("u", "p", "", "")
    client._api_request = AsyncMock(return_value=[GW, {"no": "duid"}])
    assert asyncio.run(client.get_gateways()) == [GW]
    client._api_request.assert_awaited_once_with("GET", "/user/associations", base_url=VIMAR_NGV_URL)
