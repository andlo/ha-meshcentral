"""Sensors for MeshCentral devices."""
from __future__ import annotations

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import MeshCentralCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: MeshCentralCoordinator = hass.data[DOMAIN][entry.entry_id]
    entities = []
    for node_id in coordinator.data:
        entities.append(MeshCentralOsSensor(coordinator, node_id))
        entities.append(MeshCentralIpSensor(coordinator, node_id))
    async_add_entities(entities)


class _MeshCentralBaseSensor(CoordinatorEntity[MeshCentralCoordinator], SensorEntity):
    _attr_has_entity_name = True

    def __init__(self, coordinator: MeshCentralCoordinator, node_id: str) -> None:
        super().__init__(coordinator)
        self._node_id = node_id

    @property
    def _node(self) -> dict:
        return self.coordinator.data.get(self._node_id, {})

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


class MeshCentralOsSensor(_MeshCentralBaseSensor):
    _attr_name = "OS"
    _attr_icon = "mdi:desktop-classic"

    def __init__(self, coordinator, node_id):
        super().__init__(coordinator, node_id)
        self._attr_unique_id = f"{node_id}_os"

    @property
    def native_value(self) -> str | None:
        return self._node.get("osdesc")


class MeshCentralIpSensor(_MeshCentralBaseSensor):
    _attr_name = "IP Address"
    _attr_icon = "mdi:ip-network"

    def __init__(self, coordinator, node_id):
        super().__init__(coordinator, node_id)
        self._attr_unique_id = f"{node_id}_ip"

    @property
    def native_value(self) -> str | None:
        return self._node.get("ip")
