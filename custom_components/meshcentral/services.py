"""Services for MeshCentral integration."""
from __future__ import annotations

import logging

import voluptuous as vol
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers import config_validation as cv

from .const import DOMAIN
from .coordinator import MeshCentralCoordinator

_LOGGER = logging.getLogger(__name__)

SERVICE_RUN_COMMAND = "run_command"

SERVICE_RUN_COMMAND_SCHEMA = vol.Schema(
    {
        vol.Required("device_id"): cv.string,
        vol.Required("command"): cv.string,
        vol.Optional("run_as_user", default=False): cv.boolean,
    }
)


def async_register_services(hass: HomeAssistant) -> None:
    """Register MeshCentral services."""

    async def handle_run_command(call: ServiceCall) -> None:
        device_id = call.data["device_id"]
        command = call.data["command"]
        run_as_user = call.data.get("run_as_user", False)

        # Find coordinator and node_id from device_id
        coordinator, node_id = _find_node(hass, device_id)
        if not coordinator or not node_id:
            _LOGGER.error("run_command: device '%s' not found in MeshCentral", device_id)
            return

        node = coordinator.data.get(node_id, {})
        if node.get("conn", 0) != 1:
            _LOGGER.warning(
                "run_command: device '%s' is offline, command not sent", node.get("name")
            )
            return

        result = await coordinator.client.run_command(node_id, command, run_as_user)
        if result is not None:
            _LOGGER.info(
                "run_command on '%s': %s", node.get("name"), result[:200] if result else "(no output)"
            )
        else:
            _LOGGER.warning("run_command on '%s' returned no response", node.get("name"))

    hass.services.async_register(
        DOMAIN,
        SERVICE_RUN_COMMAND,
        handle_run_command,
        schema=SERVICE_RUN_COMMAND_SCHEMA,
    )


def _find_node(hass: HomeAssistant, device_id: str):
    """Find coordinator + node_id for a given device name or node_id."""
    for key, value in hass.data.get(DOMAIN, {}).items():
        if not isinstance(value, MeshCentralCoordinator):
            continue
        coordinator: MeshCentralCoordinator = value
        # Match by node_id or device name
        for node_id, node in coordinator.data.items():
            if node_id == device_id or node.get("name", "").lower() == device_id.lower():
                return coordinator, node_id
    return None, None
