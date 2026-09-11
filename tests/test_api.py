import asyncio

from custom_components.vimar_cloud.api import VimarCloudClient, VimarConnectionError


class FakeWebSocket:
    def __init__(self):
        self.messages = []

    async def send_str(self, value):
        self.messages.append(value)


def make_client():
    client = VimarCloudClient("u", "p", "duid", "")
    client._ws = FakeWebSocket()
    return client


async def wait_for_pending(client, msgid):
    while msgid not in client._pending_requests:
        await asyncio.sleep(0)


def test_command_waits_for_matching_response():
    async def run():
        client = make_client()
        task = asyncio.create_task(client._send_command([{"idsf": 1}]))
        await asyncio.sleep(0)
        msgid = next(iter(client._pending_requests))
        await client._handle_message(
            '{"type":"response","function":"doaction","msgid":"%s","error":0,"result":[]}' % msgid
        )
        await task
        assert not client._pending_requests

    asyncio.run(run())


def test_command_error_is_propagated():
    async def run():
        client = make_client()
        task = asyncio.create_task(client._send_command([{"idsf": 1}]))
        await asyncio.sleep(0)
        msgid = next(iter(client._pending_requests))
        await client._handle_message(
            '{"type":"response","function":"doaction","msgid":"%s","error":42,"result":"denied"}' % msgid
        )
        try:
            await task
        except VimarConnectionError:
            return
        raise AssertionError("Expected VimarConnectionError")

    asyncio.run(run())
