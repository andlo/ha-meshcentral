"""Server-wide count sensors: devices online/offline, meshes, accounts."""
from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any

from homeassistant.components.sensor import SensorEntity, SensorStateClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity, DataUpdateCoordinator

from .const import DOMAIN
from .coordinator import MeshCentralCoordinator

_LOGGER = logging.getLogger(__name__)

# Meshes/accounts change rarely - poll on a slow, separate interval so this
# never adds load to the real-time device polling.
STATS_POLL_INTERVAL = timedelta(minutes=15)


class ServerStatsCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Polls mesh (device group) and user account counts."""

    def __init__(self, hass: HomeAssistant, main: MeshCentralCoordinator) -> None:
        super().__init__(
            hass, _LOGGER,
            name=f"{DOMAIN}_serverstats",
            update_interval=STATS_POLL_INTERVAL,
        )
        self._main = main

    async def _async_update_data(self) -> dict[str, Any]:
        meshes = await self._main.client.get_device_groups()
        users = await self._main.client.get_users()
        return {"mesh_count": len(meshes), "account_count": len(users)}


async def async_setup_server_stats_entities(
    hass: HomeAssistant,
    entry: ConfigEntry,
    main: MeshCentralCoordinator,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator = ServerStatsCoordinator(hass, main)
    await coordinator.async_config_entry_first_refresh()
    hass.data[DOMAIN][f"{entry.entry_id}_serverstats"] = coordinator

    async_add_entities([
        MeshCentralDevicesOnlineSensor(main, entry.entry_id),
        MeshCentralDevicesOfflineSensor(main, entry.entry_id),
        MeshCentralDevicesTotalSensor(main, entry.entry_id),
        MeshCentralMeshCountSensor(coordinator, main, entry.entry_id),
        MeshCentralAccountCountSensor(coordinator, main, entry.entry_id),
    ])


class _ServerDeviceMixin:
    """Shared device_info: groups these on the synthetic 'MeshCentral Server' device."""

    _attr_has_entity_name = True
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_icon = "mdi:server-network"

    @property
    def device_info(self):
        return {
            "identifiers": {(DOMAIN, f"{self._entry_id}_server")},
            "name": "MeshCentral Server",
            "manufacturer": "MeshCentral",
            "configuration_url": self._main.client.base_url,
        }


class _MainCoordinatorBase(_ServerDeviceMixin, CoordinatorEntity[MeshCentralCoordinator], SensorEntity):
    """Base for the three device-count sensors — reuses the main coordinator
    directly so counts update instantly via the same WebSocket push the
    per-device entities already use, with no extra polling.
    """

    def __init__(self, main: MeshCentralCoordinator, entry_id: str) -> None:
        super().__init__(main)
        self._main = main
        self._entry_id = entry_id


class MeshCentralDevicesOnlineSensor(_MainCoordinatorBase):
    _attr_name = "Devices Online"
    _attr_icon = "mdi:lan-connect"

    def __init__(self, main, entry_id):
        super().__init__(main, entry_id)
        self._attr_unique_id = f"mc_{entry_id}_server_devices_online"

    @property
    def native_value(self):
        return sum(1 for n in self._main.data.values() if n.get("conn", 0) == 1)


class MeshCentralDevicesOfflineSensor(_MainCoordinatorBase):
    _attr_name = "Devices Offline"
    _attr_icon = "mdi:lan-disconnect"

    def __init__(self, main, entry_id):
        super().__init__(main, entry_id)
        self._attr_unique_id = f"mc_{entry_id}_server_devices_offline"

    @property
    def native_value(self):
        return sum(1 for n in self._main.data.values() if n.get("conn", 0) != 1)


class MeshCentralDevicesTotalSensor(_MainCoordinatorBase):
    _attr_name = "Devices Total"
    _attr_icon = "mdi:devices"

    def __init__(self, main, entry_id):
        super().__init__(main, entry_id)
        self._attr_unique_id = f"mc_{entry_id}_server_devices_total"

    @property
    def native_value(self):
        return len(self._main.data)


class _StatsCoordinatorBase(_ServerDeviceMixin, CoordinatorEntity[ServerStatsCoordinator], SensorEntity):
    """Base for the slow-polled mesh/account count sensors."""

    def __init__(self, coordinator: ServerStatsCoordinator, main: MeshCentralCoordinator, entry_id: str) -> None:
        super().__init__(coordinator)
        self._main = main
        self._entry_id = entry_id


class MeshCentralMeshCountSensor(_StatsCoordinatorBase):
    _attr_name = "Device Groups"
    _attr_icon = "mdi:folder-network"

    def __init__(self, coordinator, main, entry_id):
        super().__init__(coordinator, main, entry_id)
        self._attr_unique_id = f"mc_{entry_id}_server_mesh_count"

    @property
    def native_value(self):
        return self.coordinator.data.get("mesh_count")


class MeshCentralAccountCountSensor(_StatsCoordinatorBase):
    _attr_name = "User Accounts"
    _attr_icon = "mdi:account-multiple"

    def __init__(self, coordinator, main, entry_id):
        super().__init__(coordinator, main, entry_id)
        self._attr_unique_id = f"mc_{entry_id}_server_account_count"

    @property
    def native_value(self):
        return self.coordinator.data.get("account_count")
