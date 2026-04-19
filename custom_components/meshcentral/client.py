"""MeshCentral WebSocket API client."""
from __future__ import annotations

import asyncio
import json
import logging
import ssl
import time
from typing import Any

import aiohttp

_LOGGER = logging.getLogger(__name__)

WS_CONTROL_PATH = "/control.ashx"
WS_TIMEOUT = 15


class MeshCentralClient:
    """Async WebSocket client for MeshCentral.

    Supports two auth methods:
      1. Login token (preferred — works with 2FA accounts)
         Set login_token to the hex token from My Account → Login Tokens.
      2. Username + password (only works without 2FA)
    """

    def __init__(
        self,
        host: str,
        port: int,
        username: str,
        password: str,
        use_ssl: bool = True,
        verify_ssl: bool = True,
        login_token: str | None = None,
    ) -> None:
        self._host = host
        self._port = port
        self._username = username
        self._password = password
        self._use_ssl = use_ssl
        self._verify_ssl = verify_ssl
        self._login_token = login_token
        self._session: aiohttp.ClientSession | None = None
        self._cookie: str | None = None

    @property
    def base_url(self) -> str:
        scheme = "https" if self._use_ssl else "http"
        return f"{scheme}://{self._host}:{self._port}"

    @property
    def ws_url(self) -> str:
        # ws:// is correct even on port 443 when tlsOffload=true
        scheme = "wss" if self._use_ssl else "ws"
        return f"{scheme}://{self._host}:{self._port}{WS_CONTROL_PATH}"

    def _ssl_context(self) -> ssl.SSLContext | bool:
        if not self._use_ssl:
            return False
        if not self._verify_ssl:
            ctx = ssl.create_default_context()
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
            return ctx
        return True

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()
        return self._session

    async def login(self) -> bool:
        """Authenticate — via login token or username+password."""
        if self._login_token:
            return await self._login_with_token()
        return await self._login_with_password()

    async def _login_with_token(self) -> bool:
        """Use a pre-created login token (bypasses 2FA)."""
        session = await self._get_session()
        ssl_ctx = self._ssl_context()
        login_url = f"{self.base_url}/login"
        payload = {
            "username": self._username,
            "token": self._login_token,
        }
        try:
            async with session.post(
                login_url,
                data=payload,
                ssl=ssl_ctx,
                allow_redirects=True,
                timeout=aiohttp.ClientTimeout(total=WS_TIMEOUT),
            ) as resp:
                _LOGGER.debug("Token login response: HTTP %s", resp.status)
                cookies = session.cookie_jar.filter_cookies(login_url)
                if cookies:
                    self._cookie = "; ".join(
                        f"{k}={v.value}" for k, v in cookies.items()
                    )
                    _LOGGER.debug("Token login OK, got session cookie")
                    return True
                _LOGGER.error("Token login: no cookie returned (status %s)", resp.status)
                return False
        except Exception as err:
            _LOGGER.error("Token login error: %s", err)
            return False

    async def _login_with_password(self) -> bool:
        """Username + password login (does not work if 2FA is enabled)."""
        session = await self._get_session()
        ssl_ctx = self._ssl_context()
        login_url = f"{self.base_url}/login"
        payload = {"username": self._username, "password": self._password}
        try:
            async with session.post(
                login_url,
                data=payload,
                ssl=ssl_ctx,
                allow_redirects=True,
                timeout=aiohttp.ClientTimeout(total=WS_TIMEOUT),
            ) as resp:
                cookies = session.cookie_jar.filter_cookies(login_url)
                if cookies:
                    self._cookie = "; ".join(
                        f"{k}={v.value}" for k, v in cookies.items()
                    )
                    return True
                _LOGGER.error("Password login failed: HTTP %s", resp.status)
                return False
        except Exception as err:
            _LOGGER.error("Password login error: %s", err)
            return False

    async def _send_recv(self, payload: dict, response_action: str) -> Any:
        """Connect WS, send a command, collect matching response."""
        session = await self._get_session()
        ssl_ctx = self._ssl_context()
        headers = {}
        if self._cookie:
            headers["Cookie"] = self._cookie

        try:
            async with session.ws_connect(
                self.ws_url,
                ssl=ssl_ctx,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=WS_TIMEOUT),
            ) as ws:
                await ws.send_str(json.dumps(payload))
                deadline = time.monotonic() + WS_TIMEOUT
                while time.monotonic() < deadline:
                    try:
                        msg = await asyncio.wait_for(ws.receive(), timeout=5)
                    except asyncio.TimeoutError:
                        break
                    if msg.type == aiohttp.WSMsgType.TEXT:
                        data = json.loads(msg.data)
                        if data.get("action") == response_action:
                            return data
                    elif msg.type in (
                        aiohttp.WSMsgType.CLOSED,
                        aiohttp.WSMsgType.ERROR,
                    ):
                        break
        except Exception as err:
            _LOGGER.error("WebSocket error: %s", err)
        return None

    async def get_devices(self) -> list[dict]:
        """Return list of all devices the user can access."""
        result = await self._send_recv(
            {"action": "nodes", "responseid": "ha-nodes"},
            "nodes",
        )
        if result is None:
            return []
        devices = []
        for mesh_id, node_list in result.get("nodes", {}).items():
            for node in node_list:
                node["_meshid"] = mesh_id
                devices.append(node)
        return devices

    async def get_device_groups(self) -> list[dict]:
        """Return list of device groups (meshes)."""
        result = await self._send_recv(
            {"action": "meshes", "responseid": "ha-meshes"},
            "meshes",
        )
        if result is None:
            return []
        return result.get("meshes", [])

    async def close(self) -> None:
        """Close underlying HTTP session."""
        if self._session and not self._session.closed:
            await self._session.close()
            self._session = None
