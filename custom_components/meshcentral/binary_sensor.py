"""Binary sensors for MeshCentral devices."""
from __future__ import annotations

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import CONN_AGENT, DOMAIN, conn_type_list
from .coordinator import MeshCentralCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: MeshCentralCoordinator = hass.data[DOMAIN][entry.entry_id]
    known_node_ids: set[str] = set()

    @callback
    def _async_add_new_device_entities() -> None:
        data = coordinator.data or {}
        new_node_ids = [
            node_id for node_id in data if node_id not in known_node_ids
        ]
        if not new_node_ids:
            return

        known_node_ids.update(new_node_ids)
        entities = []
        for node_id in new_node_ids:
            entities += [
                MeshCentralOnlineSensor(coordinator, node_id),
                MeshCentralAntivirusSensor(coordinator, node_id),
                MeshCentralFirewallSensor(coordinator, node_id),
                MeshCentralDefenderSensor(coordinator, node_id),
            ]
        async_add_entities(entities)

    _async_add_new_device_entities()
    entry.async_on_unload(
        coordinator.async_add_listener(_async_add_new_device_entities)
    )


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
        # "conn" is a bitmask (see const.py) — a device counts as online if
        # ANY connection channel is up, not just when it equals exactly 1.
        # A device connected via agent+CIRA (conn == 3) was being reported
        # as offline before this fix (#26).
        return self._node.get("conn", 0) != 0

    @property
    def extra_state_attributes(self):
        node = self._node
        conn = node.get("conn", 0)
        return {
            "ip": node.get("ip"),
            "mesh_id": node.get("_meshid"),
            "connection_types": conn_type_list(conn),
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
