"""Hardware detail sensors for MeshCentral devices.

These sensors are fetched via a separate getsysinfo call and polled
every 5 minutes. They are only created for devices that actually return
the relevant data (Windows vs Linux, etc.).
"""
from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity, SensorStateClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import PERCENTAGE, UnitOfInformation
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import (
    CoordinatorEntity,
    DataUpdateCoordinator,
    UpdateFailed,
)

from .const import DOMAIN
from .coordinator import MeshCentralCoordinator

_LOGGER = logging.getLogger(__name__)


class HardwareDataCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Coordinator that fetches getsysinfo for all online devices every 5 min."""

    def __init__(self, hass: HomeAssistant, main: MeshCentralCoordinator) -> None:
        super().__init__(
            hass, _LOGGER,
            name=f"{DOMAIN}_hardware",
            update_interval=timedelta(minutes=5),
        )
        self._main = main

    async def _async_update_data(self) -> dict[str, Any]:
        result = {}
        for node_id, node in self._main.data.items():
            if node.get("conn", 0) != 1:
                continue  # skip offline devices
            try:
                hw = await self._main.client.get_sysinfo(node_id)
                if hw:
                    result[node_id] = hw
            except Exception as err:
                _LOGGER.debug("Could not get sysinfo for %s: %s", node.get("name"), err)
        return result


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Not used directly — called from sensor.py via async_setup_hardware_entities."""
    pass


async def async_setup_hardware_entities(
    hass: HomeAssistant,
    entry: ConfigEntry,
    main: MeshCentralCoordinator,
    hw_coordinator: HardwareDataCoordinator,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Create hardware sensor entities for all devices."""
    entities: list[SensorEntity] = []
    for node_id in main.data:
        node = main.data[node_id]
        hw = hw_coordinator.data.get(node_id, {})
        is_windows = "windows" in hw or node.get("osdesc", "").lower().startswith("microsoft")
        is_linux = "linux" in hw or ("linux" in node.get("osdesc", "").lower() and not is_windows)

        # Universal
        entities += [
            CpuNameSensor(hw_coordinator, main, node_id),
            GpuNameSensor(hw_coordinator, main, node_id),
            BiosVersionSensor(hw_coordinator, main, node_id),
            BoardNameSensor(hw_coordinator, main, node_id),
        ]

        # Windows
        if is_windows:
            entities += [
                RamTotalSensor(hw_coordinator, main, node_id),
                DiskTotalSensor(hw_coordinator, main, node_id),
                DiskFreeSensor(hw_coordinator, main, node_id),
                DiskFreePercentSensor(hw_coordinator, main, node_id),
                ProcessCountSensor(hw_coordinator, main, node_id),
                ScreenResolutionSensor(hw_coordinator, main, node_id),
            ]

        # Linux
        if is_linux:
            entities += [
                LinuxDiskUsedSensor(hw_coordinator, main, node_id),
                LinuxDiskFreeSensor(hw_coordinator, main, node_id),
            ]

    async_add_entities(entities)


class _HwBase(CoordinatorEntity[HardwareDataCoordinator], SensorEntity):
    _attr_has_entity_name = True
    _attr_entity_registry_enabled_default = False  # disabled by default — "advanced"

    def __init__(
        self,
        coordinator: HardwareDataCoordinator,
        main: MeshCentralCoordinator,
        node_id: str,
    ) -> None:
        super().__init__(coordinator)
        self._node_id = node_id
        self._main = main

    @property
    def _hw(self) -> dict:
        return self.coordinator.data.get(self._node_id, {})

    @property
    def _win(self) -> dict:
        return self._hw.get("windows", {})

    @property
    def _linux(self) -> dict:
        return self._hw.get("linux", {})

    @property
    def _ids(self) -> dict:
        return self._hw.get("identifiers", {})

    @property
    def device_info(self):
        node = self._main.data.get(self._node_id, {})
        return {
            "identifiers": {(DOMAIN, self._node_id)},
            "name": node.get("name", self._node_id),
            "manufacturer": "MeshCentral",
            "model": node.get("osdesc", "Unknown OS"),
        }

    @property
    def available(self) -> bool:
        return bool(self._hw)


# ── Universal sensors ──────────────────────────────────────────────────────────

class CpuNameSensor(_HwBase):
    _attr_name = "CPU"
    _attr_icon = "mdi:chip"

    def __init__(self, coordinator, main, node_id):
        super().__init__(coordinator, main, node_id)
        self._attr_unique_id = f"mc_{node_id}_hw_cpu"

    @property
    def native_value(self):
        return self._ids.get("cpu_name", "").strip() or None


class GpuNameSensor(_HwBase):
    _attr_name = "GPU"
    _attr_icon = "mdi:expansion-card"

    def __init__(self, coordinator, main, node_id):
        super().__init__(coordinator, main, node_id)
        self._attr_unique_id = f"mc_{node_id}_hw_gpu"

    @property
    def native_value(self):
        gpus = self._ids.get("gpu_name", [])
        return ", ".join(gpus) if gpus else None


class BiosVersionSensor(_HwBase):
    _attr_name = "BIOS Version"
    _attr_icon = "mdi:memory"

    def __init__(self, coordinator, main, node_id):
        super().__init__(coordinator, main, node_id)
        self._attr_unique_id = f"mc_{node_id}_hw_bios"

    @property
    def native_value(self):
        return self._ids.get("bios_version") or None

    @property
    def extra_state_attributes(self):
        return {
            "vendor": self._ids.get("bios_vendor"),
            "date": self._ids.get("bios_date"),
            "mode": self._ids.get("bios_mode"),
        }


class BoardNameSensor(_HwBase):
    _attr_name = "Motherboard"
    _attr_icon = "mdi:developer-board"

    def __init__(self, coordinator, main, node_id):
        super().__init__(coordinator, main, node_id)
        self._attr_unique_id = f"mc_{node_id}_hw_board"

    @property
    def native_value(self):
        return self._ids.get("board_name") or None

    @property
    def extra_state_attributes(self):
        return {
            "vendor": self._ids.get("board_vendor"),
        }


# ── Windows sensors ────────────────────────────────────────────────────────────

class RamTotalSensor(_HwBase):
    _attr_name = "RAM Total"
    _attr_icon = "mdi:memory"
    _attr_native_unit_of_measurement = UnitOfInformation.GIGABYTES
    _attr_device_class = SensorDeviceClass.DATA_SIZE
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, coordinator, main, node_id):
        super().__init__(coordinator, main, node_id)
        self._attr_unique_id = f"mc_{node_id}_hw_ram"

    @property
    def native_value(self):
        mem = self._win.get("memory", [])
        if not mem:
            # Linux fallback
            lmem = self._linux.get("memory", {})
            devices = lmem.get("Memory_Device", [])
            total_str = None
            for d in devices:
                s = d.get("Size", "")
                if "GB" in s:
                    try:
                        return float(s.replace("GB", "").strip())
                    except ValueError:
                        pass
            return None
        total = sum(int(m.get("Capacity", 0)) for m in mem)
        return round(total / (1024 ** 3), 1) if total else None


class DiskTotalSensor(_HwBase):
    _attr_name = "Disk C: Total"
    _attr_icon = "mdi:harddisk"
    _attr_native_unit_of_measurement = UnitOfInformation.GIGABYTES
    _attr_device_class = SensorDeviceClass.DATA_SIZE
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, coordinator, main, node_id):
        super().__init__(coordinator, main, node_id)
        self._attr_unique_id = f"mc_{node_id}_hw_disk_total"

    @property
    def native_value(self):
        vol = self._win.get("volumes", {}).get("C", {})
        size = vol.get("size", 0)
        return round(size / (1024 ** 3), 1) if size else None


class DiskFreeSensor(_HwBase):
    _attr_name = "Disk C: Free"
    _attr_icon = "mdi:harddisk"
    _attr_native_unit_of_measurement = UnitOfInformation.GIGABYTES
    _attr_device_class = SensorDeviceClass.DATA_SIZE
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, coordinator, main, node_id):
        super().__init__(coordinator, main, node_id)
        self._attr_unique_id = f"mc_{node_id}_hw_disk_free"

    @property
    def native_value(self):
        vol = self._win.get("volumes", {}).get("C", {})
        free = vol.get("sizeremaining", 0)
        return round(free / (1024 ** 3), 1) if free else None


class DiskFreePercentSensor(_HwBase):
    _attr_name = "Disk C: Free %"
    _attr_icon = "mdi:harddisk"
    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, coordinator, main, node_id):
        super().__init__(coordinator, main, node_id)
        self._attr_unique_id = f"mc_{node_id}_hw_disk_pct"

    @property
    def native_value(self):
        vol = self._win.get("volumes", {}).get("C", {})
        size = vol.get("size", 0)
        free = vol.get("sizeremaining", 0)
        if size and free:
            return round(free / size * 100, 1)
        return None


class ProcessCountSensor(_HwBase):
    _attr_name = "Running Processes"
    _attr_icon = "mdi:application-cog"
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, coordinator, main, node_id):
        super().__init__(coordinator, main, node_id)
        self._attr_unique_id = f"mc_{node_id}_hw_procs"

    @property
    def native_value(self):
        return self._win.get("osinfo", {}).get("NumberOfProcesses")


class ScreenResolutionSensor(_HwBase):
    _attr_name = "Screen Resolution"
    _attr_icon = "mdi:monitor"

    def __init__(self, coordinator, main, node_id):
        super().__init__(coordinator, main, node_id)
        self._attr_unique_id = f"mc_{node_id}_hw_resolution"

    @property
    def native_value(self):
        gpus = self._win.get("gpu", [])
        if gpus:
            g = gpus[0]
            w = g.get("CurrentHorizontalResolution")
            h = g.get("CurrentVerticalResolution")
            if w and h:
                return f"{w}x{h}"
        return None


# ── Linux sensors ──────────────────────────────────────────────────────────────

class LinuxDiskUsedSensor(_HwBase):
    _attr_name = "Disk / Used"
    _attr_icon = "mdi:harddisk"
    _attr_native_unit_of_measurement = UnitOfInformation.MEGABYTES
    _attr_device_class = SensorDeviceClass.DATA_SIZE
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, coordinator, main, node_id):
        super().__init__(coordinator, main, node_id)
        self._attr_unique_id = f"mc_{node_id}_hw_linux_disk_used"

    @property
    def native_value(self):
        for vol in self._linux.get("volumes", []):
            if vol.get("mount_point") == "/":
                used = vol.get("used", 0)
                return round(int(used) / 1024, 1) if used else None
        return None


class LinuxDiskFreeSensor(_HwBase):
    _attr_name = "Disk / Free"
    _attr_icon = "mdi:harddisk"
    _attr_native_unit_of_measurement = UnitOfInformation.MEGABYTES
    _attr_device_class = SensorDeviceClass.DATA_SIZE
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, coordinator, main, node_id):
        super().__init__(coordinator, main, node_id)
        self._attr_unique_id = f"mc_{node_id}_hw_linux_disk_free"

    @property
    def native_value(self):
        for vol in self._linux.get("volumes", []):
            if vol.get("mount_point") == "/":
                avail = vol.get("available", 0)
                return round(int(avail) / 1024, 1) if avail else None
        return None
