"""Load mode select: "Forced off" is shown when set by the gateway but cannot be selected."""
import asyncio
from unittest.mock import AsyncMock

import pytest
from homeassistant.exceptions import ServiceValidationError

from custom_components.vimar_cloud import select
from custom_components.vimar_cloud.const import (
    LOAD_STATE_AUTO,
    LOAD_STATE_FORCED_OFF,
    LOAD_STATE_FORCED_ON,
    SFE_STATE_LOAD,
)


class FakeClient:
    def __init__(self, state):
        self.state = state
        self.set_load = AsyncMock()

    def get_state(self, idsf, sfetype):
        assert sfetype == SFE_STATE_LOAD
        return self.state


def _entity(state):
    ent = select.VimarLoadSelect.__new__(select.VimarLoadSelect)
    ent._client = FakeClient(state)
    ent._idsf = 5
    return ent


@pytest.mark.parametrize("state,expected", [
    ("Auto on", LOAD_STATE_AUTO),
    ("Auto off", LOAD_STATE_AUTO),
    ("Forced on", LOAD_STATE_FORCED_ON),
])
def test_normal_states_offer_only_selectable_options(state, expected):
    ent = _entity(state)
    assert ent.current_option == expected
    assert ent.options == [LOAD_STATE_AUTO, LOAD_STATE_FORCED_ON]


def test_forced_off_is_displayed_while_active():
    ent = _entity("Forced off")
    assert ent.current_option == LOAD_STATE_FORCED_OFF
    assert LOAD_STATE_FORCED_OFF in ent.options


def test_forced_off_cannot_be_selected():
    ent = _entity("Auto on")
    with pytest.raises(ServiceValidationError):
        asyncio.run(ent.async_select_option(LOAD_STATE_FORCED_OFF))
    ent._client.set_load.assert_not_called()


def test_selecting_forced_off_while_active_is_a_no_op():
    ent = _entity("Forced off")
    asyncio.run(ent.async_select_option(LOAD_STATE_FORCED_OFF))
    ent._client.set_load.assert_not_called()


@pytest.mark.parametrize("option", [LOAD_STATE_AUTO, LOAD_STATE_FORCED_ON])
def test_selectable_options_are_sent(option):
    ent = _entity("Forced off")
    asyncio.run(ent.async_select_option(option))
    ent._client.set_load.assert_awaited_once_with(5, option)
