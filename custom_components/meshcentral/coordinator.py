"""DataUpdateCoordinator for MeshCentral with real-time WebSocket push."""
from __future__ import annotations

import asyncio
import json
import logging
from datetime import timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_PORT, CONF_USERNAME
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .client import MeshCentralClient
from .const import (
    CONF_HW_SCAN_INTERVAL,
    CONF_LOGIN_KEY,
    CONF_MAIN_SCAN_INTERVAL,
    CONF_USE_SSL,
    CONF_VERIFY_SSL,
    DEFAULT_MAIN_SCAN_INTERVAL,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)


class MeshCentralCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Coordinator that combines initial polling with real-time WS event push.

    Strategy:
      1. On startup: poll full device list via nodes action.
      2. Start a persistent WebSocket listener task that receives nodeconnect
         and changenode events and merges them into coordinator.data instantly.
      3. Keep a 5-minute background poll as fallback in case WS drops events.
    """

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        minutes = entry.options.get(CONF_MAIN_SCAN_INTERVAL, DEFAULT_MAIN_SCAN_INTERVAL)
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(minutes=minutes),  # fallback poll behind WS push
        )
        self.entry = entry
        self.client = MeshCentralClient(
            host=entry.data[CONF_HOST],
            port=entry.data[CONF_PORT],
            username=entry.data[CONF_USERNAME],
            password=entry.data[CONF_PASSWORD],
            use_ssl=entry.data.get(CONF_USE_SSL, False),
            verify_ssl=entry.data.get(CONF_VERIFY_SSL, False),
            login_key=entry.data.get(CONF_LOGIN_KEY) or None,
        )
        self._logged_in = False
        self._event_task: asyncio.Task | None = None

    async def _async_update_data(self) -> dict[str, Any]:
        """Full poll — used on startup and as 5-minute fallback."""
        if not self._logged_in:
            ok = await self.client.login()
            if not ok:
                raise UpdateFailed("Could not log in to MeshCentral")
            self._logged_in = True

        try:
            devices = await self.client.get_devices()
        except Exception as err:
            self._logged_in = False
            raise UpdateFailed(f"Error fetching devices: {err}") from err

        data = {d["_id"]: d for d in devices if "_id" in d}

        # client.get_devices() now raises on a failed/timed-out request
        # (see #30) rather than returning [], so the except above already
        # catches that case. This is defense-in-depth for the separate
        # edge case where the request genuinely succeeds but reports 0
        # devices after we previously had some — treat that as suspect
        # too rather than trusting it outright (#29).
        if not data and self.data:
            self._logged_in = False
            raise UpdateFailed(
                "MeshCentral returned no devices (likely a stale session after "
                "a server restart) — forcing re-login and retrying"
            )

        # Start real-time listener as background task — don't await it
        if self._event_task is None or self._event_task.done():
            self._event_task = self.hass.loop.create_task(
                self._listen_for_events(),
                name="meshcentral_event_listener",
            )
            _LOGGER.debug("Started MeshCentral real-time event listener")

        return data

    async def _listen_for_events(self) -> None:
        """Persistent WebSocket loop that pushes node events into coordinator data."""
        import aiohttp

        while True:
            try:
                await self._event_loop()
            except Exception as err:
                _LOGGER.warning(
                    "MeshCentral event listener crashed (%s), reconnecting in 30s", err
                )
            await asyncio.sleep(30)

    async def _event_loop(self) -> None:
        """Single WebSocket session receiving real-time node events."""
        import aiohttp

        if not self._logged_in:
            ok = await self.client.login()
            if not ok:
                raise ConnectionError("Login failed")
            self._logged_in = True

        ws_url = self.client.ws_url
        ssl_ctx = self.client._ssl_context()
        headers = {"Cookie": self.client._cookie} if self.client._cookie else {}

        session = await self.client._get_session()
        async with session.ws_connect(
            ws_url,
            ssl=ssl_ctx,
            headers=headers,
            timeout=aiohttp.ClientTimeout(total=None),  # keep-alive forever
        ) as ws:
            opened = asyncio.get_event_loop().time()
            _LOGGER.debug("MeshCentral event WS connected (persistent control.ashx)")
            await self._refresh_after_reconnect()
            while True:
                msg = await ws.receive()
                if msg.type == aiohttp.WSMsgType.TEXT:
                    await self._handle_event(json.loads(msg.data))
                elif msg.type in (
                    aiohttp.WSMsgType.CLOSED,
                    aiohttp.WSMsgType.ERROR,
                ):
                    _LOGGER.debug(
                        "MeshCentral event WS closed (%s) after %.2fs open, reconnecting",
                        msg.type.name,
                        asyncio.get_event_loop().time() - opened,
                    )
                    break

    async def _refresh_after_reconnect(self) -> None:
        """Poll the full device list right after a WS (re)connect.

        The WebSocket only pushes deltas for devices that change state, so a
        client that reconnects after a drop (e.g. after sending a WOL command)
        can otherwise sit with stale/incomplete data until the 5-minute
        fallback poll runs, causing devices to briefly appear offline. This
        closes that gap by fetching a fresh full list immediately.
        """
        try:
            devices = await self.client.get_devices()
        except Exception as err:
            _LOGGER.warning("MeshCentral post-reconnect poll failed: %s", err)
            self._logged_in = False
            return

        data = {d["_id"]: d for d in devices if "_id" in d}

        # Same stale-session guard as _async_update_data (#29): an empty
        # result here after previously having devices means the reconnect
        # went through on a dead session. Don't overwrite good data with
        # it — force a fresh login on the next reconnect attempt instead.
        if not data and self.data:
            _LOGGER.warning(
                "MeshCentral post-reconnect poll got 0 devices (had %d) — "
                "likely a stale session, forcing re-login",
                len(self.data),
            )
            self._logged_in = False
            return

        if data:
            self.async_set_updated_data(data)
            _LOGGER.debug(
                "MeshCentral post-reconnect poll refreshed %d devices", len(data)
            )

    async def _handle_event(self, data: dict) -> None:
        """Process a single WebSocket message and update coordinator data."""
        action = data.get("action")

        if action == "event":
            evt = data.get("event", {})
            evt_action = evt.get("action")

            if evt_action == "nodeconnect":
                node_id = evt.get("nodeid")
                if node_id and self.data and node_id in self.data:
                    self.data[node_id]["conn"] = evt.get("conn", 0)
                    self.data[node_id]["pwr"] = evt.get("pwr", 0)
                    if "ct" in evt:
                        self.data[node_id]["agct"] = evt["ct"]
                    _LOGGER.debug(
                        "nodeconnect: %s conn=%s",
                        self.data[node_id].get("name", node_id),
                        evt.get("conn"),
                    )
                    if self.data:
                        self.async_set_updated_data(dict(self.data))

            elif evt_action == "changenode":
                node = evt.get("node", {})
                node_id = node.get("_id")
                if node_id and self.data and node_id in self.data:
                    self.data[node_id].update(node)
                    _LOGGER.debug(
                        "changenode: %s updated", node.get("name", node_id)
                    )
                    if self.data:
                        self.async_set_updated_data(dict(self.data))

    async def async_shutdown(self) -> None:
        """Cancel event listener and close client."""
        if self._event_task and not self._event_task.done():
            self._event_task.cancel()
            try:
                await self._event_task
            except asyncio.CancelledError:
                pass
        await self.client.close()
