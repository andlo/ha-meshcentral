"""DataUpdateCoordinator for MeshCentral."""
from __future__ import annotations

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
    """Coordinator that polls MeshCentral for device data."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=DEFAULT_SCAN_INTERVAL),
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

    async def _async_update_data(self) -> dict[str, Any]:
        """Fetch data from MeshCentral."""
        if not self._logged_in:
            ok = await self.client.login()
            if not ok:
                raise UpdateFailed("Could not log in to MeshCentral")
            self._logged_in = True

        try:
            devices = await self.client.get_devices()
        except Exception as err:
            self._logged_in = False  # force re-login next time
            raise UpdateFailed(f"Error fetching devices: {err}") from err

        # Index by node _id for easy entity lookups
        return {d["_id"]: d for d in devices if "_id" in d}

    async def async_shutdown(self) -> None:
        """Close client when entry is unloaded."""
        await self.client.close()
