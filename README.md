# ha-meshcentral

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://github.com/hacs/integration)

Home Assistant custom integration for [MeshCentral](https://meshcentral.com) — the open-source remote management platform.

## Features

### Per device — Sensors
| Entity | Description |
|---|---|
| `binary_sensor.<n>_online` | Agent connectivity (online/offline) |
| `sensor.<n>_os` | OS description |
| `sensor.<n>_ip_address` | Last known IP address |
| `sensor.<n>_last_boot` | Last boot time (timestamp) |
| `sensor.<n>_idle_time` | User idle time in seconds |
| `sensor.<n>_active_users` | Currently logged-in users |
| `sensor.<n>_description` | Device description from MeshCentral |
| `sensor.<n>_agent_last_seen` | When agent last contacted server |

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

## Installation

### Via HACS (recommended)

1. Open HACS → Integrations → ⋮ → Custom repositories
2. Add `https://github.com/andlo/ha-meshcentral` — category: Integration
3. Install **MeshCentral** and restart Home Assistant

### Manual

Copy `custom_components/meshcentral/` into your HA `custom_components/` directory and restart.

## Configuration

Go to **Settings → Devices & Services → Add Integration → MeshCentral** and enter:

| Field | Description |
|---|---|
| Host | IP or hostname of your MeshCentral server |
| Port | Default: 443 |
| Username | MeshCentral username |
| Password | MeshCentral password |
| Use SSL | Enable for HTTPS/WSS (default: off) |
| Verify SSL | Disable if using self-signed cert (default: off) |

### 2FA accounts

If your account has two-factor authentication enabled, create a **Login Token** in MeshCentral → My Account → Login Tokens. Use the generated username (`~t:...`) and password as credentials in HA — this bypasses 2FA.

### TLS offload / reverse proxy

If MeshCentral runs behind a reverse proxy (Nginx, Cloudflare Tunnel) with `tlsOffload: true`, set **Use SSL = off** and point directly at the internal plain HTTP port — even if that port is 443. The server accepts plain HTTP/WS on that port while the proxy handles TLS externally.

## Polling interval

Devices are polled every 30 seconds by default.

## Roadmap

- [ ] Real-time WebSocket event push (replace polling)
- [ ] Run custom shell command service
- [ ] Device tracker entity
- [ ] Power state sensor (on/off/sleep)

## License

MIT
