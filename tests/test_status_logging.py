"""Raw status updates are logged at DEBUG so new SFE values can be discovered."""
import asyncio
import logging

from custom_components.vimar_cloud.api import VimarCloudClient


def test_status_update_values_are_logged_at_debug(caplog):
    client = VimarCloudClient("u", "p", "duid", "")
    caplog.set_level(logging.DEBUG, logger="custom_components.vimar_cloud.api")

    asyncio.run(client._process_status_update([
        {"idsf": 7, "elements": [{"sfetype": "SFE_State_HVACMode", "value": "Absence"}]}
    ]))

    assert client.get_state(7, "SFE_State_HVACMode") == "Absence"
    assert "SFE_State_HVACMode" in caplog.text
    assert "Absence" in caplog.text
