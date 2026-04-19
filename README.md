# ha-meshcentral

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://github.com/hacs/integration)

Home Assistant custom integration for [MeshCentral](https://meshcentral.com) — the open-source remote management platform.

## Features

- **Binary sensor** per device: online/offline connectivity status
- **Sensors** per device: OS description, IP address
- **Button** per device: reboot via MeshCentral agent
- Config flow UI — set up from Settings → Integrations
- Polls every 30 seconds (configurable)

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
| Username | MeshCentral login username |
| Password | MeshCentral login password |
| Use SSL | Enable for HTTPS/WSS (default: on) |
| Verify SSL | Disable if using self-signed cert |

## Notes on TLS offload

If your MeshCentral runs behind a reverse proxy (Nginx, Cloudflare Tunnel) with `tlsOffload: true`, set **Use SSL = off** and point directly at the internal plain HTTP port (usually 80 or 443 without TLS).

## Entities created per device

| Entity | Type | Description |
|---|---|---|
| `binary_sensor.<name>_online` | Binary sensor | Agent connectivity |
| `sensor.<name>_os` | Sensor | OS description |
| `sensor.<name>_ip_address` | Sensor | Last known IP |
| `button.<name>_reboot` | Button | Send reboot command |

## Roadmap

- [ ] Power off button
- [ ] Wake-on-LAN button
- [ ] Run custom shell command service
- [ ] Real-time WebSocket event push (replace polling)
- [ ] Device tracker entity

## License

MIT
