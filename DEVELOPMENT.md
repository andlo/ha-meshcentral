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
