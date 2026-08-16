# MeshCentral integration for Home Assistant

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://github.com/hacs/integration) [![GitHub release](https://img.shields.io/github/release/andlo/ha-meshcentral.svg)](https://github.com/andlo/ha-meshcentral/releases) [![License](https://img.shields.io/github/license/andlo/ha-meshcentral.svg)](LICENSE)

Home Assistant custom integration for [MeshCentral](https://meshcentral.com) — the open-source remote management platform.

![MeshCentral integration in Home Assistant showing 8 devices](screenshots/integration-devices.png)

## What is MeshCentral?

MeshCentral is a free, open-source remote device management platform you can self-host on your own server. It lets you remotely monitor, manage and control computers and devices — Windows, Linux, and macOS — from a single web interface. Think of it as your own private TeamViewer or AnyDesk, without subscriptions or cloud dependency.

### Why MeshCentral + Home Assistant?
Running MeshCentral alongside Home Assistant is a powerful combination for anyone who wants full control over their home network:

- **See all your devices in one place** — PC online/offline status, OS info, last boot time, and logged-in users appear as native HA entities alongside your lights, sensors, and other smart home devices.
- **Automate around your computers** — trigger automations when a PC comes online (start casting music, turn on the desk lamp), or when it goes offline (cut power to peripherals via a smart plug).
- **Power control from HA** — wake, reboot, sleep, hibernate or shut down any managed device via HA buttons or automations. Wake-on-LAN works even across subnets since MeshCentral relays the magic packet through its agents.
- **Security monitoring** — Windows Defender, firewall and antivirus status exposed as binary sensors. Get notified if real-time protection goes offline.
- **Hardware insight** — CPU, GPU, RAM, disk usage and more available as optional sensors, updated every 5 minutes.
- **Real-time push** — the integration uses MeshCentral's WebSocket API for instant online/offline updates, not slow polling.

![PC devices visible in Home Assistant dashboard](screenshots/dashboard-pc.png)

## Features

### Per device — Status sensors

| Entity | Description |
|---|---|
| `binary_sensor.<n>_online` | Agent connectivity (online/offline) — real-time |
| `sensor.<n>_os` | OS description |
| `sensor.<n>_ip_address` | Last known IP address |
| `sensor.<n>_last_boot` | Last boot time (timestamp) |
| `sensor.<n>_idle_time` | User idle time in seconds |
| `sensor.<n>_active_users` | Currently logged-in users |
| `sensor.<n>_description` | Device description from MeshCentral |
| `sensor.<n>_agent_last_seen` | When agent last contacted server |
| `sensor.<n>_power_state` | Power state: on / off / sleep / hibernate / soft_off / cycle |
| `device_tracker.<n>_tracker` | Home/not_home based on agent connectivity |

### Per device — Security (Windows only)

| Entity | Description |
|---|---|
| `binary_sensor.<n>_antivirus_ok` | Antivirus status |
| `binary_sensor.<n>_firewall_ok` | Firewall status |
| `binary_sensor.<n>_defender_real_time_protection` | Windows Defender real-time protection |

### Per device — Power control

| Entity | Description |
|---|---|
| `button.<n>_reboot` | Reboot device |
| `button.<n>_shutdown` | Shut down device |
| `button.<n>_sleep` | Sleep (Windows only) |
| `button.<n>_hibernate` | Hibernate (Windows only) |
| `button.<n>_wake_on_lan` | Wake-on-LAN via MeshCentral agents |

**Wake-on-LAN** works even without direct network access — MeshCentral automatically finds online agents on the same network and uses them to broadcast the magic packet.

### Per device — Hardware detail sensors (disabled by default)

These sensors are fetched every 5 minutes via a separate `getsysinfo` call. They are **disabled by default** — enable them individually under Settings → Devices & Services → MeshCentral → device → Entities.

**All platforms:**

| Entity | Description |
|---|---|
| `sensor.<n>_cpu` | CPU model name |
| `sensor.<n>_gpu` | GPU model name |
| `sensor.<n>_bios_version` | BIOS version (vendor + date as attributes) |
| `sensor.<n>_motherboard` | Motherboard model (vendor as attribute) |

**Windows only:**

| Entity | Description |
|---|---|
| `sensor.<n>_ram_total` | Total RAM in GB |
| `sensor.<n>_battery` | Battery charge % (charging/discharging, health %, cycle count etc. as attributes) |
| `sensor.<n>_disk_c_total` | C: drive total size in GB |
| `sensor.<n>_disk_c_free` | C: drive free space in GB |
| `sensor.<n>_disk_c_free_percent` | C: drive free space in % |
| `sensor.<n>_running_processes` | Number of running processes |
| `sensor.<n>_screen_resolution` | Current screen resolution (e.g. 1920x1080) |

Additional volumes beyond C: (D:, E:, ...) get their own set of Total/Free/Free % sensors automatically, named after the drive letter. The battery sensor is only meaningful on devices that report one (laptops) — it stays unavailable on desktops.

**Linux only:**

| Entity | Description |
|---|---|
| `sensor.<n>_disk_used` | Root filesystem used in MB |
| `sensor.<n>_disk_free` | Root filesystem free in MB |

Additional mount points beyond / (e.g. /home, /mnt/data) get their own Used/Free sensors automatically, named after the mount point.

### Server-level entities

These describe the MeshCentral server itself rather than an individual managed device, and live on a synthetic "MeshCentral Server" device.

| Entity | Description |
|---|---|
| `sensor.meshcentral_server_devices_online` | Devices currently online, across all groups |
| `sensor.meshcentral_server_devices_offline` | Devices currently offline, across all groups |
| `sensor.meshcentral_server_devices_total` | Total managed devices |
| `sensor.meshcentral_server_device_groups` | Number of device groups (meshes) |
| `sensor.meshcentral_server_user_accounts` | Number of MeshCentral user accounts |
| `sensor.meshcentral_server_installed_version` | Installed MeshCentral core version |
| `sensor.meshcentral_server_latest_available_version` | Latest MeshCentral version published on npm |
| `update.meshcentral_server_meshcentral_core` | Same installed/latest version, surfaced as a native HA update entity (Settings → Updates). Informational only — no install action, since the integration doesn't assume how your server is hosted |

**Per device group** — one aggregated sensor per mesh/device group, on its own synthetic device nested under "MeshCentral Server":

| Entity | Description |
|---|---|
| `sensor.<meshname>_devices_online` | Online device count for that group. Attributes: `total` (group size), `offline_devices` (names of offline devices in the group) |

### Services

| Service | Description |
|---|---|
| `meshcentral.run_command` | Run a shell/OS command on any online device |
| `meshcentral.run_console_command` | Send a MeshCentral built-in agent console command (e.g. `apf cira`, `info`, `help`) — not an OS shell command |

`run_command` always fires a `meshcentral_command_result` event with `device_id`, `device_name`, `command`, `success`, and `output`, and returns the same data as a service response (use `response_variable` in scripts/automations to capture it). Set `notify: true` to also create a persistent notification with the output.

`run_console_command` targets one or more devices at once (`device_id` accepts a list), sending one request per MeshCentral server involved. It requires the account to hold MeshCentral's **`agentconsole`** right on the device/mesh — without it, MeshCentral accepts the request but never replies, so the call times out with no error. It fires a `meshcentral_console_command_result` event and returns a `results` dict keyed by device, e.g. `results: {fedora: {success: true, output: "..."}}`. Send `command: "help"` first to see the list of available commands for a given device.

## Installation

### Via HACS (recommended)

1. Open HACS → Integrations → ⋮ → Custom repositories
2. Add `https://github.com/andlo/ha-meshcentral` — category: Integration
3. Install **MeshCentral** and restart Home Assistant

### Manual

Copy `custom_components/meshcentral/` into your HA `custom_components/` directory and restart.

## Lovelace card

A custom card is included in the `www/` folder. Add it as a resource and use it in your dashboards.

**Add as resource** — Settings → Dashboards → Resources → Add resource:

- URL: `/local/meshcentral-card.js`
- Type: JavaScript module

**Copy the card file to HA:**

```bash
cp www/meshcentral-card.js /config/www/
```

**Card configuration:**

```yaml
type: custom:meshcentral-card
title: My Computers
devices:
  - fedora
  - ASUS-GamerPC
  - ASRock
```

The card shows online/offline status, OS, IP, logged-in users, last boot, security badges, and hardware info (CPU, RAM, disk) for each device — if the hardware sensors are enabled.

## Configuration

Go to **Settings → Devices & Services → Add Integration → MeshCentral** and enter:

| Field | Description |
|---|---|
| Host | IP or hostname of your MeshCentral server |
| Port | Default: 443 |
| Username | MeshCentral username |
| Password | MeshCentral password |
| Login Key | Server-level LoginKey for 3FA — leave empty if not used (see below) |
| Use SSL | Enable for HTTPS/WSS (default: off) |
| Verify SSL | Disable if using self-signed cert (default: off) |

### 2FA accounts

If your account has two-factor authentication enabled, create a **Login Token** in MeshCentral → My Account → Login Tokens. Use the generated username (`~t:...`) and password as credentials in HA — this bypasses 2FA entirely.

### LoginKey (3FA) — server-level access key

Some MeshCentral servers are configured with a **LoginKey** in `config.json`. This is a server-level 3FA feature that requires all requests — including the login page itself — to include a `?key=<value>` query parameter. Without it, the server blocks access before any authentication can occur.

If your server uses this, you will see an auth failure even with correct username and password. Enter the LoginKey value in the **Login Key** field during setup.

> **LoginKey vs Login Token — these are two different things:**
>
> | | What it is | Where to find it | Used as |
> |---|---|---|---|
> | **Login Key** (3FA) | Server-level URL access key | `config.json` → run server with `--logintokenkey` | The *Login Key* field in this integration |
> | **Login Token** (2FA bypass) | Per-user temporary token | MeshCentral → My Account → Login Tokens | The *Username* field (as `~t:...`) |
>
> You may need both at the same time if your server uses LoginKey AND your account has 2FA enabled.

### TLS offload / reverse proxy

If MeshCentral runs behind a reverse proxy (Nginx, Cloudflare Tunnel) with `tlsOffload: true`, set **Use SSL = off** and point directly at the internal plain HTTP port — even if that port is 443. The server accepts plain HTTP/WS on that port while the proxy handles TLS externally.

### Poll intervals

The device list updates instantly via WebSocket push — polling is just the fallback for missed events, plus the separate hardware (`getsysinfo`) poll. Both default to 5 minutes and can be changed under **Settings → Devices & Services → MeshCentral → Configure**, without needing to remove and re-add the integration.

## How it works

The integration uses two mechanisms in parallel:

- **Real-time WebSocket push** — a persistent connection to MeshCentral's `/control.ashx` endpoint receives `nodeconnect` events the moment a device goes online or offline. Online/offline status updates are instant.
- **Polling fallback** — a full device list refresh runs every 5 minutes to ensure nothing is missed if the WebSocket drops an event.
- **Hardware data** — a separate `getsysinfo` call runs every 5 minutes for each online device to update the hardware detail sensors.

## Automation examples

```yaml
# Turn on desk lamp when PC comes online
automation:
  trigger:
    platform: state
    entity_id: binary_sensor.fedora_online
    to: "on"
  action:
    service: light.turn_on
    target:
      entity_id: light.desk_lamp

# Alert if Windows Defender is disabled
automation:
  trigger:
    platform: state
    entity_id: binary_sensor.asus_gamerpc_defender_real_time_protection
    to: "off"
  action:
    service: notify.mobile_app
    data:
      message: "⚠️ Windows Defender disabled on ASUS-GamerPC!"

# Run a command on a device and get a notification with the output
service: meshcentral.run_command
data:
  device_id: fedora
  command: "systemctl restart nginx"
  notify: true

# Or capture the result in a script/automation
- service: meshcentral.run_command
  data:
    device_id: fedora
    command: "uptime"
  response_variable: cmd_result
- service: notify.mobile_app
  data:
    message: "{{ cmd_result.output }}"

# Revive a dropped CIRA connection via a MeshCentral console command
- service: meshcentral.run_console_command
  data:
    device_id: ASUS-GamerPC
    command: "apf cira"
    notify: true
```

## Related

- [MeshCentral Add-on](https://github.com/andlo/ha-meshcentral-addon) — Run MeshCentral as a Home Assistant add-on (no separate server needed)
- [MeshCentral](https://meshcentral.com) — Official MeshCentral website
- [MeshCentral GitHub](https://github.com/Ylianst/MeshCentral) — MeshCentral source code

## License

MIT
