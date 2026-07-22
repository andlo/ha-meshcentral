"""Device tracker for MeshCentral — marks devices as home/not_home based on agent connectivity."""
from __future__ import annotations

import logging

from homeassistant.components.device_tracker import SourceType, TrackerEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import CONN_AGENT, DOMAIN
from .coordinator import MeshCentralCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: MeshCentralCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        MeshCentralDeviceTracker(coordinator, node_id)
        for node_id in coordinator.data
    )


class MeshCentralDeviceTracker(
    CoordinatorEntity[MeshCentralCoordinator], TrackerEntity
):
    """Device tracker entity — home when MeshCentral agent is connected."""

    _attr_has_entity_name = True
    _attr_name = "Tracker"
    _attr_source_type = SourceType.ROUTER

    def __init__(self, coordinator: MeshCentralCoordinator, node_id: str) -> None:
        super().__init__(coordinator)
        self._node_id = node_id
        self._attr_unique_id = f"mc_{node_id}_tracker"

    @property
    def _node(self) -> dict:
        return self.coordinator.data.get(self._node_id, {})

    @property
    def is_connected(self) -> bool:
        # "conn" is a bitmask — check the agent bit specifically (this
        # tracker is documented as agent-based), don't require conn == 1
        # exactly, or a device also connected via CIRA/AMT alongside the
        # agent (conn == 3, 5, ...) would wrongly show as not_home (#26).
        return bool(self._node.get("conn", 0) & CONN_AGENT)

    @property
    def latitude(self) -> float | None:
        return None

    @property
    def longitude(self) -> float | None:
        return None

    @property
    def ip_address(self) -> str | None:
        return self._node.get("ip")

    @property
    def hostname(self) -> str | None:
        return self._node.get("name")

    @property
    def extra_state_attributes(self) -> dict:
        node = self._node
        return {
            "ip": node.get("ip"),
            "os": node.get("osdesc"),
            "mesh_id": node.get("_meshid"),
        }

    @property
    def device_info(self):
        node = self._node
        return {
            "identifiers": {(DOMAIN, self._node_id)},
            "name": node.get("name", self._node_id),
            "manufacturer": "MeshCentral",
            "model": node.get("osdesc", "Unknown OS"),
        }
