"""Button entities for MeshCentral — reboot and WOL."""
from __future__ import annotations

import logging

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import MeshCentralCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: MeshCentralCoordinator = hass.data[DOMAIN][entry.entry_id]
    entities = []
    for node_id in coordinator.data:
        entities.append(MeshCentralRebootButton(coordinator, node_id))
    async_add_entities(entities)


class _MeshCentralBaseButton(CoordinatorEntity[MeshCentralCoordinator], ButtonEntity):
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
        }

class MeshCentralRebootButton(_MeshCentralBaseButton):
    """Button to send a reboot command to the device via MeshCentral agent."""

    _attr_name = "Reboot"
    _attr_icon = "mdi:restart"

    def __init__(self, coordinator: MeshCentralCoordinator, node_id: str) -> None:
        super().__init__(coordinator, node_id)
        self._attr_unique_id = f"{node_id}_reboot"

    async def async_press(self) -> None:
        """Send reboot command."""
        node = self._node
        if node.get("conn", 0) != 1:
            _LOGGER.warning(
                "Cannot reboot %s — device is offline", node.get("name", self._node_id)
            )
            return
        # MeshCentral WS action to run a power command (2 = reboot)
        # This is sent as a meshaction on the control socket
        result = await self.coordinator.client._send_recv(
            {
                "action": "poweraction",
                "nodeid": self._node_id,
                "actiontype": 2,  # 1=sleep, 2=reboot, 3=poweroff
                "responseid": "ha-reboot",
            },
            "poweraction",
        )
        if result:
            _LOGGER.info("Reboot command sent to %s", node.get("name", self._node_id))
        else:
            _LOGGER.error(
                "Reboot command failed for %s", node.get("name", self._node_id)
            )
