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
- **`getsysinfo` field naming:** mostly raw WMI PascalCase pass-through (`windows.memory[].Capacity`, `windows.osinfo.NumberOfProcesses`, `windows.gpu[].CurrentHorizontalResolution`) — `windows.volumes` and `battery[]` are both exceptions with their own normalized formats, not raw WMI. **`battery` lives at `hardware.battery`, a sibling of `hardware.windows`, NOT `hardware.windows.battery`** — easy mistake, cost us a whole beta cycle (#25). Confirmed live: `BatteryCharge` (%), `Health` (a *separate* state-of-health %), `Charging`/`Discharging` (plain booleans, no status-code enum), `CycleCount`, `DesignedCapacity`/`FullChargedCapacity`/`RemainingCapacity`, `EstimatedRuntime`. It's a list — only the first entry is used, multi-battery devices not yet handled
- **Real-time events:** `nodeconnect` events provide instant online/offline updates
- **`conn` is a BITMASK, not an enum (v0.5.2, #26):** confirmed in MeshCentral's own source (`meshcentral.js`, `SetConnectivityState`'s doc comment): `1 = MeshAgent, 2 = Intel AMT CIRA, 4 = Intel AMT local, 8 = Intel AMT Relay, 16 = MQTT`, and these combine (agent + CIRA = `3`). Every place in this codebase originally checked `conn == 1`, so any device connected via more than one channel at once was wrongly treated as offline. Always use bitwise AND — `conn & CONN_AGENT` for "is the agent up specifically" (needed for `getsysinfo`/`run_command`, which don't work over CIRA/AMT-only), or `conn != 0` for "is the device reachable at all" (the general "online" state). See `const.py` (`CONN_AGENT` etc., `conn_type_list()`)
- **`POWER_STATE_MAP` was wrong for 4 of 6 values (#27, fixed in v0.5.3):** confirmed against meshcentral.js's `powerStateStrings` doc comment — real mapping is `0=Unknown, 1=S0 power on, 2=S1 Sleep, 3=S2 Sleep, 4=S3 Sleep, 5=S4 Hibernate, 6=S5 Soft-Off, 7=Present, 8=Off`. Previous map only had 6 entries and got `0` (labeled "off", should be unknown), `3` ("hibernate", should be sleep), `4` ("soft_off", should be deep_sleep), and `5` ("cycle" — not a real MC state — should be hibernate) all wrong; `6`/`7`/`8` weren't mapped at all. Two different pwr codes (S1, S2) both legitimately map to "sleep" — dedupe with `dict.fromkeys()` when building `SensorEntity._attr_options` for the ENUM device class, or you get a duplicate option

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

### HACS

- **HACS store icon shows "icon not available" despite a correct local `brand/` folder (#38):** not our bug. Since HA 2026.3, custom integrations ship their own brand icon inline (`custom_components/meshcentral/brand/icon.png`), served via `/api/brands/integration/{domain}/icon.png` — and it renders fine everywhere in HA core. `home-assistant/brands` now auto-closes PRs for custom integrations and points to this mechanism, so there's no PR to submit anymore. HACS' own store/downloads panel, however, still only fetches icons from `data-v2.hacs.xyz` and hasn't added a fallback to the local proxy — tracked upstream at hacs/integration#5171 and #5223. Nothing to fix here; resolves itself once HACS ships a fix.

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
