"""Constants for MeshCentral integration."""

DOMAIN = "meshcentral"

CONF_HOST = "host"
CONF_PORT = "port"
CONF_USERNAME = "username"
CONF_PASSWORD = "password"
CONF_USE_SSL = "use_ssl"
CONF_VERIFY_SSL = "verify_ssl"

DEFAULT_PORT = 443
DEFAULT_USE_SSL = True
DEFAULT_VERIFY_SSL = True
DEFAULT_SCAN_INTERVAL = 30

# Device attributes
ATTR_NODE_ID = "node_id"
ATTR_MESH_ID = "mesh_id"
ATTR_MESH_NAME = "mesh_name"
ATTR_OS_DESC = "os_description"
ATTR_AGENT_VERSION = "agent_version"
ATTR_IP_ADDRESS = "ip_address"
ATTR_LAST_CONNECT = "last_connect"
ATTR_POWER_STATE = "power_state"
