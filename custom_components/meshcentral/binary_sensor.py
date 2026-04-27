"""Binary sensors for MeshCentral devices."""
from __future__ import annotations

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
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
        entities += [
            MeshCentralOnlineSensor(coordinator, node_id),
            MeshCentralAntivirusSensor(coordinator, node_id),
            MeshCentralFirewallSensor(coordinator, node_id),
            MeshCentralDefenderSensor(coordinator, node_id),
        ]
    async_add_entities(entities)


class _Base(CoordinatorEntity[MeshCentralCoordinator], BinarySensorEntity):
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
            "sw_version": str(node.get("agent", {}).get("core", "")),
        }


class MeshCentralOnlineSensor(_Base):
    _attr_name = "Online"
    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY

    def __init__(self, coordinator, node_id):
        super().__init__(coordinator, node_id)
        self._attr_unique_id = f"mc_{node_id}_online"

    @property
    def is_on(self):
        return self._node.get("conn", 0) == 1

    @property
    def extra_state_attributes(self):
        node = self._node
        return {
            "ip": node.get("ip"),
            "mesh_id": node.get("_meshid"),
        }


class MeshCentralAntivirusSensor(_Base):
    _attr_name = "Antivirus OK"
    _attr_icon = "mdi:shield-check"

    def __init__(self, coordinator, node_id):
        super().__init__(coordinator, node_id)
        self._attr_unique_id = f"mc_{node_id}_av"

    @property
    def is_on(self):
        return self._node.get("wsc", {}).get("antiVirus") == "OK"

    @property
    def available(self):
        return "wsc" in self._node


class MeshCentralFirewallSensor(_Base):
    _attr_name = "Firewall OK"
    _attr_icon = "mdi:wall-fire"

    def __init__(self, coordinator, node_id):
        super().__init__(coordinator, node_id)
        self._attr_unique_id = f"mc_{node_id}_fw"

    @property
    def is_on(self):
        return self._node.get("wsc", {}).get("firewall") == "OK"

    @property
    def available(self):
        return "wsc" in self._node


class MeshCentralDefenderSensor(_Base):
    _attr_name = "Defender Real-Time Protection"
    _attr_icon = "mdi:shield-lock"

    def __init__(self, coordinator, node_id):
        super().__init__(coordinator, node_id)
        self._attr_unique_id = f"mc_{node_id}_defender"

    @property
    def is_on(self):
        return self._node.get("defender", {}).get("RealTimeProtection", False)

    @property
    def available(self):
        return "defender" in self._node
