# Development Notes

This document captures technical findings and gotchas discovered while building this integration. Useful for contributors and for picking up development after a break.

## MeshCentral WebSocket API

### Authentication

- All communication goes through WebSocket on `/control.ashx` — there is no REST API

- Login via HTTP POST to `/login` returns a session cookie in `Set-Cookie` header

- **Important:** `aiohttp`'s cookie jar silently drops cookies on non-standard port combinations (e.g. plain HTTP on port 443). Read `resp.raw_headers` directly instead:

  ```python
  for name, val in resp.raw_headers:
      if name.lower() == b"set-cookie":
          cookies.append(val.decode().split(";")[0].strip())
  ```

- Login tokens (`~t:...` username format) bypass 2FA entirely and work as normal credentials

### tlsOffload

- If MeshCentral runs behind a reverse proxy (Nginx, Cloudflare Tunnel) with `tlsOffload: true`, the server accepts **plain HTTP/WS** even on port 443
- Use `http://` and `ws://` — not `https://`/`wss://` — when connecting internally
- `certUrl` in `config.json` is required for agents outside the local network to connect

### Actions

- **WOL:** Use `wakedevices` action (not `poweraction` type 4). MeshCentral finds online agents on the same network and relays the magic packet
- **Power:** `poweraction` with types: 1=sleep, 2=reboot, 3=shutdown, 5=hibernate
- **Hardware info:** `getsysinfo` returns full hardware details including Windows volumes, RAM, GPU, BIOS
- **`getsysinfo` field naming:** mostly raw WMI PascalCase pass-through (`windows.memory[].Capacity`, `windows.osinfo.NumberOfProcesses`, `windows.gpu[].CurrentHorizontalResolution`) — `windows.volumes` is the one exception with its own normalized lowercase keys (`size`, `sizeremaining`). Battery (`windows.battery[]`, added v0.5.0) is implemented assuming the same raw-WMI pattern (`EstimatedChargeRemaining`, `BatteryStatus` per `Win32_Battery`) but **not yet confirmed against a live payload from a battery-equipped device** — verify before relying on it
- **Real-time events:** `nodeconnect` events provide instant online/offline updates

### responseid field

- The `responseid` field in WebSocket payloads must not contain special characters like `//`, `@`, `$`
- Node IDs contain these characters — use a fixed string like `"ha-wol"` instead of `f"ha-wol-{node_id}"`

## Home Assistant Integration

### Coordinator

- Combine `DataUpdateCoordinator` (5-minute fallback poll) with a persistent WebSocket event listener for instant updates
- Guard `async_set_updated_data()` with `if self.data:` to prevent all devices showing offline on WS reconnect
- Start the event listener with `loop.create_task()` not `async_create_task()` to avoid HA bootstrap timeout warning

### Entities

- **Hardware sensors offline fallback (v0.5.0):** the hardware coordinator used to build a fresh `{}` on every poll, only including devices that were online *at that exact poll* — so any device offline at HA startup, or that went offline mid-session, immediately showed `unavailable` with no fallback, even though MeshCentral's own Details tab still shows the last known values. Fixed two ways: (1) the coordinator now carries forward the previous poll's data instead of dropping offline devices, and (2) hardware sensor entities use `RestoreEntity`/`extra_restore_state_data` to persist the last known `getsysinfo` payload across HA restarts too. See `sensor_hardware.py::_HwBase`
- **Entity creation must not depend on data that may not exist yet:** don't gate a sensor's *creation* (as opposed to its `native_value`/`available`) on `hw_coordinator.data` at platform-setup time — if the backing device happens to be offline during initial setup, the entity never gets created at all, not just marked unavailable. Always create the entity unconditionally and let `available` reflect missing data instead (see the disk-sensor "no sysinfo fetched yet" fallback and `BatteryLevelSensor` for the pattern)
- **device_class: SAFETY** on binary sensors shows "Unsafe"/"Safe" instead of "On"/"Off" — omit device_class for security sensors where `True` = OK
- **Unique ID prefix:** Always prefix unique IDs with `mc_` (e.g. `f"mc_{node_id}_online"`) to avoid collisions with other integrations like HASS.Agent that use the same device names

### Entity registry

- Old entities can be removed directly from `.storage/core.entity_registry` using `jq`
- Entities get `_2` suffix when two integrations register the same `entity_id` — solved by unique prefix in `unique_id`

### Lovelace

- Dashboard changes via `.storage/lovelace.dashboard_modern` require a version bump for browsers to update
- HA sections layout distributes sections automatically — `max_columns: 3` + 6 sections = 3×2 grid
- Custom cards must be registered in `.storage/lovelace_resources` (not just `configuration.yaml`)

## MeshCentral config.json

Valid options reference: <https://config.meshcentraltools.com>

Known invalid/problematic options:

- `cleanErrorLog` — **not a valid option**, remove it
- `mstsc: false` — **disables RDP access**, omit entirely (default is true)

Folder paths: MeshCentral creates extra folders next to `--datapath`. Use these to keep everything in one place:

- `--filespath` CLI flag → controls `meshcentral-files`
- `settings.autoBackup.backupPath` in config.json → controls `meshcentral-backups`
- `domains[""].sessionRecording.filepath` in config.json → controls `meshcentral-recordings`
- `meshcentral-web` **cannot** be redirected (MeshCentral limitation)
