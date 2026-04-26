"""Sensors for MeshCentral devices."""
from __future__ import annotations

from datetime import datetime, timezone

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
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
            MeshCentralOsSensor(coordinator, node_id),
            MeshCentralIpSensor(coordinator, node_id),
            MeshCentralLastBootSensor(coordinator, node_id),
            MeshCentralIdleTimeSensor(coordinator, node_id),
            MeshCentralUsersSensor(coordinator, node_id),
            MeshCentralDescSensor(coordinator, node_id),
            MeshCentralAgentLastSeenSensor(coordinator, node_id),
        ]
    async_add_entities(entities)


class _Base(CoordinatorEntity[MeshCentralCoordinator], SensorEntity):
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


class MeshCentralOsSensor(_Base):
    _attr_name = "OS"
    _attr_icon = "mdi:desktop-classic"

    def __init__(self, coordinator, node_id):
        super().__init__(coordinator, node_id)
        self._attr_unique_id = f"{node_id}_os"

    @property
    def native_value(self):
        return self._node.get("osdesc")


class MeshCentralIpSensor(_Base):
    _attr_name = "IP Address"
    _attr_icon = "mdi:ip-network"

    def __init__(self, coordinator, node_id):
        super().__init__(coordinator, node_id)
        self._attr_unique_id = f"{node_id}_ip"

    @property
    def native_value(self):
        return self._node.get("ip")


class MeshCentralLastBootSensor(_Base):
    _attr_name = "Last Boot"
    _attr_icon = "mdi:restart"
    _attr_device_class = SensorDeviceClass.TIMESTAMP

    def __init__(self, coordinator, node_id):
        super().__init__(coordinator, node_id)
        self._attr_unique_id = f"{node_id}_lastboot"

    @property
    def native_value(self):
        ts = self._node.get("lastbootuptime")
        if ts:
            return datetime.fromtimestamp(ts / 1000, tz=timezone.utc)
        return None


class MeshCentralIdleTimeSensor(_Base):
    _attr_name = "Idle Time"
    _attr_icon = "mdi:timer-outline"
    _attr_native_unit_of_measurement = "s"

    def __init__(self, coordinator, node_id):
        super().__init__(coordinator, node_id)
        self._attr_unique_id = f"{node_id}_idletime"

    @property
    def native_value(self):
        return self._node.get("idletime")


class MeshCentralUsersSensor(_Base):
    _attr_name = "Active Users"
    _attr_icon = "mdi:account-multiple"

    def __init__(self, coordinator, node_id):
        super().__init__(coordinator, node_id)
        self._attr_unique_id = f"{node_id}_users"

    @property
    def native_value(self):
        users = self._node.get("lusers") or self._node.get("users", [])
        if not users:
            return "None"
        # Strip domain prefix (HOSTNAME\\user -> user)
        cleaned = [u.split("\\")[-1] if "\\" in u else u for u in users]
        return ", ".join(cleaned)


class MeshCentralDescSensor(_Base):
    _attr_name = "Description"
    _attr_icon = "mdi:information-outline"

    def __init__(self, coordinator, node_id):
        super().__init__(coordinator, node_id)
        self._attr_unique_id = f"{node_id}_desc"

    @property
    def native_value(self):
        return self._node.get("desc") or self._node.get("rname")


class MeshCentralAgentLastSeenSensor(_Base):
    _attr_name = "Agent Last Seen"
    _attr_icon = "mdi:lan-connect"
    _attr_device_class = SensorDeviceClass.TIMESTAMP

    def __init__(self, coordinator, node_id):
        super().__init__(coordinator, node_id)
        self._attr_unique_id = f"{node_id}_agct"

    @property
    def native_value(self):
        ts = self._node.get("agct")
        if ts:
            return datetime.fromtimestamp(ts / 1000, tz=timezone.utc)
        return None
