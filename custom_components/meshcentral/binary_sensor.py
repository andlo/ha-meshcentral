"""Binary sensors for MeshCentral — device online/offline."""
from __future__ import annotations

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import ATTR_IP_ADDRESS, ATTR_LAST_CONNECT, ATTR_MESH_ID, DOMAIN
from .coordinator import MeshCentralCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up binary sensors."""
    coordinator: MeshCentralCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        MeshCentralDeviceOnlineSensor(coordinator, node_id)
        for node_id in coordinator.data
    )


class MeshCentralDeviceOnlineSensor(
    CoordinatorEntity[MeshCentralCoordinator], BinarySensorEntity
):
    """Binary sensor: is this MeshCentral device currently online?"""

    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY
    _attr_has_entity_name = True
    _attr_name = "Online"

    def __init__(self, coordinator: MeshCentralCoordinator, node_id: str) -> None:
        super().__init__(coordinator)
        self._node_id = node_id
        self._attr_unique_id = f"{node_id}_online"

    @property
    def _node(self) -> dict:
        return self.coordinator.data.get(self._node_id, {})

    @property
    def is_on(self) -> bool:
        # conn == 1 means agent connected
        return self._node.get("conn", 0) == 1

    @property
    def extra_state_attributes(self) -> dict:
        node = self._node
        return {
            ATTR_MESH_ID: node.get("meshid"),
            ATTR_IP_ADDRESS: node.get("ip"),
            ATTR_LAST_CONNECT: node.get("lastconnect"),
        }

    @property
    def device_info(self):
        node = self._node
        return {
            "identifiers": {(DOMAIN, self._node_id)},
            "name": node.get("name", self._node_id),
            "manufacturer": "MeshCentral",
            "model": node.get("osdesc", "Unknown OS"),
            "sw_version": node.get("agent", {}).get("ver"),
        }
