"""MeshCentral integration for Home Assistant."""
from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er

from .const import CONF_ENTITY_CATEGORIES, DOMAIN, categorize_entity_unique_id
from .coordinator import MeshCentralCoordinator
from .sensor_serverversion import ServerVersionCoordinator
from .services import async_register_services

_LOGGER = logging.getLogger(__name__)

PLATFORMS = [
    Platform.BINARY_SENSOR,
    Platform.SENSOR,
    Platform.BUTTON,
    Platform.DEVICE_TRACKER,
    Platform.UPDATE,
]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up MeshCentral from a config entry."""
    coordinator = MeshCentralCoordinator(hass, entry)

    try:
        await coordinator.async_config_entry_first_refresh()
    except Exception as err:
        raise ConfigEntryNotReady(f"Cannot connect to MeshCentral: {err}") from err

    _async_cleanup_deselected_devices(hass, entry, coordinator)
    _async_cleanup_deselected_categories(hass, entry)

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator

    # Created here — not inside sensor.py's own setup — and stored before
    # forwarding platforms, because async_forward_entry_setups() sets up
    # SENSOR and UPDATE concurrently (#43). UPDATE reads this coordinator
    # from hass.data too, so it can't rely on SENSOR having created it
    # first; both platforms would otherwise race on which one wins.
    version_coordinator = ServerVersionCoordinator(hass, coordinator)
    await version_coordinator.async_config_entry_first_refresh()
    hass.data[DOMAIN][f"{entry.entry_id}_serverversion"] = version_coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # Register services (only once across all entries)
    if not hass.services.has_service(DOMAIN, "run_command"):
        async_register_services(hass)

    # Reload the entry whenever its options change (e.g. poll interval)
    entry.async_on_unload(entry.add_update_listener(async_update_listener))

    return True


async def async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload the config entry when its options are updated."""
    await hass.config_entries.async_reload(entry.entry_id)


def _async_cleanup_deselected_devices(
    hass: HomeAssistant, entry: ConfigEntry, coordinator: MeshCentralCoordinator
) -> None:
    """Remove devices that fell outside the group filter (#47).

    coordinator.all_devices is the unfiltered list from the fetch that just
    ran; coordinator.data is the same fetch after the selected-groups
    filter. Any node still present in the former but not the latter is a
    device that genuinely still exists on the MeshCentral server but was
    just excluded by the current group selection — remove its HA device
    (which cascades to its entities) so it doesn't linger as an orphaned
    "unavailable" entry. Devices that no longer exist on the server at all
    (removed in MeshCentral itself) are left untouched here, unchanged
    from the integration's behavior before this filter existed.
    """
    all_node_ids = {d["_id"] for d in coordinator.all_devices if "_id" in d}
    selected_node_ids = set(coordinator.data or {})
    stale_node_ids = all_node_ids - selected_node_ids
    if not stale_node_ids:
        return

    device_registry = dr.async_get(hass)
    for device in dr.async_entries_for_config_entry(device_registry, entry.entry_id):
        node_id = next(
            (
                identifier[1]
                for identifier in device.identifiers
                if identifier[0] == DOMAIN and identifier[1] in stale_node_ids
            ),
            None,
        )
        if node_id is not None:
            _LOGGER.info(
                "Removing device %s (%s) — excluded by the device group filter",
                device.name,
                node_id,
            )
            device_registry.async_remove_device(device.id)


def _async_cleanup_deselected_categories(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Remove entities that fell outside the entity category filter (#47).

    Unlike the group filter, this never touches a whole device — only the
    specific entities belonging to a deselected category. It works purely
    off the entity registry (categorize_entity_unique_id), not live data,
    since the category list is static rather than fetched from the server.
    An empty selection means "all categories", so there's nothing to do.
    """
    active = entry.options.get(CONF_ENTITY_CATEGORIES) or []
    if not active:
        return

    entity_registry = er.async_get(hass)
    for entity in er.async_entries_for_config_entry(entity_registry, entry.entry_id):
        category = categorize_entity_unique_id(entity.unique_id)
        if category is not None and category not in active:
            _LOGGER.info(
                "Removing entity %s — excluded by the entity category filter",
                entity.entity_id,
            )
            entity_registry.async_remove(entity.entity_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        coordinator: MeshCentralCoordinator = hass.data[DOMAIN].pop(entry.entry_id)
        await coordinator.async_shutdown()
        hass.data[DOMAIN].pop(f"{entry.entry_id}_hw", None)
        hass.data[DOMAIN].pop(f"{entry.entry_id}_serverversion", None)
        hass.data[DOMAIN].pop(f"{entry.entry_id}_serverstats", None)
    return unload_ok


async def async_remove_config_entry_device(
    hass: HomeAssistant, entry: ConfigEntry, device_entry
) -> bool:
    """Allow removing a device from the UI."""
    return True


async def async_migrate_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Handle migration of old config entries."""
    return True
