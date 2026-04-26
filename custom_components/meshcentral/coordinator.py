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
    CONF_USE_SSL,
    CONF_VERIFY_SSL,
    DEFAULT_SCAN_INTERVAL,
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
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=300),  # fallback poll every 5 min
        )
        self.entry = entry
        self.client = MeshCentralClient(
            host=entry.data[CONF_HOST],
            port=entry.data[CONF_PORT],
            username=entry.data[CONF_USERNAME],
            password=entry.data[CONF_PASSWORD],
            use_ssl=entry.data.get(CONF_USE_SSL, False),
            verify_ssl=entry.data.get(CONF_VERIFY_SSL, False),
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
            _LOGGER.debug("MeshCentral event WS connected")
            while True:
                msg = await ws.receive()
                if msg.type == aiohttp.WSMsgType.TEXT:
                    await self._handle_event(json.loads(msg.data))
                elif msg.type in (
                    aiohttp.WSMsgType.CLOSED,
                    aiohttp.WSMsgType.ERROR,
                ):
                    _LOGGER.debug("MeshCentral event WS closed, reconnecting")
                    break

    async def _handle_event(self, data: dict) -> None:
        """Process a single WebSocket message and update coordinator data."""
        action = data.get("action")

        # Real-time connectivity change: conn=1 online, conn=0 offline
        if action == "event":
            evt = data.get("event", {})
            evt_action = evt.get("action")

            if evt_action == "nodeconnect":
                node_id = evt.get("nodeid")
                if node_id and node_id in self.data:
                    self.data[node_id]["conn"] = evt.get("conn", 0)
                    self.data[node_id]["pwr"] = evt.get("pwr", 0)
                    if "ct" in evt:
                        self.data[node_id]["agct"] = evt["ct"]
                    _LOGGER.debug(
                        "nodeconnect: %s conn=%s",
                        self.data[node_id].get("name", node_id),
                        evt.get("conn"),
                    )
                    self.async_set_updated_data(dict(self.data))

            elif evt_action == "changenode":
                node = evt.get("node", {})
                node_id = node.get("_id")
                if node_id and node_id in self.data:
                    # Merge updated fields into existing node data
                    self.data[node_id].update(node)
                    _LOGGER.debug(
                        "changenode: %s updated", node.get("name", node_id)
                    )
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
