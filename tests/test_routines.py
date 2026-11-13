"""Routines (REST API): list, execute, plant UID from attach, button errors."""
import asyncio
from unittest.mock import AsyncMock

import pytest
from homeassistant.exceptions import HomeAssistantError

from custom_components.vimar_cloud import button
from custom_components.vimar_cloud.api import VimarCloudClient, VimarConnectionError

PLANT = "00000000-0000-0000-0000-000000000001"
RUID = "00000000-0000-0000-0000-0000000000aa"


def _client(plant_uid=PLANT):
    return VimarCloudClient("u", "p", "duid", plant_uid)


def test_plant_uid_taken_from_attach_response():
    client = _client("")
    client._send_request = AsyncMock()
    msg = {"type": "response", "function": "attach", "msgid": "1", "error": 0,
           "result": [{"plantname": "Casa", "plantuid": PLANT, "token": "t", "serverinfo": {}}]}
    asyncio.run(client._handle_response("attach", msg))
    assert client.plant_uid == PLANT


def test_get_routines_parses_list():
    client = _client()
    client._api_request = AsyncMock(return_value={"routines": [
        {"ruid": RUID, "name": "Luci Tramonto", "isActive": True},
        {"name": "senza ruid"},
    ]})
    routines = asyncio.run(client.get_routines())
    assert routines == [{"ruid": RUID, "name": "Luci Tramonto", "isActive": True}]
    client._api_request.assert_awaited_once_with("GET", f"/plants/{PLANT}/routines")


def test_execute_routine_posts_execute():
    client = _client()
    client._api_request = AsyncMock(return_value=None)
    asyncio.run(client.execute_routine(RUID))
    client._api_request.assert_awaited_once_with("POST", f"/plants/{PLANT}/routines/{RUID}/execute")


def test_routines_need_plant_uid():
    client = _client("")
    with pytest.raises(VimarConnectionError):
        asyncio.run(client.get_routines())


def _button(client):
    ent = button.VimarRoutineButton.__new__(button.VimarRoutineButton)
    ent._client = client
    ent._ruid = RUID
    ent._attr_name = "Luci Tramonto"
    return ent


def test_button_press_executes_routine():
    client = _client()
    client.execute_routine = AsyncMock()
    asyncio.run(_button(client).async_press())
    client.execute_routine.assert_awaited_once_with(RUID)


def test_button_press_error_is_home_assistant_error():
    client = _client()
    client.execute_routine = AsyncMock(side_effect=VimarConnectionError("500"))
    with pytest.raises(HomeAssistantError):
        asyncio.run(_button(client).async_press())


def test_set_routine_active_patches_is_active():
    client = _client()
    client._api_request = AsyncMock(return_value=None)
    asyncio.run(client.set_routine_active(RUID, False))
    client._api_request.assert_awaited_once_with(
        "PATCH", f"/plants/{PLANT}/routines/{RUID}", {"isActive": False}
    )


def test_routines_are_loaded_once():
    client = _client()
    client.get_routines = AsyncMock(return_value=[{"ruid": RUID, "name": "X", "isActive": True}])

    async def run():
        await client.load_routines()
        await client.load_routines()

    asyncio.run(run())
    client.get_routines.assert_awaited_once()


def _switch(client, active=True):
    from custom_components.vimar_cloud import switch
    ent = switch.VimarRoutineActiveSwitch.__new__(switch.VimarRoutineActiveSwitch)
    ent._client = client
    ent._ruid = RUID
    ent._attr_name = "Luci Tramonto abilitata"
    ent._attr_is_on = active
    ent.async_write_ha_state = lambda: None
    return ent


def test_switch_turn_off_and_on():
    client = _client()
    client.set_routine_active = AsyncMock()
    ent = _switch(client)
    asyncio.run(ent.async_turn_off())
    assert ent.is_on is False
    asyncio.run(ent.async_turn_on())
    assert ent.is_on is True
    assert client.set_routine_active.await_args_list[0].args == (RUID, False)


def test_switch_error_keeps_state():
    client = _client()
    client.set_routine_active = AsyncMock(side_effect=VimarConnectionError("500"))
    ent = _switch(client)
    with pytest.raises(HomeAssistantError):
        asyncio.run(ent.async_turn_off())
    assert ent.is_on is True
