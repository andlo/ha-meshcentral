"""Native HA update entity for the MeshCentral server core version (#43)."""
from __future__ import annotations

from homeassistant.components.update import UpdateEntity, UpdateEntityFeature
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import MeshCentralCoordinator
from .sensor_serverversion import ServerVersionCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    main: MeshCentralCoordinator = hass.data[DOMAIN][entry.entry_id]
    coordinator: ServerVersionCoordinator = hass.data[DOMAIN][f"{entry.entry_id}_serverversion"]
    async_add_entities([MeshCentralUpdateEntity(coordinator, main, entry.entry_id)])


class MeshCentralUpdateEntity(CoordinatorEntity[ServerVersionCoordinator], UpdateEntity):
    """Informational-only update entity for the MeshCentral server core.

    This intentionally does NOT support an install action. The integration
    can't assume how any given MeshCentral server is hosted (add-on vs. bare
    install vs. someone else's Docker setup), so it has never attempted to
    trigger updates itself — that decision stands. This entity only adds
    HA's native Settings -> Updates badge/notification on top of the
    installed/latest-available values the sensor pair already tracked,
    it doesn't change what the integration is allowed to do.
    """

    _attr_has_entity_name = True
    _attr_name = "MeshCentral Core"
    _attr_icon = "mdi:server"
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_supported_features = UpdateEntityFeature(0)

    def __init__(self, coordinator: ServerVersionCoordinator, main: MeshCentralCoordinator, entry_id: str) -> None:
        super().__init__(coordinator)
        self._entry_id = entry_id
        self._main = main
        self._attr_unique_id = f"mc_{entry_id}_server_update"

    @property
    def installed_version(self) -> str | None:
        return self.coordinator.data.get("installed")

    @property
    def latest_version(self) -> str | None:
        return self.coordinator.data.get("latest")

    @property
    def device_info(self):
        return {
            "identifiers": {(DOMAIN, f"{self._entry_id}_server")},
            "name": "MeshCentral Server",
            "manufacturer": "MeshCentral",
            "configuration_url": self._main.client.base_url,
        }
