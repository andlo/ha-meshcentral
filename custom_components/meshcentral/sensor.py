"""Sensors for MeshCentral devices."""
from __future__ import annotations

from datetime import datetime, timezone

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, POWER_STATE_MAP, POWER_STATE_UNKNOWN
from .coordinator import MeshCentralCoordinator
from .sensor_hardware import HardwareDataCoordinator, async_setup_hardware_entities
from .sensor_serverstats import async_setup_server_stats_entities
from .sensor_serverversion import async_setup_server_version_entities


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
                MeshCentralOsSensor(coordinator, node_id),
                MeshCentralIpSensor(coordinator, node_id),
                MeshCentralLastBootSensor(coordinator, node_id),
                MeshCentralIdleTimeSensor(coordinator, node_id),
                MeshCentralUsersSensor(coordinator, node_id),
                MeshCentralDescSensor(coordinator, node_id),
                MeshCentralAgentLastSeenSensor(coordinator, node_id),
                MeshCentralPowerStateSensor(coordinator, node_id),
            ]
        async_add_entities(entities)

    _async_add_new_device_entities()
    entry.async_on_unload(
        coordinator.async_add_listener(_async_add_new_device_entities)
    )

    # Hardware detail sensors (disabled by default, fetched separately)
    hw_coordinator = HardwareDataCoordinator(hass, coordinator)
    await hw_coordinator.async_config_entry_first_refresh()
    hass.data[DOMAIN][f"{entry.entry_id}_hw"] = hw_coordinator
    await async_setup_hardware_entities(hass, entry, coordinator, hw_coordinator, async_add_entities)

    # Server-level version sensors (installed / latest available)
    await async_setup_server_version_entities(hass, entry, coordinator, async_add_entities)

    # Server-level count sensors (devices online/offline, meshes, accounts)
    await async_setup_server_stats_entities(hass, entry, coordinator, async_add_entities)


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
        self._attr_unique_id = f"mc_{node_id}_os"

    @property
    def native_value(self):
        return self._node.get("osdesc")


class MeshCentralIpSensor(_Base):
    _attr_name = "IP Address"
    _attr_icon = "mdi:ip-network"

    def __init__(self, coordinator, node_id):
        super().__init__(coordinator, node_id)
        self._attr_unique_id = f"mc_{node_id}_ip"

    @property
    def native_value(self):
        return self._node.get("ip")


class MeshCentralLastBootSensor(_Base):
    _attr_name = "Last Boot"
    _attr_icon = "mdi:restart"
    _attr_device_class = SensorDeviceClass.TIMESTAMP

    def __init__(self, coordinator, node_id):
        super().__init__(coordinator, node_id)
        self._attr_unique_id = f"mc_{node_id}_lastboot"

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
        self._attr_unique_id = f"mc_{node_id}_idletime"

    @property
    def native_value(self):
        return self._node.get("idletime")


class MeshCentralUsersSensor(_Base):
    _attr_name = "Active Users"
    _attr_icon = "mdi:account-multiple"

    def __init__(self, coordinator, node_id):
        super().__init__(coordinator, node_id)
        self._attr_unique_id = f"mc_{node_id}_users"

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
        self._attr_unique_id = f"mc_{node_id}_desc"

    @property
    def native_value(self):
        return self._node.get("desc") or self._node.get("rname")


class MeshCentralAgentLastSeenSensor(_Base):
    _attr_name = "Agent Last Seen"
    _attr_icon = "mdi:lan-connect"
    _attr_device_class = SensorDeviceClass.TIMESTAMP

    def __init__(self, coordinator, node_id):
        super().__init__(coordinator, node_id)
        self._attr_unique_id = f"mc_{node_id}_agct"

    @property
    def native_value(self):
        ts = self._node.get("agct")
        if ts:
            return datetime.fromtimestamp(ts / 1000, tz=timezone.utc)
        return None


class MeshCentralPowerStateSensor(_Base):
    """Power state (on/sleep/deep_sleep/hibernate/soft_off/present/off) for a device.

    MeshCentral reports this via the numeric "pwr" field on the node and in
    "nodeconnect" WebSocket events. See const.POWER_STATE_MAP for the mapping.
    """

    _attr_name = "Power State"
    _attr_icon = "mdi:power-settings"
    _attr_device_class = SensorDeviceClass.ENUM
    # dict.fromkeys(...) dedupes while preserving order — POWER_STATE_MAP
    # maps two different pwr codes (ACPI S1 and S2) to the same "sleep"
    # label, so a plain list() here would give ENUM a duplicate option.
    _attr_options = list(dict.fromkeys(POWER_STATE_MAP.values())) + [POWER_STATE_UNKNOWN]

    def __init__(self, coordinator, node_id):
        super().__init__(coordinator, node_id)
        self._attr_unique_id = f"mc_{node_id}_pwr"

    @property
    def native_value(self):
        pwr = self._node.get("pwr")
        if pwr is None:
            return POWER_STATE_UNKNOWN
        return POWER_STATE_MAP.get(pwr, POWER_STATE_UNKNOWN)
