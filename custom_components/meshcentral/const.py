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
# See: https://github.com/Ylianst/MeshCentral (nodeconnect / node "pwr" field)
POWER_STATE_MAP = {
    0: "off",
    1: "on",
    2: "sleep",
    3: "hibernate",
    4: "soft_off",
    5: "cycle",
}
POWER_STATE_UNKNOWN = "unknown"
