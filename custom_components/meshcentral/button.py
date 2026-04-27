"""Button entities for MeshCentral — power control per device."""
from __future__ import annotations

import logging

from homeassistant.components.button import ButtonEntity, ButtonDeviceClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import MeshCentralCoordinator

_LOGGER = logging.getLogger(__name__)

# MeshCentral poweraction types
PWR_SLEEP = 1
PWR_REBOOT = 2
PWR_SHUTDOWN = 3
PWR_WOL = 4
PWR_HIBERNATE = 5


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: MeshCentralCoordinator = hass.data[DOMAIN][entry.entry_id]
    entities = []
    for node_id in coordinator.data:
        node = coordinator.data[node_id]
        is_windows = "wsc" in node  # Windows nodes have wsc field

        entities += [
            MeshCentralRebootButton(coordinator, node_id),
            MeshCentralShutdownButton(coordinator, node_id),
            MeshCentralWolButton(coordinator, node_id),
        ]
        if is_windows:
            entities += [
                MeshCentralSleepButton(coordinator, node_id),
                MeshCentralHibernateButton(coordinator, node_id),
            ]
    async_add_entities(entities)


class _BaseButton(CoordinatorEntity[MeshCentralCoordinator], ButtonEntity):
    _attr_has_entity_name = True
    _power_action: int

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
        }

    async def async_press(self) -> None:
        node = self._node
        _LOGGER.debug(
            "Sending power action %s to %s", self._power_action, node.get("name")
        )
        ok = await self.coordinator.client.send_power_action(
            self._node_id, self._power_action
        )
        if ok:
            _LOGGER.info(
                "Power action %s sent to %s", self._power_action, node.get("name")
            )
        else:
            _LOGGER.warning(
                "Power action %s to %s returned no response",
                self._power_action,
                node.get("name"),
            )


class MeshCentralRebootButton(_BaseButton):
    _attr_name = "Reboot"
    _attr_icon = "mdi:restart"
    _attr_device_class = ButtonDeviceClass.RESTART
    _power_action = PWR_REBOOT

    def __init__(self, coordinator, node_id):
        super().__init__(coordinator, node_id)
        self._attr_unique_id = f"mc_{node_id}_reboot"


class MeshCentralShutdownButton(_BaseButton):
    _attr_name = "Shutdown"
    _attr_icon = "mdi:power"
    _attr_device_class = ButtonDeviceClass.UPDATE
    _power_action = PWR_SHUTDOWN

    def __init__(self, coordinator, node_id):
        super().__init__(coordinator, node_id)
        self._attr_unique_id = f"mc_{node_id}_shutdown"


class MeshCentralSleepButton(_BaseButton):
    _attr_name = "Sleep"
    _attr_icon = "mdi:sleep"
    _power_action = PWR_SLEEP

    def __init__(self, coordinator, node_id):
        super().__init__(coordinator, node_id)
        self._attr_unique_id = f"mc_{node_id}_sleep"


class MeshCentralHibernateButton(_BaseButton):
    _attr_name = "Hibernate"
    _attr_icon = "mdi:power-sleep"
    _power_action = PWR_HIBERNATE

    def __init__(self, coordinator, node_id):
        super().__init__(coordinator, node_id)
        self._attr_unique_id = f"mc_{node_id}_hibernate"


class MeshCentralWolButton(_BaseButton):
    """Wake-on-LAN via MeshCentral — uses online agents on same network to send magic packet."""

    _attr_name = "Wake on LAN"
    _attr_icon = "mdi:lan-pending"
    _power_action = PWR_WOL  # kept for completeness, not used directly

    def __init__(self, coordinator, node_id):
        super().__init__(coordinator, node_id)
        self._attr_unique_id = f"mc_{node_id}_wol"

    async def async_press(self) -> None:
        node = self._node
        _LOGGER.debug("Sending WOL to %s", node.get("name"))
        result = await self.coordinator.client.send_wol(self._node_id)
        if result:
            _LOGGER.info("WOL sent to %s: %s", node.get("name"), result)
        else:
            _LOGGER.warning("WOL to %s failed — no agents available on same network?", node.get("name"))
