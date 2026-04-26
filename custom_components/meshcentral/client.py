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

    Authenticates via username + password. If 2FA is enabled on the account,
    create a Login Token in MeshCentral → My Account → Login Tokens and use
    the generated username (~t:...) and password as credentials here.

    Note on tlsOffload: if MeshCentral runs behind a reverse proxy with
    tlsOffload=true, set use_ssl=False even if the port is 443. The server
    accepts plain HTTP/WS on that port while the proxy handles TLS externally.
    """

    def __init__(
        self,
        host: str,
        port: int,
        username: str,
        password: str,
        use_ssl: bool = True,
        verify_ssl: bool = True,
    ) -> None:
        self._host = host
        self._port = port
        self._username = username
        self._password = password
        self._use_ssl = use_ssl
        self._verify_ssl = verify_ssl
        self._session: aiohttp.ClientSession | None = None
        self._cookie: str | None = None

    @property
    def base_url(self) -> str:
        scheme = "https" if self._use_ssl else "http"
        return f"{scheme}://{self._host}:{self._port}"

    @property
    def ws_url(self) -> str:
        # Use ws:// even on port 443 when tlsOffload=true
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
        """Authenticate with MeshCentral and store session cookie."""
        session = await self._get_session()
        ssl_ctx = self._ssl_context()
        login_url = f"{self.base_url}/login"
        payload = {"username": self._username, "password": self._password}
        _LOGGER.debug("Logging in to MeshCentral at %s", login_url)
        try:
            async with session.post(
                login_url,
                data=payload,
                ssl=ssl_ctx,
                allow_redirects=False,
                timeout=aiohttp.ClientTimeout(total=WS_TIMEOUT),
            ) as resp:
                _LOGGER.debug("Login response: HTTP %s", resp.status)
                # Read Set-Cookie directly from raw headers — aiohttp's cookie
                # jar silently drops cookies on non-standard port combinations
                cookies = []
                for name, val in resp.raw_headers:
                    if name.lower() == b"set-cookie":
                        cookie_pair = val.decode().split(";")[0].strip()
                        cookies.append(cookie_pair)
                if cookies:
                    self._cookie = "; ".join(cookies)
                    _LOGGER.debug("Login successful")
                    return True
                _LOGGER.error(
                    "Login failed: HTTP %s returned no session cookie", resp.status
                )
                return False
        except Exception as err:
            _LOGGER.error("Login error: %s", err)
            return False

    async def _send_recv(self, payload: dict, response_action: str) -> Any:
        """Open a WebSocket, send a command, and return the matching response."""
        session = await self._get_session()
        ssl_ctx = self._ssl_context()
        headers = {"Cookie": self._cookie} if self._cookie else {}
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
        """Return all devices the authenticated user can access."""
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
        _LOGGER.debug("Fetched %d device(s) from MeshCentral", len(devices))
        return devices

    async def get_device_groups(self) -> list[dict]:
        """Return all device groups (meshes)."""
        result = await self._send_recv(
            {"action": "meshes", "responseid": "ha-meshes"},
            "meshes",
        )
        if result is None:
            return []
        return result.get("meshes", [])

    async def send_power_action(self, node_id: str, action_type: int) -> bool:
        """Send a power command to a device.

        action_type:
            1 = Sleep
            2 = Reboot
            3 = Shutdown / Power off
            4 = Wake-on-LAN
            5 = Hibernate (Windows only)
        """
        result = await self._send_recv(
            {
                "action": "poweraction",
                "nodeid": node_id,
                "actiontype": action_type,
                "responseid": f"ha-pwr-{node_id}",
            },
            "poweraction",
        )
        return result is not None

    async def close(self) -> None:
        """Close the underlying HTTP session."""
        if self._session and not self._session.closed:
            await self._session.close()
            self._session = None
