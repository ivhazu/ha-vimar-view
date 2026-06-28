"""Vimar Cloud WebSocket API client."""
from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import logging
import random
import re
import secrets
import string
import time
from typing import Any, Callable

import aiohttp

from .const import (
    CHANGE_OVER_COOLING,
    CHANGE_OVER_HEATING,
    FUNC_ATTACH,
    FUNC_CHANGESTATUS,
    FUNC_DETACH,
    FUNC_DOACTION,
    FUNC_GETSTATUS,
    FUNC_KEEPALIVE,
    FUNC_REGISTER,
    FUNC_SFDISCOVERY,
    HVAC_MODE_VIMAR_AUTO,
    HVAC_MODE_VIMAR_OFF,
    HVAC_MODE_VIMAR_TIMED_MANUAL,
    KEEPALIVE_INTERVAL,
    LOAD_STATE_AUTO,
    SF_CATEGORY_BIGDATA,
    SF_CATEGORY_PLANT,
    SFE_CMD_AMBIENT_SETPOINT,
    SFE_CMD_BRIGHTNESS,
    SFE_CMD_CHANGE_OVER_MODE,
    SFE_CMD_EXECUTE,
    SFE_CMD_HVAC_MODE,
    SFE_CMD_LOAD,
    SFE_CMD_ONOFF,
    SFE_CMD_SHUTTER,
    SFE_STATE_BRIGHTNESS,
    SFE_STATE_GLOBAL_ACTIVE_POWER,
    SFE_STATE_GLOBAL_THRESHOLD,
    SFE_STATE_HVAC_MODE,
    SFE_STATE_LOAD,
    SFE_STATE_LOAD_ID,
    SFE_STATE_LOADS_PRIORITY,
    SFE_STATE_ONOFF,
    SFE_STATE_SHUTTER,
    SHUTTER_CMD_CLOSE,
    SHUTTER_CMD_OPEN,
    SHUTTER_CMD_STOP,
    TOKEN_REFRESH_MARGIN,
    VIMAR_AUTH_URL,
    VIMAR_CLIENT_ID,
    VIMAR_OAUTH_AUTH_URL,
    VIMAR_REDIRECT_URI,
    VIMAR_WS_URL,
)

_LOGGER = logging.getLogger(__name__)

USER_AGENT = "VIEW / 2.16.2 (1260324852) - 8250fb9b66c413b6 - Android"
IDSF_PAIR_OFFSET = 8  # Measure idsf = Load idsf + 8


class VimarAuthError(Exception):
    """Authentication error."""


class VimarConnectionError(Exception):
    """Connection error."""


def _pkce_pair() -> tuple[str, str]:
    verifier = secrets.token_urlsafe(64)
    challenge = base64.urlsafe_b64encode(
        hashlib.sha256(verifier.encode()).digest()
    ).rstrip(b"=").decode()
    return verifier, challenge


def _random_source_id() -> str:
    return ''.join(random.choices('0123456789abcdef', k=16))


def _random_client_token() -> str:
    return ''.join(random.choices(string.ascii_letters + string.digits, k=12))


class VimarCloudClient:
    """Vimar Cloud WebSocket client."""

    def __init__(
        self,
        username: str,
        password: str,
        duid: str,
        plant_uid: str,
        refresh_token: str | None = None,
    ) -> None:
        self._username = username
        self._password = password
        self._duid = duid
        self._plant_uid = plant_uid

        self._access_token: str | None = None
        # Pre-load saved refresh token to avoid full login on restart
        self._refresh_token: str | None = refresh_token
        self._token_expires_at: float = 0

        self._session_token: str | None = None
        self._source_id: str = _random_source_id()
        self._client_token: str = _random_client_token()
        self._user_uid: str = ""

        self._ws: aiohttp.ClientWebSocketResponse | None = None
        self._msgid: int = 9

        self.device_states: dict[int, dict[str, Any]] = {}
        self.devices: dict[int, dict] = {}
        self.measure_to_load: dict[int, int] = {}
        self.idsf_energy_manager: int | None = None

        self.plant_name: str = ""
        self.gateway_sw_version: str = ""
        self.gateway_mac: str = ""

        self._state_callbacks: list[Callable] = []
        self._token_update_callback: Callable[[str], None] | None = None
        self._running = False
        self._keepalive_task: asyncio.Task | None = None
        self._discovery_callback: Callable | None = None

    def set_token_update_callback(self, callback: Callable[[str], None]) -> None:
        """Register callback fired whenever refresh token changes (to persist it)."""
        self._token_update_callback = callback

    # ─── Token management ────────────────────────────────────────────────────

    async def _get_token(self) -> str:
        now = time.time()
        if self._access_token and now < self._token_expires_at - TOKEN_REFRESH_MARGIN:
            return self._access_token
        if self._refresh_token:
            try:
                return await self._refresh_access_token()
            except Exception:
                _LOGGER.warning(
                    "Vimar: refresh token failed, doing full login")
        return await self._login()

    async def _login(self) -> str:
        code_verifier, code_challenge = _pkce_pair()
        headers = {
            "User-Agent": USER_AGENT,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "it",
            "Accept-Encoding": "gzip, deflate",
        }

        async with aiohttp.ClientSession(headers=headers) as session:
            auth_params = {
                "client_id": VIMAR_CLIENT_ID,
                "redirect_uri": VIMAR_REDIRECT_URI,
                "response_type": "code",
                "scope": "openid offline_access",
                "code_challenge": code_challenge,
                "code_challenge_method": "S256",
            }
            async with session.get(
                VIMAR_OAUTH_AUTH_URL, params=auth_params, allow_redirects=True
            ) as resp:
                if resp.status != 200:
                    raise VimarAuthError(f"Login page failed ({resp.status})")
                login_page = await resp.text()
                login_url = str(resp.url)

            match = (
                re.search(r'id="hash"[^>]+value="([^"]+)"', login_page) or
                re.search(r'name="hash"[^>]+value="([^"]+)"', login_page) or
                re.search(r'value="([^"]+)"\s+id="hash"', login_page)
            )
            if not match:
                raise VimarAuthError("CSRF hash not found in login page")
            csrf_hash = match.group(1)

            login_data = aiohttp.FormData()
            login_data.add_field("email", self._username)
            login_data.add_field("passw", self._password)
            login_data.add_field("hash", csrf_hash)

            auth_code: str | None = None
            current_url = login_url
            current_data: aiohttp.FormData | None = login_data
            method = "POST"

            for _ in range(12):
                if method == "POST" and current_data is not None:
                    async with session.post(
                        current_url, data=current_data, allow_redirects=False
                    ) as r:
                        status = r.status
                        location = r.headers.get("Location", "")
                else:
                    async with session.get(current_url, allow_redirects=False) as r:
                        status = r.status
                        location = r.headers.get("Location", "")

                if status not in (301, 302, 303, 307, 308):
                    raise VimarAuthError(
                        f"Unexpected status {status} during redirect chain")

                if location.startswith(VIMAR_REDIRECT_URI):
                    m = re.search(r"code=([^&\s]+)", location)
                    if m:
                        auth_code = m.group(1)
                    break

                current_url = location
                current_data = None
                method = "GET"

            if not auth_code:
                raise VimarAuthError(
                    "Authorization code not found in redirect chain")

            token_data = {
                "grant_type": "authorization_code",
                "client_id": VIMAR_CLIENT_ID,
                "redirect_uri": VIMAR_REDIRECT_URI,
                "code": auth_code,
                "code_verifier": code_verifier,
            }
            async with session.post(VIMAR_AUTH_URL, data=token_data) as resp:
                if resp.status != 200:
                    text = await resp.text()
                    raise VimarAuthError(
                        f"Token exchange failed ({resp.status}): {text}")
                tokens = await resp.json()

        self._store_tokens(tokens)
        _LOGGER.info("Vimar: full login OK, refresh_token obtained: %s",
                     "yes" if self._refresh_token else "no")
        return self._access_token  # type: ignore[return-value]

    async def _refresh_access_token(self) -> str:
        """Use saved refresh token to get a new access token without full login."""
        async with aiohttp.ClientSession() as session:
            data = {
                "client_id": VIMAR_CLIENT_ID,
                "refresh_token": self._refresh_token,
                "grant_type": "refresh_token",
            }
            async with session.post(VIMAR_AUTH_URL, data=data) as resp:
                if resp.status != 200:
                    raise VimarAuthError(
                        f"Refresh token failed ({resp.status})")
                token_data = await resp.json()

        self._store_tokens(token_data)
        _LOGGER.info("Vimar: token refreshed successfully")
        return self._access_token  # type: ignore[return-value]

    def _store_tokens(self, tokens: dict) -> None:
        """Store tokens and notify callback to persist refresh token."""
        self._access_token = tokens["access_token"]
        new_refresh = tokens.get("refresh_token")
        if new_refresh:
            self._refresh_token = new_refresh
            if self._token_update_callback:
                self._token_update_callback(new_refresh)
        self._token_expires_at = time.time() + tokens.get("expires_in", 300)

        try:
            payload = tokens["access_token"].split(".")[1] + "=="
            jwt_data = json.loads(base64.urlsafe_b64decode(payload))
            self._user_uid = jwt_data.get("sub", "")
        except Exception:
            _LOGGER.warning("Vimar: could not extract useruid from JWT")

    # ─── WebSocket messaging ─────────────────────────────────────────────────

    def _next_msgid(self) -> str:
        mid = str(self._msgid)
        self._msgid += 1
        return mid

    async def _send(self, msg: dict) -> None:
        if self._ws is None:
            raise VimarConnectionError("WebSocket not connected")
        await self._ws.send_str(json.dumps(msg))

    async def _send_request(self, function: str, args: list, params: list | None = None) -> str:
        msgid = self._next_msgid()
        msg = {
            "type": "request",
            "function": function,
            "source": self._source_id,
            "target": self._duid,
            "token": self._session_token or "",
            "msgid": msgid,
            "args": args,
            "params": params or [],
        }
        await self._send(msg)
        return msgid

    # ─── Protocol ────────────────────────────────────────────────────────────

    async def _attach(self) -> None:
        msgid = self._next_msgid()
        msg = {
            "type": "request",
            "function": FUNC_ATTACH,
            "source": self._source_id,
            "target": self._duid,
            "token": self._client_token,
            "msgid": msgid,
            "args": [{
                "credential": {
                    "username": self._username,
                    "useruid": self._user_uid,
                    "password": "NOPWD",
                },
                "clientinfo": {
                    "manufacturertag": "Vimar",
                    "clienttag": "userapp",
                    "sfmodelversion": "1.0.0",
                    "lang": "it",
                    "protocolversion": "2.4",
                },
                "communication": {"ipaddress": ""},
            }],
            "params": [],
        }
        await self._send(msg)

    async def _register_idsf(self, idsf_list: list[dict]) -> None:
        if not idsf_list:
            return
        await self._send_request(FUNC_REGISTER, idsf_list)
        await self._send_request(FUNC_GETSTATUS, idsf_list)

    # ─── Message handling ─────────────────────────────────────────────────────

    async def _handle_message(self, raw: str) -> None:
        try:
            msg = json.loads(raw)
        except json.JSONDecodeError:
            return

        msg_type = msg.get("type")
        function = msg.get("function")
        error = msg.get("error", 0)
        # _LOGGER.warning(
        #     "VIMAR-DEBUG: msg_type=%s function=%s error=%s", msg_type, function, error)

        if error != 0:
            _LOGGER.error("Vimar: error in %s: %s",
                          function, msg.get("result"))
            return

        if msg_type == "response":
            await self._handle_response(function, msg)
        elif msg_type == "request":
            await self._handle_push(function, msg)

    async def _handle_response(self, function: str, msg: dict) -> None:
        result = msg.get("result", [])

        if function == FUNC_ATTACH:
            if result:
                info = result[0]
                self._session_token = info.get("token")
                self.plant_name = info.get("plantname", "")
                srv = info.get("serverinfo", {})
                self.gateway_sw_version = srv.get("softwareversion", "")
                self.gateway_mac = srv.get("mac", "")
                # _LOGGER.warning("VIMAR-DEBUG: attach OK plant=%r fw=%s — sending sfdiscovery",
                #                 self.plant_name, self.gateway_sw_version)
                await self._send_request(FUNC_SFDISCOVERY, [{"sfcategory": SF_CATEGORY_PLANT}])

        elif function == FUNC_SFDISCOVERY:
            # _LOGGER.warning("VIMAR-DEBUG: sfdiscovery result len=%d first_keys=%s",
            #                 len(result), list(result[0].keys()) if result else [])
            if result and isinstance(result[0], dict) and "sf" in result[0]:
                await self._process_plant_discovery(result)
            else:
                # _LOGGER.warning(
                #     "VIMAR-DEBUG: sfdiscovery — condition NOT met, skipped plant discovery")
                _LOGGER.debug("Vimar: BigData discovery: %s",
                              json.dumps(result)[:500])

        elif function == FUNC_GETSTATUS:
            await self._process_status_update(result)

        elif function in (FUNC_REGISTER, FUNC_KEEPALIVE, FUNC_DOACTION):
            pass

    async def _handle_push(self, function: str, msg: dict) -> None:
        if function == FUNC_CHANGESTATUS:
            await self._process_status_update(msg.get("args", []))

    async def _process_plant_discovery(self, result: list) -> None:
        # _LOGGER.warning(
        #     "VIMAR-DEBUG: _process_plant_discovery called, result items=%d", len(result))
        sf_list: list[dict] = []
        for item in result:
            if "sf" in item:
                sf_list.extend(item["sf"])
            elif "idsf" in item:
                sf_list.append(item)
        # _LOGGER.warning(
        #     "VIMAR-DEBUG: sf_list built, %d SF entries", len(sf_list))

        load_idsfs: set[int] = set()
        measure_idsfs: dict[int, int] = {}

        for sf in sf_list:
            idsf = sf.get("idsf")
            sstype = sf.get("sstype", "")
            if idsf is None:
                continue
            if sstype == "SS_Energy_Load":
                load_idsfs.add(idsf)
            elif sstype == "SS_Energy_Measure1P":
                load_idsf = idsf - IDSF_PAIR_OFFSET
                measure_idsfs[idsf] = load_idsf
                self.measure_to_load[idsf] = load_idsf

        idsf_to_register = []

        for sf in sf_list:
            idsf = sf.get("idsf")
            sstype = sf.get("sstype", "")
            if idsf is None:
                continue

            elements = sf.get("elements", [])
            sfetypes = [e["sfetype"] for e in elements if "sfetype" in e]
            initial_values = {
                e["sfetype"]: e["value"]
                for e in elements
                if e.get("sfetype") and e.get("value") is not None
            }

            if sstype == "SS_Energy_Measure1P":
                load_idsf = measure_idsfs.get(idsf)
                if load_idsf and load_idsf in load_idsfs:
                    if initial_values:
                        self.device_states.setdefault(
                            load_idsf, {}).update(initial_values)
                    reg_sfetypes = [
                        s for s in sfetypes if s.startswith("SFE_State_")]
                    if reg_sfetypes:
                        idsf_to_register.append(
                            {"idsf": idsf, "sfetype": reg_sfetypes})
                    continue

            device_type = self._classify_device(sfetypes, sstype)

            self.devices[idsf] = {
                "idsf": idsf,
                "name": sf.get("name", f"Device {idsf}"),
                "sftype": sf.get("sftype", ""),
                "sstype": sstype,
                "sfetypes": sfetypes,
                "device_type": device_type,
            }

            if device_type == "energy_manager":
                self.idsf_energy_manager = idsf

            if initial_values:
                self.device_states.setdefault(idsf, {}).update(initial_values)

            reg_sfetypes = [s for s in sfetypes if s.startswith("SFE_State_")]
            if reg_sfetypes:
                idsf_to_register.append(
                    {"idsf": idsf, "sfetype": reg_sfetypes})

        # _LOGGER.warning(
        #     "VIMAR-DEBUG: discovered %d devices total", len(self.devices))
        # for _idsf, _dev in self.devices.items():
        #     _LOGGER.warning("VIMAR-DEBUG: device idsf=%s name=%r sstype=%s type=%s",
        #                     _idsf, _dev.get("name"), _dev.get("sstype"), _dev.get("device_type"))
        await self._register_idsf(idsf_to_register)

        try:
            await self._send_request(FUNC_SFDISCOVERY, [{"sfcategory": SF_CATEGORY_BIGDATA}])
        except Exception:
            pass

        if self._discovery_callback:
            self._discovery_callback()
            self._discovery_callback = None

    def _classify_device(self, sfetypes: list[str], sstype: str) -> str:
        # _LOGGER.warning("VIMAR-DEBUG: _classify_device sstype=%r", sstype)
        if sstype == "SS_Clima_Zone":
            return "thermostat"
        if sstype == "SS_Light_Dimmer":
            return "dimmer"
        if sstype == "SS_Light_Switch":
            return "light"
        if sstype == "SS_Energy_LoadControl1P":
            return "energy_manager"
        if sstype == "SS_Energy_Load":
            return "load_control"
        if sstype == "SS_Shutter_Position":
            return "shutter"
        if sstype == "SS_SceneActivator_Activator":
            return "scene_activator_unused"  # non esposto come entità
        if sstype == "SS_Scene_Executor":
            return "scene"
        if SFE_STATE_SHUTTER in sfetypes:
            return "shutter"
        if SFE_STATE_BRIGHTNESS in sfetypes and SFE_STATE_ONOFF in sfetypes:
            return "dimmer"
        if SFE_STATE_ONOFF in sfetypes:
            return "light"
        if SFE_STATE_LOADS_PRIORITY in sfetypes:
            return "energy_manager"
        if SFE_STATE_LOAD_ID in sfetypes:
            return "load_control"
        if SFE_STATE_GLOBAL_ACTIVE_POWER in sfetypes:
            return "energy"
        return "unknown"

    async def _process_status_update(self, args: list) -> None:
        updated_idsf: list[int] = []
        for item in args:
            idsf = item.get("idsf")
            if idsf is None:
                continue

            target_idsf = self.measure_to_load.get(idsf, idsf)
            self.device_states.setdefault(target_idsf, {})
            for element in item.get("elements", []):
                sfetype = element.get("sfetype")
                value = element.get("value")
                if sfetype and value is not None:
                    self.device_states[target_idsf][sfetype] = value

            if target_idsf not in updated_idsf:
                updated_idsf.append(target_idsf)

        if updated_idsf:
            for callback in self._state_callbacks:
                callback(updated_idsf)

    # ─── Public API ───────────────────────────────────────────────────────────

    def register_state_callback(self, callback: Callable) -> None:
        self._state_callbacks.append(callback)

    def set_discovery_callback(self, callback: Callable) -> None:
        self._discovery_callback = callback

    def get_state(self, idsf: int, sfetype: str) -> Any | None:
        return self.device_states.get(idsf, {}).get(sfetype)

    async def turn_on(self, idsf: int) -> None:
        await self._send_request(FUNC_DOACTION, [{"idsf": idsf, "sfetype": SFE_CMD_ONOFF, "value": "On"}])

    async def turn_off(self, idsf: int) -> None:
        await self._send_request(FUNC_DOACTION, [{"idsf": idsf, "sfetype": SFE_CMD_ONOFF, "value": "Off"}])

    async def set_brightness(self, idsf: int, brightness: int) -> None:
        await self._send_request(FUNC_DOACTION, [{"idsf": idsf, "sfetype": SFE_CMD_BRIGHTNESS, "value": str(brightness)}])

    async def set_load(self, idsf: int, state: str) -> None:
        await self._send_request(FUNC_DOACTION, [{"idsf": idsf, "sfetype": SFE_CMD_LOAD, "value": state}])

    async def restore_load(self, idsf: int) -> None:
        await self.set_load(idsf, LOAD_STATE_AUTO)

    async def restore_all_loads(self) -> None:
        for idsf, device in self.devices.items():
            if device.get("device_type") == "load_control":
                await self.restore_load(idsf)

    async def open_cover(self, idsf: int) -> None:
        await self._send_request(FUNC_DOACTION, [{"idsf": idsf, "sfetype": SFE_CMD_SHUTTER, "value": SHUTTER_CMD_OPEN}])

    async def close_cover(self, idsf: int) -> None:
        await self._send_request(FUNC_DOACTION, [{"idsf": idsf, "sfetype": SFE_CMD_SHUTTER, "value": SHUTTER_CMD_CLOSE}])

    async def stop_cover(self, idsf: int) -> None:
        await self._send_request(FUNC_DOACTION, [{"idsf": idsf, "sfetype": SFE_CMD_SHUTTER, "value": SHUTTER_CMD_STOP}])

    async def set_cover_position(self, idsf: int, vimar_pos: int) -> None:
        """Set cover position. vimar_pos: 0=open, 100=closed."""
        await self._send_request(FUNC_DOACTION, [{"idsf": idsf, "sfetype": SFE_CMD_SHUTTER, "value": str(vimar_pos)}])

    async def execute_scene(self, idsf: int) -> None:
        await self._send_request(FUNC_DOACTION, [{"idsf": idsf, "sfetype": SFE_CMD_EXECUTE, "value": "Execute"}])

    # ─── Climate / thermostat ─────────────────────────────────────────────────

    async def set_climate_hvac_mode(self, idsf: int, vimar_mode: str) -> None:
        """Set the HVAC mode: 'Off', 'Auto', or 'Timed manual'."""
        await self._send_request(FUNC_DOACTION, [{"idsf": idsf, "sfetype": SFE_CMD_HVAC_MODE, "value": vimar_mode}])

    async def set_climate_change_over(self, idsf: int, change_over: str) -> None:
        """Switch between 'Heating' and 'Cooling' season."""
        await self._send_request(FUNC_DOACTION, [{"idsf": idsf, "sfetype": SFE_CMD_CHANGE_OVER_MODE, "value": change_over}])

    async def set_climate_temperature(self, idsf: int, temperature: float) -> None:
        """Set the ambient setpoint. Switches to 'Timed manual' if currently in 'Auto' program mode."""
        current_mode = self.get_state(idsf, SFE_STATE_HVAC_MODE)
        if current_mode == HVAC_MODE_VIMAR_AUTO:
            await self.set_climate_hvac_mode(idsf, HVAC_MODE_VIMAR_TIMED_MANUAL)
        await self._send_request(FUNC_DOACTION, [{"idsf": idsf, "sfetype": SFE_CMD_AMBIENT_SETPOINT, "value": str(temperature)}])

    async def set_climate_setpoint(self, idsf: int, cmd_sfetype: str, value: float) -> None:
        """Set any advanced thermostat temperature setpoint (reduction, absence, protection)."""
        await self._send_request(FUNC_DOACTION, [{"idsf": idsf, "sfetype": cmd_sfetype, "value": str(value)}])

    # ─── Connection lifecycle ─────────────────────────────────────────────────

    async def connect(self) -> None:
        self._running = True
        await self._connect_and_run()

    async def _connect_and_run(self) -> None:
        retry_delay = 5
        while self._running:
            try:
                token = await self._get_token()
                ws_url = f"{VIMAR_WS_URL}?duid={self._duid}&access_token={token}"
                # _LOGGER.warning(
                #     "VIMAR-DEBUG: connecting to WebSocket url=%s", ws_url[:60])

                async with aiohttp.ClientSession() as session:
                    async with session.ws_connect(
                        ws_url,
                        heartbeat=None,
                        timeout=aiohttp.ClientWSTimeout(ws_close=5),
                        headers={
                            "User-Agent": "okhttp/5.3.2",
                            "Upgrade": "websocket",
                            "Connection": "Upgrade",
                        },
                        compress=15,
                    ) as ws:
                        self._ws = ws
                        self._msgid = 9
                        self._client_token = _random_client_token()
                        retry_delay = 5

                        self._keepalive_task = asyncio.create_task(
                            self._keepalive_loop())
                        await self._attach()

                        async for msg in ws:
                            if msg.type == aiohttp.WSMsgType.TEXT:
                                await self._handle_message(msg.data)
                            elif msg.type == aiohttp.WSMsgType.ERROR:
                                _LOGGER.warning(
                                    "Vimar: WS error: %s", ws.exception())
                                break
                            elif msg.type in (aiohttp.WSMsgType.CLOSE, aiohttp.WSMsgType.CLOSED):
                                _LOGGER.info("Vimar: WS closed")
                                break

            except VimarAuthError as err:
                _LOGGER.error("Vimar: auth error: %s", err)
                self._running = False
                return
            except Exception as err:
                _LOGGER.error("Vimar: connection error: %s", err)
            finally:
                self._ws = None
                if self._keepalive_task:
                    self._keepalive_task.cancel()
                    self._keepalive_task = None

            if self._running:
                _LOGGER.info("Vimar: reconnecting in %ds", retry_delay)
                await asyncio.sleep(retry_delay)
                retry_delay = min(retry_delay * 2, 60)

    async def _keepalive_loop(self) -> None:
        while self._running and self._ws:
            await asyncio.sleep(KEEPALIVE_INTERVAL)
            try:
                if self._session_token:
                    await self._send_request(FUNC_KEEPALIVE, [])
            except Exception as err:
                _LOGGER.warning("Vimar: keepalive failed: %s", err)
                break

    async def disconnect(self) -> None:
        self._running = False
        if self._keepalive_task:
            self._keepalive_task.cancel()
        if self._ws:
            try:
                await self._send_request(FUNC_DETACH, [{"user": "logout"}])
                await self._ws.close()
            except Exception:
                pass
            self._ws = None
        _LOGGER.info("Vimar: disconnected")
