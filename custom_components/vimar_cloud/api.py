"""Vimar Cloud WebSocket API client."""
from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import logging
import re
import secrets
import time
from urllib.parse import parse_qs, urlsplit
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
    HTTP_TIMEOUT_SECONDS,
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
    SFE_CMD_TIMED_DYNAMIC_MODE,
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
    return secrets.token_hex(8)


def _random_client_token() -> str:
    return secrets.token_urlsafe(12)


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
        self.automation_to_measure: dict[int, int] = {}
        self.idsf_energy_manager: int | None = None

        self.plant_name: str = ""
        self.gateway_sw_version: str = ""
        self.gateway_mac: str = ""
        self.gateway_device_id: str | None = None

        self._state_callbacks: list[Callable] = []
        self._token_update_callback: Callable[[str], None] | None = None
        self._running = False
        self._keepalive_task: asyncio.Task | None = None
        self._discovery_callback: Callable | None = None
        self._token_lock = asyncio.Lock()
        self._pending_requests: dict[str, asyncio.Future[dict[str, Any]]] = {}
        self._request_timeout = 15.0

    def set_token_update_callback(self, callback: Callable[[str], None]) -> None:
        self._token_update_callback = callback

    # ─── Token management ────────────────────────────────────────────────────

    async def _get_token(self) -> str:
        now = time.time()
        if self._access_token and now < self._token_expires_at - TOKEN_REFRESH_MARGIN:
            _LOGGER.debug("Vimar auth: using cached access token")
            return self._access_token

        if self._refresh_token:
            _LOGGER.debug("Vimar auth: access token unavailable/expired, trying refresh token")
            try:
                token = await self._refresh_access_token()
                _LOGGER.debug("Vimar auth: refresh token succeeded")
                return token
            except Exception as err:
                _LOGGER.warning(
                    "Vimar: refresh token failed, doing full login (%s)",
                    type(err).__name__,
                )

        _LOGGER.debug("Vimar auth: performing full login")
        return await self._login()

    async def _login(self) -> str:
        _LOGGER.debug("Vimar auth: full login started")
        code_verifier, code_challenge = _pkce_pair()
        headers = {
            "User-Agent": USER_AGENT,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "it",
            "Accept-Encoding": "gzip, deflate",
        }

        timeout = aiohttp.ClientTimeout(total=HTTP_TIMEOUT_SECONDS, connect=10)
        async with aiohttp.ClientSession(headers=headers, timeout=timeout) as session:
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
                    raise VimarAuthError(f"Unexpected status {status} during redirect chain")

                if location.startswith(VIMAR_REDIRECT_URI):
                    query = parse_qs(urlsplit(location).query)
                    auth_code = query.get("code", [None])[0]
                    error = query.get("error", [None])[0]
                    if error:
                        raise VimarAuthError(f"Authorization failed ({error})")
                    break

                current_url = location
                current_data = None
                method = "GET"

            if not auth_code:
                raise VimarAuthError("Authorization code not found in redirect chain")

            token_data = {
                "grant_type": "authorization_code",
                "client_id": VIMAR_CLIENT_ID,
                "redirect_uri": VIMAR_REDIRECT_URI,
                "code": auth_code,
                "code_verifier": code_verifier,
            }
            async with session.post(VIMAR_AUTH_URL, data=token_data) as resp:
                if resp.status != 200:
                    raise VimarAuthError(f"Token exchange failed ({resp.status})")
                tokens = await resp.json()
                if not isinstance(tokens, dict) or not tokens.get("access_token"):
                    raise VimarAuthError("Token exchange returned an invalid response")

        self._store_tokens(tokens)
        _LOGGER.info("Vimar: full login OK, refresh_token obtained: %s", "yes" if self._refresh_token else "no")
        _LOGGER.debug("Vimar auth: full login succeeded")
        return self._access_token  # type: ignore[return-value]

    async def _refresh_access_token(self) -> str:
        _LOGGER.debug("Vimar auth: refresh token request started")
        timeout = aiohttp.ClientTimeout(total=HTTP_TIMEOUT_SECONDS, connect=10)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            data = {
                "client_id": VIMAR_CLIENT_ID,
                "refresh_token": self._refresh_token,
                "grant_type": "refresh_token",
            }
            async with session.post(VIMAR_AUTH_URL, data=data) as resp:
                if resp.status != 200:
                    raise VimarAuthError(f"Refresh token failed ({resp.status})")
                token_data = await resp.json()
                if not isinstance(token_data, dict) or not token_data.get("access_token"):
                    raise VimarAuthError("Refresh token returned an invalid response")

        self._store_tokens(token_data)
        _LOGGER.info("Vimar: token refreshed successfully")
        return self._access_token  # type: ignore[return-value]

    def _store_tokens(self, tokens: dict) -> None:
        access_token = tokens.get("access_token")
        if not isinstance(access_token, str) or not access_token:
            raise VimarAuthError("Missing access token")
        self._access_token = access_token
        new_refresh = tokens.get("refresh_token")
        if new_refresh:
            self._refresh_token = new_refresh
            if self._token_update_callback:
                self._token_update_callback(new_refresh)
        expires_in = tokens.get("expires_in", 300)
        try:
            expires_in = max(1, float(expires_in))
        except (TypeError, ValueError):
            expires_in = 300
        self._token_expires_at = time.time() + expires_in

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

    async def _send_request(
        self,
        function: str,
        args: list,
        params: list | None = None,
        *,
        wait_response: bool = False,
        timeout: float | None = None,
    ) -> str:
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
        future: asyncio.Future[dict[str, Any]] | None = None
        if wait_response:
            future = asyncio.get_running_loop().create_future()
            self._pending_requests[msgid] = future
        try:
            await self._send(msg)
            if future is not None:
                await asyncio.wait_for(
                    future, timeout=timeout if timeout is not None else self._request_timeout
                )
        except asyncio.CancelledError:
            raise
        except Exception:
            self._pending_requests.pop(msgid, None)
            raise
        finally:
            if future is not None and future.done():
                self._pending_requests.pop(msgid, None)
        return msgid

    async def _send_command(self, args: list, timeout: float | None = None) -> None:
        await self._send_request(
            FUNC_DOACTION, args, wait_response=True, timeout=timeout
        )

    def _fail_pending_requests(self, error: Exception) -> None:
        pending = self._pending_requests
        self._pending_requests = {}
        for future in pending.values():
            if not future.done():
                future.set_exception(error)

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

        if not isinstance(msg, dict):
            return

        msg_type = msg.get("type")
        function = msg.get("function")
        error = msg.get("error", 0)

        if error != 0:
            _LOGGER.error("Vimar: error in %s: %s", function, msg.get("result"))
            if msg_type == "response":
                msgid = msg.get("msgid")
                future = self._pending_requests.pop(str(msgid), None) if msgid is not None else None
                if future is not None and not future.done():
                    future.set_exception(VimarConnectionError(
                        f"Vimar rejected {function} (error {error})"
                    ))
            return

        if msg_type == "response":
            await self._handle_response(function, msg)
        elif msg_type == "request":
            await self._handle_push(function, msg)

    async def _handle_response(self, function: str, msg: dict) -> None:
        result = msg.get("result", [])
        if result is None:
            result = []
        if not isinstance(result, list):
            _LOGGER.warning("Vimar: unexpected response payload for %s", function)
            result = []
        msgid = msg.get("msgid")
        future = self._pending_requests.pop(str(msgid), None) if msgid is not None else None
        if future is not None and not future.done():
            future.set_result(msg)

        if function == FUNC_ATTACH:
            if result:
                info = result[0]
                self._session_token = info.get("token")
                self.plant_name = info.get("plantname", "")
                srv = info.get("serverinfo", {})
                self.gateway_sw_version = srv.get("softwareversion", "")
                self.gateway_mac = srv.get("mac", "")
                await self._send_request(FUNC_SFDISCOVERY, [{"sfcategory": SF_CATEGORY_PLANT}])

        elif function == FUNC_SFDISCOVERY:
            if result and isinstance(result[0], dict) and "sf" in result[0]:
                await self._process_plant_discovery(result)
            else:
                _LOGGER.debug("Vimar: BigData discovery: %s", json.dumps(result)[:500])

        elif function == FUNC_GETSTATUS:
            await self._process_status_update(result)

        elif function in (FUNC_REGISTER, FUNC_KEEPALIVE, FUNC_DOACTION):
            pass

    async def _handle_push(self, function: str, msg: dict) -> None:
        if function == FUNC_CHANGESTATUS:
            await self._process_status_update(msg.get("args", []))

    async def _process_plant_discovery(self, result: list) -> None:
        sf_list: list[dict] = []
        for item in result:
            if not isinstance(item, dict):
                continue
            idambient = item.get("idambient")
            if "sf" in item:
                if not isinstance(item["sf"], list):
                    continue
                for sf in item["sf"]:
                    if not isinstance(sf, dict):
                        continue
                    sf["_idambient"] = idambient
                    sf_list.append(sf)
            elif "idsf" in item:
                item["_idambient"] = idambient
                sf_list.append(item)

        load_idsfs: set[int] = set()
        automation_by_ambient_name: dict[tuple[Any, str], int] = {}
        measure_sfs: list[dict] = []

        for sf in sf_list:
            idsf = sf.get("idsf")
            sstype = sf.get("sstype", "")
            amb = sf.get("_idambient")
            name = sf.get("name", "")
            if not isinstance(idsf, int):
                continue

            if sstype == "SS_Energy_Load":
                load_idsfs.add(idsf)
            elif sstype == "SS_Automation_OnOff":
                automation_by_ambient_name[(amb, name)] = idsf
            elif sstype == "SS_Energy_Measure1P":
                measure_sfs.append(sf)

        for sf in measure_sfs:
            idsf = sf.get("idsf")
            amb = sf.get("_idambient")
            name = sf.get("name", "")
            if not isinstance(idsf, int):
                continue

            paired_load_idsf = idsf - IDSF_PAIR_OFFSET
            if paired_load_idsf in load_idsfs:
                self.measure_to_load[idsf] = paired_load_idsf
            elif (amb, name) in automation_by_ambient_name:
                auto_idsf = automation_by_ambient_name[(amb, name)]
                self.measure_to_load[idsf] = auto_idsf
                self.automation_to_measure[auto_idsf] = idsf

        idsf_to_register = []

        for sf in sf_list:
            idsf = sf.get("idsf")
            sstype = sf.get("sstype", "")
            if not isinstance(idsf, int):
                continue

            elements = sf.get("elements", [])
            if not isinstance(elements, list):
                elements = []
            sfetypes = [
                e["sfetype"] for e in elements
                if isinstance(e, dict) and isinstance(e.get("sfetype"), str)
            ]
            initial_values = {
                e["sfetype"]: e["value"]
                for e in elements
                if isinstance(e, dict)
                and e.get("sfetype")
                and e.get("value") is not None
            }

            if sstype == "SS_Energy_Measure1P":
                target_idsf = self.measure_to_load.get(idsf)
                if target_idsf:
                    if initial_values:
                        self.device_states.setdefault(target_idsf, {}).update(initial_values)
                        self.device_states.setdefault(idsf, {}).update(initial_values)
                    reg_sfetypes = [s for s in sfetypes if s.startswith("SFE_State_")]
                    if reg_sfetypes:
                        idsf_to_register.append({"idsf": idsf, "sfetype": reg_sfetypes})
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
                idsf_to_register.append({"idsf": idsf, "sfetype": reg_sfetypes})

        await self._register_idsf(idsf_to_register)

        for measure_idsf in self.measure_to_load.keys():
            try:
                await self._send_command(
                    [{"idsf": measure_idsf, "sfetype": SFE_CMD_TIMED_DYNAMIC_MODE, "value": "Start"}]
                )
            except Exception:
                pass

        try:
            await self._send_request(FUNC_SFDISCOVERY, [{"sfcategory": SF_CATEGORY_BIGDATA}])
        except Exception:
            pass

        if self._discovery_callback:
            self._discovery_callback()
            self._discovery_callback = None

    def _classify_device(self, sfetypes: list[str], sstype: str) -> str:
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
        if sstype == "SS_Automation_OnOff":
            return "automation_switch"
        if sstype == "SS_SceneActivator_Activator":
            return "scene_activator_unused"
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
        if not isinstance(args, list):
            return

        for item in args:
            if not isinstance(item, dict):
                continue
            idsf = item.get("idsf")
            if not isinstance(idsf, int):
                continue

            target_idsf = self.measure_to_load.get(idsf, idsf)
            self.device_states.setdefault(target_idsf, {})
            self.device_states.setdefault(idsf, {})

            elements = item.get("elements", [])
            if not isinstance(elements, list):
                continue
            for element in elements:
                if not isinstance(element, dict):
                    continue
                sfetype = element.get("sfetype")
                value = element.get("value")
                if sfetype and value is not None:
                    self.device_states[target_idsf][sfetype] = value
                    self.device_states[idsf][sfetype] = value

            if target_idsf not in updated_idsf:
                updated_idsf.append(target_idsf)
            if idsf not in updated_idsf:
                updated_idsf.append(idsf)

        if updated_idsf:
            for callback in tuple(self._state_callbacks):
                try:
                    callback(updated_idsf)
                except Exception:
                    _LOGGER.exception("Vimar: state callback failed")

    # ─── Public API ───────────────────────────────────────────────────────────

    def register_state_callback(self, callback: Callable) -> None:
        if callback not in self._state_callbacks:
            self._state_callbacks.append(callback)

    def unregister_state_callback(self, callback: Callable) -> None:
        try:
            self._state_callbacks.remove(callback)
        except ValueError:
            pass

    def set_discovery_callback(self, callback: Callable) -> None:
        self._discovery_callback = callback

    def get_state(self, idsf: int, sfetype: str) -> Any | None:
        return self.device_states.get(idsf, {}).get(sfetype)

    async def turn_on(self, idsf: int) -> None:
        await self._send_command([{"idsf": idsf, "sfetype": SFE_CMD_ONOFF, "value": "On"}])

    async def turn_off(self, idsf: int) -> None:
        await self._send_command([{"idsf": idsf, "sfetype": SFE_CMD_ONOFF, "value": "Off"}])

    async def set_brightness(self, idsf: int, brightness: int) -> None:
        await self._send_command([{"idsf": idsf, "sfetype": SFE_CMD_BRIGHTNESS, "value": str(brightness)}])

    async def set_load(self, idsf: int, state: str) -> None:
        await self._send_command([{"idsf": idsf, "sfetype": SFE_CMD_LOAD, "value": state}])

    async def restore_load(self, idsf: int) -> None:
        await self.set_load(idsf, LOAD_STATE_AUTO)

    async def restore_all_loads(self) -> None:
        for idsf, device in self.devices.items():
            if device.get("device_type") == "load_control":
                await self.restore_load(idsf)

    async def open_cover(self, idsf: int) -> None:
        await self._send_command([{"idsf": idsf, "sfetype": SFE_CMD_SHUTTER, "value": SHUTTER_CMD_OPEN}])

    async def close_cover(self, idsf: int) -> None:
        await self._send_command([{"idsf": idsf, "sfetype": SFE_CMD_SHUTTER, "value": SHUTTER_CMD_CLOSE}])

    async def stop_cover(self, idsf: int) -> None:
        await self._send_command([{"idsf": idsf, "sfetype": SFE_CMD_SHUTTER, "value": SHUTTER_CMD_STOP}])

    async def set_cover_position(self, idsf: int, vimar_pos: int) -> None:
        await self._send_command([{"idsf": idsf, "sfetype": SFE_CMD_SHUTTER, "value": str(vimar_pos)}])

    async def execute_scene(self, idsf: int) -> None:
        await self._send_command([{"idsf": idsf, "sfetype": SFE_CMD_EXECUTE, "value": "Execute"}])

    async def turn_on_automation(self, idsf: int) -> None:
        await self._send_command([{"idsf": idsf, "sfetype": SFE_CMD_ONOFF, "value": "On"}])
        measure_idsf = self.automation_to_measure.get(idsf)
        if measure_idsf:
            try:
                await self._send_command(
                    [{"idsf": measure_idsf, "sfetype": SFE_CMD_TIMED_DYNAMIC_MODE, "value": "Start"}]
                )
            except Exception:
                pass

    async def turn_off_automation(self, idsf: int) -> None:
        await self._send_command([{"idsf": idsf, "sfetype": SFE_CMD_ONOFF, "value": "Off"}])

    # ─── Climate / thermostat ─────────────────────────────────────────────────

    async def set_climate_hvac_mode(self, idsf: int, vimar_mode: str) -> None:
        await self._send_command([{"idsf": idsf, "sfetype": SFE_CMD_HVAC_MODE, "value": vimar_mode}])

    async def set_climate_change_over(self, idsf: int, change_over: str) -> None:
        await self._send_command([{"idsf": idsf, "sfetype": SFE_CMD_CHANGE_OVER_MODE, "value": change_over}])

    async def set_climate_temperature(self, idsf: int, temperature: float) -> None:
        current_mode = self.get_state(idsf, SFE_STATE_HVAC_MODE)
        if current_mode == HVAC_MODE_VIMAR_AUTO:
            await self.set_climate_hvac_mode(idsf, HVAC_MODE_VIMAR_TIMED_MANUAL)
        await self._send_command([{"idsf": idsf, "sfetype": SFE_CMD_AMBIENT_SETPOINT, "value": str(temperature)}])

    async def set_climate_setpoint(self, idsf: int, cmd_sfetype: str, value: float) -> None:
        await self._send_command([{"idsf": idsf, "sfetype": cmd_sfetype, "value": str(value)}])

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

                        self._keepalive_task = asyncio.create_task(self._keepalive_loop())
                        await self._attach()

                        async for msg in ws:
                            if msg.type == aiohttp.WSMsgType.TEXT:
                                await self._handle_message(msg.data)
                            elif msg.type == aiohttp.WSMsgType.ERROR:
                                _LOGGER.warning("Vimar: WS error: %s", ws.exception())
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
                self._session_token = None
                self._fail_pending_requests(VimarConnectionError("WebSocket disconnected"))
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