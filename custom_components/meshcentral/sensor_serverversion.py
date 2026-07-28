"""Server-level version sensors (installed vs. latest available)."""
from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity, DataUpdateCoordinator

from .const import DOMAIN
from .coordinator import MeshCentralCoordinator

_LOGGER = logging.getLogger(__name__)

NPM_LATEST_URL = "https://registry.npmjs.org/meshcentral/latest"


class ServerVersionCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Polls installed + latest available MeshCentral server version.

    Slow interval by design — server versions change rarely, and one branch
    of this check is an external HTTPS call to the npm registry that
    shouldn't run on every device poll.
    """

    def __init__(self, hass: HomeAssistant, main: MeshCentralCoordinator) -> None:
        super().__init__(
            hass, _LOGGER,
            name=f"{DOMAIN}_serverversion",
            update_interval=timedelta(hours=6),
        )
        self._main = main

    async def _async_update_data(self) -> dict[str, Any]:
        data: dict[str, Any] = {"installed": None, "latest": None}

        # Fast path: serverconsole info returns MeshCentral's in-memory
        # current version and does not wait for an npm dist-tag lookup.
        installed = await self._main.client.get_installed_server_version()
        if installed:
            data["installed"] = installed

        # Compatibility fallback for servers that do not permit serverconsole.
        tags = None
        if not installed:
            tags = await self._main.client.get_server_version_tags()
        if tags:
            data["installed"] = tags.get("current")
            if tags.get("latest"):
                data["latest"] = tags["latest"]

        # Always cross-check against npm directly too — this works for any
        # server regardless of auth type or hosting, and is authoritative
        # for "latest" even when the server-reported value above is missing
        # or the server itself has no internet access to check npm.
        try:
            session = async_get_clientsession(self.hass)
            async with session.get(NPM_LATEST_URL, timeout=10) as resp:
                if resp.status == 200:
                    npm_data = await resp.json(content_type=None)
                    npm_version = npm_data.get("version")
                    if npm_version:
                        data["latest"] = npm_version
        except Exception as err:  # noqa: BLE001 - never let this break device polling
            _LOGGER.debug("npm registry version check failed: %s", err)

        return data


async def async_setup_server_version_entities(
    hass: HomeAssistant,
    entry: ConfigEntry,
    main: MeshCentralCoordinator,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator = ServerVersionCoordinator(hass, main)
    await coordinator.async_config_entry_first_refresh()
    hass.data[DOMAIN][f"{entry.entry_id}_serverversion"] = coordinator

    async_add_entities([
        MeshCentralInstalledVersionSensor(coordinator, main, entry.entry_id),
        MeshCentralLatestVersionSensor(coordinator, main, entry.entry_id),
    ])


class _ServerBase(CoordinatorEntity[ServerVersionCoordinator], SensorEntity):
    """Base for server-level (not per-device) sensors.

    These live on a synthetic "MeshCentral Server" device, separate from the
    per-node devices, since they describe the server itself.
    """

    _attr_has_entity_name = True
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator: ServerVersionCoordinator, main: MeshCentralCoordinator, entry_id: str) -> None:
        super().__init__(coordinator)
        self._entry_id = entry_id
        self._main = main

    @property
    def device_info(self):
        return {
            "identifiers": {(DOMAIN, f"{self._entry_id}_server")},
            "name": "MeshCentral Server",
            "manufacturer": "MeshCentral",
            "configuration_url": self._main.client.base_url,
        }


class MeshCentralInstalledVersionSensor(_ServerBase):
    """Installed MeshCentral server version."""

    _attr_name = "Installed Version"
    _attr_icon = "mdi:server"

    def __init__(self, coordinator, main, entry_id):
        super().__init__(coordinator, main, entry_id)
        self._attr_unique_id = f"mc_{entry_id}_server_installed_version"

    @property
    def native_value(self):
        return self.coordinator.data.get("installed")

    @property
    def available(self) -> bool:
        return self.coordinator.data.get("installed") is not None


class MeshCentralLatestVersionSensor(_ServerBase):
    """Latest MeshCentral version published on npm.

    Works for any server regardless of hosting or auth type — this is a
    direct, unauthenticated check against the npm registry.
    """

    _attr_name = "Latest Available Version"
    _attr_icon = "mdi:cloud-download-outline"

    def __init__(self, coordinator, main, entry_id):
        super().__init__(coordinator, main, entry_id)
        self._attr_unique_id = f"mc_{entry_id}_server_latest_version"

    @property
    def native_value(self):
        return self.coordinator.data.get("latest")

    @property
    def available(self) -> bool:
        return self.coordinator.data.get("latest") is not None
