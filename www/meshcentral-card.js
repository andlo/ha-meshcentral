class MeshCentralCard extends HTMLElement {
  set hass(hass) {
    this._hass = hass;
    this._render();
  }

  setConfig(config) {
    if (!config.devices) throw new Error("Please define devices");
    this._config = config;
  }

  _render() {
    if (!this._hass || !this._config) return;
    const hass = this._hass;
    const devices = this._config.devices;
    const title = this._config.title || "MeshCentral";

    const rows = devices.map(name => {
      const slug = name.toLowerCase().replace(/[^a-z0-9]/g, "_");
      const online = hass.states[`binary_sensor.${slug}_online`];
      const os = hass.states[`sensor.${slug}_os`];
      const ip = hass.states[`sensor.${slug}_ip_address`];
      const users = hass.states[`sensor.${slug}_active_users`];
      const lastBoot = hass.states[`sensor.${slug}_last_boot`];
      const av = hass.states[`binary_sensor.${slug}_antivirus_ok`];
      const fw = hass.states[`binary_sensor.${slug}_firewall_ok`];
      const defender = hass.states[`binary_sensor.${slug}_defender_real_time_protection`];
      const cpu = hass.states[`sensor.${slug}_cpu`];
      const ram = hass.states[`sensor.${slug}_ram_total`];
      const diskFree = hass.states[`sensor.${slug}_disk_c_free_2`] || hass.states[`sensor.${slug}_disk_c_free`];

      const isOnline = online?.state === "on";
      const statusColor = isOnline ? "var(--success-color, #4caf50)" : "var(--error-color, #f44336)";
      const statusIcon = isOnline ? "mdi:check-circle" : "mdi:circle-off-outline";

      const securityBadges = [
        av ? `<span title="Antivirus" style="color:${av.state==='on'?'#4caf50':'#f44336'}">🛡</span>` : "",
        fw ? `<span title="Firewall" style="color:${fw.state==='on'?'#4caf50':'#f44336'}">🔥</span>` : "",
        defender ? `<span title="Defender" style="color:${defender.state==='on'?'#4caf50':'#f44336'}">🪟</span>` : "",
      ].filter(Boolean).join(" ");

      const bootTime = lastBoot?.state && lastBoot.state !== "unavailable"
        ? new Date(lastBoot.state).toLocaleDateString("da-DK", {day:"2-digit",month:"short"})
        : "";

      return `
        <div class="device-row" style="border-left: 3px solid ${statusColor}">
          <div class="device-header">
            <span class="device-name">${name}</span>
            <span class="device-status" style="color:${statusColor}">${isOnline ? "Online" : "Offline"}</span>
          </div>
          ${isOnline ? `
          <div class="device-details">
            ${os?.state && os.state!=="unavailable" ? `<span class="detail">💻 ${os.state.replace("Microsoft Windows ","Win ")}</span>` : ""}
            ${ip?.state && ip.state!=="unavailable" ? `<span class="detail">🌐 ${ip.state}</span>` : ""}
            ${users?.state && users.state!=="None" && users.state!=="unavailable" ? `<span class="detail">👤 ${users.state}</span>` : ""}
            ${bootTime ? `<span class="detail">🔄 ${bootTime}</span>` : ""}
          </div>
          ${cpu?.state && cpu.state!=="unavailable" ? `<div class="hw-row">🖥 ${cpu.state}${ram?.state && ram.state!=="unavailable" ? ` · ${ram.state} GB RAM` : ""}${diskFree?.state && diskFree.state!=="unavailable" ? ` · ${diskFree.state} GB ledig` : ""}</div>` : ""}
          ${securityBadges ? `<div class="security-row">${securityBadges}</div>` : ""}
          ` : ""}
        </div>`;
    }).join("");

    this.innerHTML = `
      <ha-card header="${title}">
        <style>
          .card-content { padding: 0 16px 16px; }
          .device-row { margin: 8px 0; padding: 10px 12px; border-radius: 6px; background: var(--secondary-background-color); border-left-width: 3px; border-left-style: solid; }
          .device-header { display: flex; justify-content: space-between; align-items: center; }
          .device-name { font-weight: 600; font-size: 1em; }
          .device-status { font-size: 0.85em; font-weight: 500; }
          .device-details { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 6px; }
          .detail { font-size: 0.8em; color: var(--secondary-text-color); }
          .hw-row { font-size: 0.78em; color: var(--secondary-text-color); margin-top: 4px; }
          .security-row { margin-top: 4px; font-size: 1em; }
        </style>
        <div class="card-content">${rows}</div>
      </ha-card>`;
  }

  getCardSize() {
    return (this._config?.devices?.length || 1) + 1;
  }

  static getConfigElement() {
    return document.createElement("meshcentral-card-editor");
  }

  static getStubConfig() {
    return { title: "MeshCentral Devices", devices: ["fedora", "ASUS-GamerPC"] };
  }
}

customElements.define("meshcentral-card", MeshCentralCard);
window.customCards = window.customCards || [];
window.customCards.push({
  type: "meshcentral-card",
  name: "MeshCentral Card",
  description: "Shows status, users, security and hardware for MeshCentral devices",
});
