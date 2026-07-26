"""Constants for MeshCentral integration."""

DOMAIN = "meshcentral"

CONF_USE_SSL = "use_ssl"
CONF_VERIFY_SSL = "verify_ssl"
CONF_LOGIN_KEY = "login_key"

DEFAULT_PORT = 443
DEFAULT_USE_SSL = False
DEFAULT_VERIFY_SSL = False

# Options flow keys for configurable poll intervals (in minutes)
CONF_MAIN_SCAN_INTERVAL = "main_scan_interval"
CONF_HW_SCAN_INTERVAL = "hw_scan_interval"
DEFAULT_MAIN_SCAN_INTERVAL = 5  # minutes — fallback poll behind the WS push
DEFAULT_HW_SCAN_INTERVAL = 5  # minutes — getsysinfo poll for hardware sensors

# Device attributes
ATTR_NODE_ID = "node_id"
ATTR_MESH_ID = "mesh_id"
ATTR_MESH_NAME = "mesh_name"
ATTR_OS_DESC = "os_description"
ATTR_AGENT_VERSION = "agent_version"
ATTR_IP_ADDRESS = "ip_address"
ATTR_LAST_CONNECT = "last_connect"
ATTR_POWER_STATE = "power_state"

# Mapping of MeshCentral's numeric "pwr" node field to a human-readable state.
# Confirmed against meshcentral.js's powerState doc comment (next to
# SetConnectivityState): 0=Unknown, 1=S0 power on, 2=S1 Sleep, 3=S2 Sleep,
# 4=S3 Sleep, 5=S4 Hibernate, 6=S5 Soft-Off, 7=Present, 8=Off (#27 — the
# previous mapping only had 6 entries and most of them were wrong).
# 0 is intentionally omitted — it means "Unknown", same as an absent/None
# "pwr" field, so it falls through to POWER_STATE_UNKNOWN below either way.
POWER_STATE_MAP = {
    1: "on",
    2: "sleep",        # ACPI S1
    3: "sleep",        # ACPI S2 — MeshCentral's own UI also just shows "Sleep" for this
    4: "deep_sleep",   # ACPI S3
    5: "hibernate",    # ACPI S4
    6: "soft_off",     # ACPI S5
    7: "present",
    8: "off",
}
POWER_STATE_UNKNOWN = "unknown"

# Mapping of MeshCentral's numeric "conn" node field. It's a BITMASK, not an
# enum — a device can be connected via more than one channel at once (e.g.
# agent + CIRA), so callers must use bitwise AND (conn & CONN_AGENT), never
# equality (conn == CONN_AGENT). Values confirmed against meshcentral.js,
# SetConnectivityState()'s "connectType" doc comment.
CONN_AGENT = 1
CONN_CIRA = 2
CONN_AMT_LOCAL = 4
CONN_AMT_RELAY = 8
CONN_MQTT = 16

CONN_TYPE_LABELS = {
    CONN_AGENT: "agent",
    CONN_CIRA: "cira",
    CONN_AMT_LOCAL: "amt_local",
    CONN_AMT_RELAY: "amt_relay",
    CONN_MQTT: "mqtt",
}


def conn_type_list(conn: int) -> list[str]:
    """Decode a conn bitmask into a list of human-readable connection types."""
    return [label for bit, label in CONN_TYPE_LABELS.items() if conn & bit]
