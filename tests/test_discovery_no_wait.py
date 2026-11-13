"""Discovery runs inside the WebSocket read loop: it must never wait for a response."""
import asyncio
from types import SimpleNamespace

from custom_components.vimar_cloud.api import IDSF_PAIR_OFFSET, VimarCloudClient


def _sf(idsf, sstype, name="Lavatrice"):
    return {"idsf": idsf, "sstype": sstype, "name": name,
            "elements": [{"sfetype": "SFE_State_GlobalActivePowerConsumption", "value": "0"}]}


def test_discovery_signals_ready_without_waiting_for_responses():
    client = VimarCloudClient("u", "p", "duid", "")
    client._ws = SimpleNamespace(closed=False)  # connected session, as in the real read loop
    client._session_token = "session"
    calls = []

    async def fake_send_request(function, args, params=None, *, wait_response=False, timeout=None):
        calls.append((function, wait_response))
        if wait_response:  # in the real read loop this would block until timeout
            await asyncio.sleep(3600)
        return "1"

    client._send_request = fake_send_request
    ready = []
    client.set_discovery_callback(lambda: ready.append(True))

    loads = [_sf(100 + i, "SS_Energy_Load", f"Carico {i}") for i in range(4)]
    measures = [_sf(100 + i + IDSF_PAIR_OFFSET, "SS_Energy_Measure1P", f"Carico {i}") for i in range(4)]
    result = [{"idambient": 1, "sf": loads + measures}]

    asyncio.run(asyncio.wait_for(client._process_plant_discovery(result), timeout=2))

    assert ready == [True]
    assert len(client.measure_to_load) == 4
    assert not any(wait for _, wait in calls)
