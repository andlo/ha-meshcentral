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

    Note on LoginKey (3FA): if the MeshCentral server has LoginKey enabled in
    config.json, ALL requests (including login POST and WebSocket) must include
    ?key=<loginkey> as a query parameter.  Pass the key via login_key here.
    This is separate from per-user Login Tokens (~t:... username format).
    """

    def __init__(
        self,
        host: str,
        port: int,
        username: str,
        password: str,
        use_ssl: bool = True,
        verify_ssl: bool = True,
        login_key: str | None = None,
    ) -> None:
        self._host = host
        self._port = port
        self._username = username
        self._password = password
        self._use_ssl = use_ssl
        self._verify_ssl = verify_ssl
        self._login_key = login_key or None
        self._session: aiohttp.ClientSession | None = None
        self._cookie: str | None = None
        self._ssl_ctx_cache: ssl.SSLContext | None = None

    @property
    def _key_param(self) -> str:
        """Return ?key=<loginkey> query string if LoginKey (3FA) is configured."""
        return f"?key={self._login_key}" if self._login_key else ""

    @property
    def base_url(self) -> str:
        """Base URL without path — used for constructing endpoint URLs."""
        scheme = "https" if self._use_ssl else "http"
        return f"{scheme}://{self._host}:{self._port}"

    @property
    def ws_url(self) -> str:
        """WebSocket URL for /control.ashx, with optional ?key= after the path."""
        # Use ws:// even on port 443 when tlsOffload=true
        scheme = "wss" if self._use_ssl else "ws"
        return f"{scheme}://{self._host}:{self._port}{WS_CONTROL_PATH}{self._key_param}"

    async def _ssl_context(self) -> ssl.SSLContext | bool:
        """Return the SSL context for requests, built off the event loop.

        ssl.create_default_context() does blocking disk I/O (loading the
        system's default CA certs), so it must not be called directly on
        the event loop — HA's blocking-call detector flags this, and on
        a busy instance it can stall/interfere with time-sensitive login
        and WebSocket request/response cycles. Built once and cached.
        """
        if not self._use_ssl:
            return False
        if not self._verify_ssl:
            if self._ssl_ctx_cache is None:
                loop = asyncio.get_event_loop()
                ctx = await loop.run_in_executor(None, ssl.create_default_context)
                ctx.check_hostname = False
                ctx.verify_mode = ssl.CERT_NONE
                self._ssl_ctx_cache = ctx
            return self._ssl_ctx_cache
        return True

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()
        return self._session

    async def login(self) -> bool:
        """Authenticate with MeshCentral and store session cookie."""
        session = await self._get_session()
        ssl_ctx = await self._ssl_context()
        login_url = f"{self.base_url}/login{self._key_param}"
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
        ssl_ctx = await self._ssl_context()
        headers = {"Cookie": self._cookie} if self._cookie else {}
        action = payload.get("action", "?")
        opened = time.monotonic()
        _LOGGER.debug("_send_recv: opening control.ashx WS for action=%s", action)
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
                        # The 5s receive() timeout is only a polling interval
                        # so we can re-check the overall deadline below — not
                        # the actual request timeout. Keep waiting for a
                        # response until WS_TIMEOUT actually elapses instead
                        # of giving up on the first slow-but-valid response.
                        continue
                    if msg.type == aiohttp.WSMsgType.TEXT:
                        data = json.loads(msg.data)
                        if data.get("action") == response_action:
                            _LOGGER.debug(
                                "_send_recv: action=%s got response in %.2fs",
                                action,
                                time.monotonic() - opened,
                            )
                            return data
                    elif msg.type in (
                        aiohttp.WSMsgType.CLOSED,
                        aiohttp.WSMsgType.ERROR,
                    ):
                        _LOGGER.debug(
                            "_send_recv: action=%s socket %s after %.2fs, no response",
                            action,
                            msg.type.name,
                            time.monotonic() - opened,
                        )
                        break
                else:
                    _LOGGER.debug(
                        "_send_recv: action=%s timed out after %.2fs waiting for response",
                        action,
                        time.monotonic() - opened,
                    )
        except Exception as err:
            _LOGGER.error(
                "_send_recv: action=%s WebSocket error after %.2fs: %s",
                action,
                time.monotonic() - opened,
                err,
            )
        return None

    async def _send_command_recv(
        self,
        payload: dict,
        response_id: str,
        wait_for_output: bool,
    ) -> Any:
        """Open a WebSocket for runcommands and match its reply.

        MeshCentral answers runcommands in one of two shapes: an immediate
        ``action: runcommands`` acknowledgement that the command was
        dispatched (result usually just "OK"), and — once the remote
        process actually exits — a separate ``action: msg`` message with
        ``type: runcommands`` carrying the real output. Which one counts
        as "done" depends on wait_for_output: False accepts the immediate
        ack (fire-and-forget, e.g. for GUI apps that never exit), True
        holds out for the delayed message with actual output.

        Credit: @Onoitsu2, PR #33.
        """
        session = await self._get_session()
        ssl_ctx = await self._ssl_context()
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
                        continue

                    if msg.type == aiohttp.WSMsgType.TEXT:
                        try:
                            data = json.loads(msg.data)
                        except (TypeError, json.JSONDecodeError):
                            continue

                        if data.get("responseid") != response_id:
                            continue

                        if not wait_for_output:
                            if data.get("action") == "runcommands":
                                return data
                            continue

                        if data.get("type") == "runcommands":
                            return data

                        if data.get("action") == "runcommands":
                            result = data.get("result")
                            if (
                                result not in (None, "OK", "ok")
                                or "output" in data
                                or "value" in data
                            ):
                                return data

                    elif msg.type in (
                        aiohttp.WSMsgType.CLOSED,
                        aiohttp.WSMsgType.ERROR,
                    ):
                        break
        except Exception as err:
            _LOGGER.error("Command WebSocket error: %s", err)
        return None

    async def get_devices(self) -> list[dict]:
        """Return all devices the authenticated user can access."""
        result = await self._send_recv(
            {"action": "nodes", "responseid": "ha-nodes"},
            "nodes",
        )
        if result is None:
            # Distinguish "request failed" from "genuinely zero devices" —
            # returning [] here would let a failed/timed-out request look
            # identical to an empty account, which on first load (before
            # the coordinator has any prior data to compare against) was
            # silently accepted as valid and left every derived sensor
            # confidently showing 0 instead of unavailable (#30).
            raise TimeoutError("MeshCentral did not respond to the 'nodes' request")
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

    async def get_users(self) -> list[dict]:
        """Return all user accounts on the server.

        Requires site-admin rights. Unlike serverversion/serverupdate, this
        works fine for Login Token sessions too — confirmed against a live
        server.
        """
        result = await self._send_recv(
            {"action": "users", "responseid": "ha-users"},
            "users",
        )
        if result is None:
            return []
        return result.get("users", [])

    async def get_installed_server_version(self) -> str | None:
        """Read the installed MeshCentral version from serverconsole info.

        Faster and more broadly available than get_server_version_tags():
        "serverconsole info" returns MeshCentral's in-memory current version
        immediately, without waiting on an npm dist-tag lookup (which can be
        slow or fail outright on a server with restricted/no internet
        access). Uses its own short-lived WS connection since the reply is
        matched by "tag", not the "responseid" scheme _send_recv expects.

        Credit: @Onoitsu2, PR #34.
        """
        session = await self._get_session()
        ssl_ctx = await self._ssl_context()
        headers = {"Cookie": self._cookie} if self._cookie else {}
        tag = f"ha-server-info-{time.monotonic_ns()}"
        try:
            async with session.ws_connect(
                self.ws_url,
                ssl=ssl_ctx,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=8),
            ) as ws:
                await ws.send_str(
                    json.dumps(
                        {
                            "action": "serverconsole",
                            "value": "info",
                            "tag": tag,
                        }
                    )
                )
                deadline = time.monotonic() + 8
                while time.monotonic() < deadline:
                    try:
                        msg = await asyncio.wait_for(ws.receive(), timeout=2)
                    except asyncio.TimeoutError:
                        continue

                    if msg.type == aiohttp.WSMsgType.TEXT:
                        try:
                            data = json.loads(msg.data)
                        except (TypeError, json.JSONDecodeError):
                            continue
                        if (
                            data.get("action") != "serverconsole"
                            or data.get("tag") != tag
                        ):
                            continue

                        value = data.get("value")
                        if not isinstance(value, str):
                            return None
                        try:
                            info = json.loads(value)
                        except json.JSONDecodeError:
                            return None
                        version = info.get("meshVersion")
                        if not isinstance(version, str) or not version:
                            return None
                        return (
                            version[1:]
                            if version.lower().startswith("v")
                            else version
                        )

                    if msg.type in (
                        aiohttp.WSMsgType.CLOSED,
                        aiohttp.WSMsgType.ERROR,
                    ):
                        break
        except Exception as err:
            _LOGGER.debug("MeshCentral serverconsole info failed: %s", err)
        return None

    async def get_server_version_tags(self) -> dict | None:
        """Return the server's own version info, if this session is allowed to.

        MeshCentral only answers the "serverversion" action for full site
        administrators authenticated with a regular username/password login —
        it is explicitly refused for sessions using a Login Token (the
        "~t:..." username used to bypass 2FA), and requires the account's
        "update" site-right. Returns None if unavailable for either reason;
        callers should treat that as "unknown", not an error.

        On success, the dict has a "current" key with the installed version,
        and usually a "latest" key with the latest published version (from
        the server's own npm dist-tag check) — but "latest" may be absent if
        the server itself has no internet/npm access.
        """
        result = await self._send_recv(
            {"action": "serverversion", "responseid": "ha-serverversion"},
            "serverversion",
        )
        if result and isinstance(result.get("tags"), dict):
            return result["tags"]
        return None

    async def get_sysinfo(self, node_id: str) -> dict | None:
        """Return full hardware/sysinfo for a single device."""
        result = await self._send_recv(
            {
                "action": "getsysinfo",
                "nodeid": node_id,
                "responseid": "ha-sysinfo",
            },
            "getsysinfo",
        )
        if result:
            return result.get("hardware")
        return None

    async def send_power_action(self, node_id: str, action_type: int) -> bool:
        """Send a power command to a device.

        action_type:
            1 = Sleep
            2 = Reboot
            3 = Shutdown / Power off
            5 = Hibernate (Windows only)
        """
        result = await self._send_recv(
            {
                "action": "poweraction",
                "nodeid": node_id,
                "actiontype": action_type,
                "responseid": "ha-pwr",
            },
            "poweraction",
        )
        return result is not None

    async def send_wol(self, node_id: str) -> str | None:
        """Send Wake-on-LAN via MeshCentral wakedevices action.

        MeshCentral finds all online agents on the same network and uses
        them to broadcast the WOL magic packet to the target device.
        Returns a result string like "Used 2 device(s) to send wake packets"
        or None on failure.
        """
        result = await self._send_recv(
            {
                "action": "wakedevices",
                "nodeids": [node_id],
                "responseid": "ha-wol",
            },
            "wakedevices",
        )
        if result:
            return result.get("result", "ok")
        return None

    async def run_command(
        self,
        node_id: str,
        command: str,
        run_as_user: bool = False,
        wait_for_output: bool = True,
        powershell: bool = False,
    ) -> str | None:
        """Run a shell or PowerShell command through the MeshCentral agent.

        Returns command output as string, or None on timeout/failure.
        """
        response_id = f"ha-cmd-{time.monotonic_ns()}"
        result = await self._send_command_recv(
            {
                "action": "runcommands",
                "nodeids": [node_id],
                "type": 2 if powershell else 0,
                "cmds": command,
                "responseid": response_id,
                "runAsUser": 2 if run_as_user else 0,
                "reply": wait_for_output,
            },
            response_id,
            wait_for_output,
        )
        if result is not None:
            return result.get(
                "result",
                result.get("output", result.get("value", "")),
            )
        return None

    async def close(self) -> None:
        """Close the underlying HTTP session."""
        if self._session and not self._session.closed:
            await self._session.close()
            self._session = None
