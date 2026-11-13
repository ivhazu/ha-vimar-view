"""Exercise real recovery methods with fake transports; no cloud access."""
import ast,asyncio,unittest,logging
from pathlib import Path
from types import SimpleNamespace as NS
from unittest.mock import AsyncMock
P=Path(__file__).resolve().parents[1]/'custom_components/vimar_cloud'
class ConnectionError(Exception):pass
root=ast.parse((P/'api.py').read_text())
cls=next(n for n in root.body if isinstance(n,ast.ClassDef) and n.name=='VimarCloudClient')
methods=[n for n in cls.body if isinstance(n,ast.AsyncFunctionDef) and n.name in ['_attach_watchdog','_send_command','_connect_and_run']]
env=dict(asyncio=asyncio,_LOGGER=logging.getLogger('test'),VimarConnectionError=ConnectionError,VimarAuthError=type('AuthError',(Exception,),{}),FUNC_DOACTION='doaction',VIMAR_WS_URL='wss://test',_random_client_token=lambda:'test',_redact=str)
exec(compile(ast.fix_missing_locations(ast.Module(body=[ast.ClassDef(name='Client',bases=[],keywords=[],body=methods,decorator_list=[])],type_ignores=[])),'actual_candidate','exec'),env)
Client=env['Client']
class Tests(unittest.IsolatedAsyncioTestCase):

    async def test_incomplete_session_closed(self):
        c = Client()
        c._running = True
        c._session_token = None
        c._ws = NS(close=AsyncMock())
        await c._attach_watchdog(c._ws, 0)
        c._ws.close.assert_awaited_once()

    async def test_healthy_or_replaced_or_stopped_session_not_closed(self):
        for mode in ['healthy', 'replaced', 'stopped']:
            c = Client()
            ws = NS(close=AsyncMock())
            c._ws = object() if mode == 'replaced' else ws
            c._running = mode != 'stopped'
            c._session_token = 'ok' if mode == 'healthy' else None
            await c._attach_watchdog(ws, 0)
            ws.close.assert_not_called()

    async def test_no_commands_before_session_ready(self):
        for (ws, token) in [(None, None), (NS(closed=True), 'ok'), (NS(closed=False), None)]:
            c = Client()
            c._ws = ws
            c._session_token = token
            c._send_request = AsyncMock()
            with self.assertRaises(ConnectionError):
                await c._send_command([])
            c._send_request.assert_not_called()

    async def test_ready_command_unchanged(self):
        c = Client()
        c._ws = NS(closed=False)
        c._session_token = 'ok'
        c._send_request = AsyncMock()
        await c._send_command([1])
        c._send_request.assert_awaited_once_with('doaction', [1], wait_response=True, timeout=None)

    async def test_full_loop_recovers_and_backs_off(self):
        c = Client()
        c._running = True
        c._session_token = None
        c._pending_requests = {}
        c._duid = 'test'
        c._get_token = AsyncMock(return_value='test')
        c._attach = AsyncMock()
        c._fail_pending_requests = lambda e: None
        c._keepalive_loop = lambda : asyncio.sleep(100)
        original = Client._attach_watchdog
        c._attach_watchdog = lambda ws: original(c, ws, 0.002)
        delays = []
        sockets = []

        class WS:
            closed = False
            close_code = None

            def __init__(self):
                self.done = asyncio.Event()

            async def __aenter__(self):
                return self

            async def __aexit__(self, *args):
                await self.close()

            async def close(self):
                self.closed = True
                self.close_code = 1000
                self.done.set()

            def exception(self):
                return None

            def __aiter__(self):
                return self

            async def __anext__(self):
                await self.done.wait()
                raise StopAsyncIteration

        class Session:

            async def __aenter__(self):
                return self

            async def __aexit__(self, *args):
                pass

            def ws_connect(self, *args, **kwargs):
                ws = WS()
                sockets.append(ws)
                return ws

        async def sleep(delay):
            if delay >= 5:
                delays.append(delay)
                if len(delays) == 2:
                    c._running = False
            else:
                await asyncio.sleep(delay)
        real = env['asyncio']
        env['asyncio'] = NS(sleep=sleep, get_running_loop=asyncio.get_running_loop, create_task=asyncio.create_task, gather=asyncio.gather)
        env['aiohttp'] = NS(ClientSession=Session, ClientWSTimeout=lambda **kw: None, WSMsgType=NS(TEXT=1, ERROR=2, CLOSE=3, CLOSED=4))
        try:
            await asyncio.wait_for(c._connect_and_run(), 1)
        finally:
            env['asyncio'] = real
        self.assertEqual(delays, [5, 10])
        self.assertEqual(len(sockets), 2)
        self.assertTrue(all((w.closed for w in sockets)))
        self.assertIsNone(c._ws)



class LightCommandTests(unittest.IsolatedAsyncioTestCase):
    async def test_transport_errors_are_wrapped_and_unexpected_errors_propagate(self):
        class HAError(Exception): pass
        class ClientError(Exception): pass
        tree = ast.parse((P / 'light.py').read_text())
        method = next(n for n in ast.walk(tree) if isinstance(n, ast.AsyncFunctionDef) and n.name == '_async_light_command')
        namespace = dict(Any=object, HomeAssistantError=HAError, VimarConnectionError=ConnectionError, aiohttp=NS(ClientError=ClientError))
        exec(compile(ast.fix_missing_locations(ast.Module(body=[method], type_ignores=[])), 'light_command', 'exec'), namespace)
        for command, args in [('turn_on', ()), ('turn_off', ()), ('set_brightness', (50,))]:
            for error in [ConnectionError('offline'), ClientError('network'), TimeoutError(), ValueError('bug'), asyncio.CancelledError()]:
                client = NS(**{command: AsyncMock(side_effect=error)})
                entity = NS(_client=client, _idsf=1)
                expected = HAError if isinstance(error, (ConnectionError, ClientError, TimeoutError)) else type(error)
                with self.assertRaises(expected) as raised:
                    await namespace['_async_light_command'](entity, command, *args)
                if expected is HAError:
                    self.assertIs(raised.exception.__cause__, error)
                getattr(client, command).assert_awaited_once_with(1, *args)

if __name__ == "__main__": unittest.main()
