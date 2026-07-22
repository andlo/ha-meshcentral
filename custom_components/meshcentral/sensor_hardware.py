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
from homeassistant.helpers.restore_state import RestoreEntity, RestoredExtraData
from homeassistant.helpers.update_coordinator import (
    CoordinatorEntity,
    DataUpdateCoordinator,
    UpdateFailed,
)

from .const import CONF_HW_SCAN_INTERVAL, DEFAULT_HW_SCAN_INTERVAL, DOMAIN
from .coordinator import MeshCentralCoordinator

_LOGGER = logging.getLogger(__name__)


def _win_volume_slug(drive_letter: str) -> str:
    """Turn a Windows drive letter (e.g. 'D') into an entity-id-safe slug."""
    return drive_letter.strip().rstrip(":").lower()


def _linux_mount_slug(mount_point: str) -> str:
    """Turn a Linux mount point (e.g. '/home') into an entity-id-safe slug."""
    if mount_point in ("/", ""):
        return "root"
    return mount_point.strip("/").replace("/", "_").lower() or "root"


class HardwareDataCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Coordinator that fetches getsysinfo for all online devices."""

    def __init__(self, hass: HomeAssistant, main: MeshCentralCoordinator) -> None:
        minutes = main.entry.options.get(CONF_HW_SCAN_INTERVAL, DEFAULT_HW_SCAN_INTERVAL)
        super().__init__(
            hass, _LOGGER,
            name=f"{DOMAIN}_hardware",
            update_interval=timedelta(minutes=minutes),
        )
        self._main = main

    async def _async_update_data(self) -> dict[str, Any]:
        # Start from the previous poll's data so devices that are offline
        # right now (or that just went offline) keep showing their last
        # known-good hardware data instead of flipping to unavailable —
        # only a device that has *never* reported anything is missing here.
        result = dict(self.data or {})
        for node_id, node in self._main.data.items():
            if node.get("conn", 0) != 1:
                continue  # skip offline devices — leave any previous entry as-is
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
                ProcessCountSensor(hw_coordinator, main, node_id),
                ScreenResolutionSensor(hw_coordinator, main, node_id),
            ]
            # Battery — created for every Windows device, same as the other
            # hardware sensors. Gating creation on hw.get("battery") here
            # would hit the exact bug from #24: if the device happens to be
            # offline during initial setup there's no hw data yet, so the
            # entity would never be created at all (not just unavailable).
            # Desktops without a battery simply report unavailable, and
            # this is disabled-by-default anyway. Charging state and health
            # are exposed as attributes rather than a separate binary_sensor
            # to keep everything on this one coordinator/platform.
            entities.append(BatteryLevelSensor(hw_coordinator, main, node_id))
            win_volumes = hw.get("windows", {}).get("volumes", {})
            if win_volumes:
                for drive_letter in win_volumes:
                    entities += [
                        WindowsDiskTotalSensor(hw_coordinator, main, node_id, drive_letter),
                        WindowsDiskFreeSensor(hw_coordinator, main, node_id, drive_letter),
                        WindowsDiskFreePercentSensor(hw_coordinator, main, node_id, drive_letter),
                    ]
            else:
                # No sysinfo fetched yet for this device — fall back to the
                # C: drive so entities still get created on first setup.
                entities += [
                    WindowsDiskTotalSensor(hw_coordinator, main, node_id, "C"),
                    WindowsDiskFreeSensor(hw_coordinator, main, node_id, "C"),
                    WindowsDiskFreePercentSensor(hw_coordinator, main, node_id, "C"),
                ]

        # Linux
        if is_linux:
            linux_volumes = hw.get("linux", {}).get("volumes", [])
            mount_points = [v.get("mount_point") for v in linux_volumes if v.get("mount_point")]
            if not mount_points:
                mount_points = ["/"]
            for mount_point in mount_points:
                entities += [
                    LinuxDiskUsedSensor(hw_coordinator, main, node_id, mount_point),
                    LinuxDiskFreeSensor(hw_coordinator, main, node_id, mount_point),
                ]

    async_add_entities(entities)


class _HwBase(CoordinatorEntity[HardwareDataCoordinator], SensorEntity, RestoreEntity):
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
        self._restored_hw: dict | None = None

    async def async_added_to_hass(self) -> None:
        """Restore the last known getsysinfo payload across HA restarts.

        The hardware coordinator only ever holds data for devices that were
        online during this HA run. If a device is offline when HA (re)starts,
        coordinator.data has nothing for it yet — without this, every
        hardware sensor would sit at `unavailable` until the device happens
        to come online, even though MeshCentral itself still reports the
        last known values on its own Details tab.
        """
        await super().async_added_to_hass()
        if not self.coordinator.data.get(self._node_id):
            last_extra_data = await self.async_get_last_extra_data()
            if last_extra_data is not None:
                self._restored_hw = last_extra_data.as_dict()

    @property
    def extra_restore_state_data(self) -> RestoredExtraData | None:
        """Persist whichever hw dict is currently backing this entity."""
        hw = self._hw
        return RestoredExtraData(hw) if hw else None

    @property
    def _hw(self) -> dict:
        live = self.coordinator.data.get(self._node_id)
        if live:
            return live
        return self._restored_hw or {}

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


class WindowsDiskTotalSensor(_HwBase):
    _attr_icon = "mdi:harddisk"
    _attr_native_unit_of_measurement = UnitOfInformation.GIGABYTES
    _attr_device_class = SensorDeviceClass.DATA_SIZE
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, coordinator, main, node_id, drive_letter: str):
        super().__init__(coordinator, main, node_id)
        self._drive_letter = drive_letter
        self._attr_name = f"Disk {drive_letter}: Total"
        if drive_letter.upper() == "C":
            # Keep the original unique_id for backwards compatibility.
            self._attr_unique_id = f"mc_{node_id}_hw_disk_total"
        else:
            slug = _win_volume_slug(drive_letter)
            self._attr_unique_id = f"mc_{node_id}_hw_disk_{slug}_total"

    @property
    def native_value(self):
        vol = self._win.get("volumes", {}).get(self._drive_letter, {})
        size = vol.get("size", 0)
        return round(size / (1024 ** 3), 1) if size else None


class WindowsDiskFreeSensor(_HwBase):
    _attr_icon = "mdi:harddisk"
    _attr_native_unit_of_measurement = UnitOfInformation.GIGABYTES
    _attr_device_class = SensorDeviceClass.DATA_SIZE
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, coordinator, main, node_id, drive_letter: str):
        super().__init__(coordinator, main, node_id)
        self._drive_letter = drive_letter
        self._attr_name = f"Disk {drive_letter}: Free"
        if drive_letter.upper() == "C":
            self._attr_unique_id = f"mc_{node_id}_hw_disk_free"
        else:
            slug = _win_volume_slug(drive_letter)
            self._attr_unique_id = f"mc_{node_id}_hw_disk_{slug}_free"

    @property
    def native_value(self):
        vol = self._win.get("volumes", {}).get(self._drive_letter, {})
        free = vol.get("sizeremaining", 0)
        return round(free / (1024 ** 3), 1) if free else None


class WindowsDiskFreePercentSensor(_HwBase):
    _attr_icon = "mdi:harddisk"
    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, coordinator, main, node_id, drive_letter: str):
        super().__init__(coordinator, main, node_id)
        self._drive_letter = drive_letter
        self._attr_name = f"Disk {drive_letter}: Free %"
        if drive_letter.upper() == "C":
            self._attr_unique_id = f"mc_{node_id}_hw_disk_pct"
        else:
            slug = _win_volume_slug(drive_letter)
            self._attr_unique_id = f"mc_{node_id}_hw_disk_{slug}_pct"

    @property
    def native_value(self):
        vol = self._win.get("volumes", {}).get(self._drive_letter, {})
        size = vol.get("size", 0)
        free = vol.get("sizeremaining", 0)
        if size and free:
            return round(free / size * 100, 1)
        return None


class BatteryLevelSensor(_HwBase):
    """Battery charge level for laptops.

    Confirmed live (see #25) — MeshCentral does NOT pass this through raw
    from WMI like memory/osinfo/gpu do; it's its own normalized format:

        "battery": [{
            "InstanceName": "ACPI\\PNP0C0A\\0_0",
            "CycleCount": 60,
            "FullChargedCapacity": 60228,
            "EstimatedRuntime": -1,
            "Chemistry": "LIon",
            "DesignedCapacity": 75998,
            "DeviceName": "ASUS Battery",
            "ManufactureName": "ASUSTeK",
            "SerialNumber": " ",
            "ChargeRate": 0,
            "Charging": false,
            "DischargeRate": 0,
            "Discharging": true,
            "RemainingCapacity": 48100,
            "Voltage": 15833,
            "Health": 79,
            "BatteryCharge": 79
        }]

    "battery" is a list (multi-battery devices exist), but every device
    seen so far only has one entry — only the first is used for now.
    "BatteryCharge" is the charge percentage; "Health" is a separate
    state-of-health percentage (not the same field, despite matching in
    this particular sample). "Charging"/"Discharging" are plain booleans —
    no status-code guessing needed.
    """

    _attr_name = "Battery"
    _attr_icon = "mdi:battery"
    _attr_device_class = SensorDeviceClass.BATTERY
    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, coordinator, main, node_id):
        super().__init__(coordinator, main, node_id)
        self._attr_unique_id = f"mc_{node_id}_hw_battery"

    @property
    def _battery(self) -> dict:
        # NOTE: "battery" is a sibling of "windows" directly under
        # "hardware" (hardware.battery), NOT hardware.windows.battery like
        # memory/osinfo/cpu/gpu/volumes are. Confirmed against two live
        # payloads on #25 — the first beta used self._win by mistake, which
        # is why it stayed unavailable even with correct field names.
        batteries = self._hw.get("battery", [])
        return batteries[0] if batteries else {}

    @property
    def native_value(self):
        pct = self._battery.get("BatteryCharge")
        return int(pct) if pct is not None else None

    @property
    def available(self) -> bool:
        return bool(self._battery)

    @property
    def extra_state_attributes(self):
        b = self._battery
        return {
            "charging": b.get("Charging"),
            "discharging": b.get("Discharging"),
            "health_percent": b.get("Health"),
            "chemistry": b.get("Chemistry"),
            "cycle_count": b.get("CycleCount"),
            "design_capacity": b.get("DesignedCapacity"),
            "full_charge_capacity": b.get("FullChargedCapacity"),
            "remaining_capacity": b.get("RemainingCapacity"),
            "estimated_runtime_min": b.get("EstimatedRuntime"),
            "device_name": b.get("DeviceName"),
        }


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
    _attr_icon = "mdi:harddisk"
    _attr_native_unit_of_measurement = UnitOfInformation.MEGABYTES
    _attr_device_class = SensorDeviceClass.DATA_SIZE
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, coordinator, main, node_id, mount_point: str):
        super().__init__(coordinator, main, node_id)
        self._mount_point = mount_point
        self._attr_name = f"Disk {mount_point} Used"
        if mount_point == "/":
            # Keep the original unique_id for backwards compatibility.
            self._attr_unique_id = f"mc_{node_id}_hw_linux_disk_used"
        else:
            slug = _linux_mount_slug(mount_point)
            self._attr_unique_id = f"mc_{node_id}_hw_linux_disk_{slug}_used"

    @property
    def native_value(self):
        for vol in self._linux.get("volumes", []):
            if vol.get("mount_point") == self._mount_point:
                used = vol.get("used", 0)
                return round(int(used) / 1024, 1) if used else None
        return None


class LinuxDiskFreeSensor(_HwBase):
    _attr_icon = "mdi:harddisk"
    _attr_native_unit_of_measurement = UnitOfInformation.MEGABYTES
    _attr_device_class = SensorDeviceClass.DATA_SIZE
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, coordinator, main, node_id, mount_point: str):
        super().__init__(coordinator, main, node_id)
        self._mount_point = mount_point
        self._attr_name = f"Disk {mount_point} Free"
        if mount_point == "/":
            self._attr_unique_id = f"mc_{node_id}_hw_linux_disk_free"
        else:
            slug = _linux_mount_slug(mount_point)
            self._attr_unique_id = f"mc_{node_id}_hw_linux_disk_{slug}_free"

    @property
    def native_value(self):
        for vol in self._linux.get("volumes", []):
            if vol.get("mount_point") == self._mount_point:
                avail = vol.get("available", 0)
                return round(int(avail) / 1024, 1) if avail else None
        return None
