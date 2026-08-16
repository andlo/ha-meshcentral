"""Server-wide count sensors: devices online/offline, meshes, accounts."""
from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any

from homeassistant.components.sensor import SensorEntity, SensorStateClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant, callback
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
        return {
            "mesh_count": len(meshes),
            "account_count": len(users),
            # Trimmed id/name pairs only — used to spawn one aggregated
            # online-count sensor per device group (#41). The full mesh
            # objects aren't needed here and would just bloat coordinator
            # data that's diffed/compared on every 15-minute refresh.
            "meshes": [
                {"_id": m["_id"], "name": m.get("name", m["_id"])}
                for m in meshes
                if m.get("_id")
            ],
        }


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

    # One aggregated online-count sensor per device group (#41). Device
    # groups are rarely added/removed, but handle it the same way sensor.py
    # handles new devices — add entities for any group we haven't seen yet,
    # every time the slow-polled stats coordinator refreshes.
    known_group_ids: set[str] = set()

    @callback
    def _async_add_new_group_entities() -> None:
        meshes = coordinator.data.get("meshes") or []
        new_meshes = [m for m in meshes if m["_id"] not in known_group_ids]
        if not new_meshes:
            return
        known_group_ids.update(m["_id"] for m in new_meshes)
        async_add_entities([
            MeshCentralGroupDevicesOnlineSensor(main, entry.entry_id, m["_id"], m["name"])
            for m in new_meshes
        ])

    _async_add_new_group_entities()
    entry.async_on_unload(coordinator.async_add_listener(_async_add_new_group_entities))


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
        # Matches the per-device "Online" binary_sensor: any connectivity
        # counts (conn is a bitmask, not conn == 1) — see binary_sensor.py.
        return sum(1 for n in self._main.data.values() if n.get("conn", 0) != 0)


class MeshCentralDevicesOfflineSensor(_MainCoordinatorBase):
    _attr_name = "Devices Offline"
    _attr_icon = "mdi:lan-disconnect"

    def __init__(self, main, entry_id):
        super().__init__(main, entry_id)
        self._attr_unique_id = f"mc_{entry_id}_server_devices_offline"

    @property
    def native_value(self):
        return sum(1 for n in self._main.data.values() if n.get("conn", 0) == 0)


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


class MeshCentralGroupDevicesOnlineSensor(CoordinatorEntity[MeshCentralCoordinator], SensorEntity):
    """Online/total device count for a single device group (mesh) (#41).

    Reuses the main coordinator directly (not the slow-polled stats one) so
    the count updates instantly via the same nodeconnect WebSocket push the
    per-device online binary_sensor already relies on.

    Gets its own synthetic per-group device (nested under the MeshCentral
    Server device via via_device) rather than living on the server device
    itself, so each group reads cleanly as e.g. "Office" -> "Devices Online"
    instead of a long, prefixed entity name.
    """

    _attr_has_entity_name = True
    _attr_name = "Devices Online"
    _attr_icon = "mdi:lan-connect"
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, main: MeshCentralCoordinator, entry_id: str, mesh_id: str, mesh_name: str) -> None:
        super().__init__(main)
        self._main = main
        self._entry_id = entry_id
        self._mesh_id = mesh_id
        self._mesh_name = mesh_name
        self._attr_unique_id = f"mc_{entry_id}_group_{mesh_id}_devices_online"

    @property
    def _group_nodes(self) -> list[dict]:
        return [n for n in self._main.data.values() if n.get("_meshid") == self._mesh_id]

    @property
    def native_value(self):
        # Matches the server-wide Devices Online sensor: conn is a bitmask,
        # so any nonzero value counts as online (see binary_sensor.py).
        return sum(1 for n in self._group_nodes if n.get("conn", 0) != 0)

    @property
    def extra_state_attributes(self):
        nodes = self._group_nodes
        offline = sorted(n.get("name", n.get("_id")) for n in nodes if n.get("conn", 0) == 0)
        return {"total": len(nodes), "offline_devices": offline}

    @property
    def device_info(self):
        return {
            "identifiers": {(DOMAIN, f"{self._entry_id}_group_{self._mesh_id}")},
            "name": self._mesh_name,
            "manufacturer": "MeshCentral",
            "model": "Device Group",
            "via_device": (DOMAIN, f"{self._entry_id}_server"),
        }
