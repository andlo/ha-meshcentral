"""Services for MeshCentral integration."""
from __future__ import annotations

import logging

import voluptuous as vol
from homeassistant.core import HomeAssistant, ServiceCall, ServiceResponse, SupportsResponse
from homeassistant.helpers import config_validation as cv
from homeassistant.components.persistent_notification import async_create as async_create_notification

from .const import CONN_AGENT, DOMAIN
from .coordinator import MeshCentralCoordinator

_LOGGER = logging.getLogger(__name__)

SERVICE_RUN_COMMAND = "run_command"
SERVICE_RUN_CONSOLE_COMMAND = "run_console_command"
EVENT_COMMAND_RESULT = "meshcentral_command_result"
EVENT_CONSOLE_COMMAND_RESULT = "meshcentral_console_command_result"

SERVICE_RUN_COMMAND_SCHEMA = vol.Schema(
    {
        vol.Required("device_id"): cv.string,
        vol.Required("command"): cv.string,
        vol.Optional("run_as_user", default=False): cv.boolean,
        vol.Optional("wait_for_output", default=True): cv.boolean,
        vol.Optional("powershell", default=False): cv.boolean,
        vol.Optional("notify", default=False): cv.boolean,
    }
)

SERVICE_RUN_CONSOLE_COMMAND_SCHEMA = vol.Schema(
    {
        vol.Required("device_id"): vol.All(cv.ensure_list, [cv.string]),
        vol.Required("command"): cv.string,
        vol.Optional("notify", default=False): cv.boolean,
    }
)


def async_register_services(hass: HomeAssistant) -> None:
    """Register MeshCentral services."""

    async def handle_run_command(call: ServiceCall) -> ServiceResponse:
        device_id = call.data["device_id"]
        command = call.data["command"]
        run_as_user = call.data.get("run_as_user", False)
        wait_for_output = call.data.get("wait_for_output", True)
        powershell = call.data.get("powershell", False)
        notify = call.data.get("notify", False)

        # Find coordinator and node_id from device_id
        coordinator, node_id = _find_node(hass, device_id)
        if not coordinator or not node_id:
            _LOGGER.error("run_command: device '%s' not found in MeshCentral", device_id)
            return {"success": False, "device": device_id, "command": command, "output": None}

        # A complete raw node ID can be used even before device discovery has
        # populated the local cache. Only enforce the cached agent check when
        # the node is present in coordinator data.
        node = (coordinator.data or {}).get(node_id)
        device_name = node.get("name", device_id) if node else device_id

        # run_command needs the agent specifically — "conn" is a bitmask,
        # so check the agent bit rather than requiring conn == 1 exactly
        # (a device also connected via CIRA/AMT alongside the agent was
        # being wrongly treated as offline here) (#26).
        if node is not None and not (node.get("conn", 0) & CONN_AGENT):
            _LOGGER.warning("run_command: device '%s' is offline, command not sent", device_name)
            return {"success": False, "device": device_name, "command": command, "output": None}

        result = await coordinator.client.run_command(
            node_id, command, run_as_user, wait_for_output, powershell
        )
        success = result is not None

        if success:
            _LOGGER.info(
                "run_command on '%s': %s", device_name, result[:200] if result else "(no output)"
            )
        else:
            _LOGGER.warning("run_command on '%s' returned no response", device_name)

        hass.bus.async_fire(
            EVENT_COMMAND_RESULT,
            {
                "device_id": node_id,
                "device_name": device_name,
                "command": command,
                "run_as_user": run_as_user,
                "wait_for_output": wait_for_output,
                "powershell": powershell,
                "success": success,
                "output": result,
            },
        )

        if notify:
            async_create_notification(
                hass,
                f"Command: `{command}`\n\n```\n{result or '(no output)'}\n```",
                title=f"MeshCentral: {device_name}",
                notification_id=f"meshcentral_run_command_{node_id}",
            )

        return {"success": success, "device": device_name, "command": command, "output": result}

    async def handle_run_console_command(call: ServiceCall) -> ServiceResponse:
        """Send a MeshCentral agent console command (e.g. "apf cira", "info").

        Different from run_command: these are MeshCentral's own built-in
        agent console commands (see the device's Console tab in the
        MeshCentral web UI — "help" lists them), not OS shell commands.
        Requires the account to hold the "agentconsole" right on the
        device/mesh, or MeshCentral will accept the request but never
        reply, and this will time out (#28).

        Accepts one or more device_id entries, targeted in as few requests
        as possible (one per MeshCentral server involved, since the
        underlying protocol already accepts a list of node IDs per call).
        """
        device_ids: list[str] = call.data["device_id"]
        command = call.data["command"]
        notify = call.data.get("notify", False)

        results: dict[str, dict] = {}

        # Resolve every requested device first, and group the ones that
        # were found by coordinator so each MeshCentral server involved
        # gets a single run_console_command call covering all its targets.
        by_coordinator: dict[MeshCentralCoordinator, list[tuple[str, str]]] = {}
        for device_id in device_ids:
            coordinator, node_id = _find_node(hass, device_id)
            if not coordinator or not node_id:
                _LOGGER.error(
                    "run_console_command: device '%s' not found in MeshCentral",
                    device_id,
                )
                results[device_id] = {"success": False, "output": None}
                continue

            node = (coordinator.data or {}).get(node_id)
            device_name = node.get("name", device_id) if node else device_id

            if node is not None and not (node.get("conn", 0) & CONN_AGENT):
                _LOGGER.warning(
                    "run_console_command: device '%s' is offline, command not sent",
                    device_name,
                )
                results[device_name] = {"success": False, "output": None}
                continue

            by_coordinator.setdefault(coordinator, []).append((node_id, device_name))

        for coordinator, targets in by_coordinator.items():
            node_ids = [node_id for node_id, _ in targets]
            outputs = await coordinator.client.run_console_command(node_ids, command)

            for node_id, device_name in targets:
                output = outputs.get(node_id)
                success = output is not None
                results[device_name] = {"success": success, "output": output}

                if success:
                    _LOGGER.info(
                        "run_console_command on '%s': %s",
                        device_name,
                        output[:200] if output else "(no output)",
                    )
                else:
                    _LOGGER.warning(
                        "run_console_command on '%s' returned no response — check "
                        "the account has the 'agentconsole' right on this device/mesh",
                        device_name,
                    )

                hass.bus.async_fire(
                    EVENT_CONSOLE_COMMAND_RESULT,
                    {
                        "device_id": node_id,
                        "device_name": device_name,
                        "command": command,
                        "success": success,
                        "output": output,
                    },
                )

        if notify:
            blocks = "\n\n".join(
                f"**{name}**\n```\n{r['output'] or '(no output)'}\n```"
                for name, r in results.items()
            )
            async_create_notification(
                hass,
                f"Console command: `{command}`\n\n{blocks}",
                title="MeshCentral console command",
                notification_id=f"meshcentral_run_console_command_{'_'.join(device_ids)[:100]}",
            )

        return {
            "command": command,
            "success": all(r["success"] for r in results.values()) if results else False,
            "results": results,
        }

    hass.services.async_register(
        DOMAIN,
        SERVICE_RUN_COMMAND,
        handle_run_command,
        schema=SERVICE_RUN_COMMAND_SCHEMA,
        supports_response=SupportsResponse.OPTIONAL,
    )

    hass.services.async_register(
        DOMAIN,
        SERVICE_RUN_CONSOLE_COMMAND,
        handle_run_console_command,
        schema=SERVICE_RUN_CONSOLE_COMMAND_SCHEMA,
        supports_response=SupportsResponse.OPTIONAL,
    )


def _find_node(hass: HomeAssistant, device_id: str):
    """Find a coordinator and node ID by exact ID or device name."""
    coordinators: list[MeshCentralCoordinator] = []

    for value in hass.data.get(DOMAIN, {}).values():
        if not isinstance(value, MeshCentralCoordinator):
            continue

        coordinator: MeshCentralCoordinator = value
        coordinators.append(coordinator)
        for node_id, node in (coordinator.data or {}).items():
            if node_id == device_id:
                return coordinator, node_id
            if node.get("name", "").casefold() == device_id.casefold():
                return coordinator, node_id

    # A full node ID is unambiguous when exactly one MeshCentral server exists.
    if device_id.startswith("node/") and len(coordinators) == 1:
        return coordinators[0], device_id

    return None, None
