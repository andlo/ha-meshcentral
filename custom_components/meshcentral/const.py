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

# Options flow key for device group filtering (#47). A list of MeshCentral
# mesh IDs (not names, so renaming a group doesn't break the selection). An
# empty list (the default) means "all groups" — the pre-#47 behavior.
CONF_SELECTED_MESH_IDS = "selected_mesh_ids"

# Options flow key for per-device entity category filtering (#47, part 2).
# A list of category keys (below). An empty list (the default) means "all
# categories" - the pre-#47 behavior, so existing installs are unaffected.
CONF_ENTITY_CATEGORIES = "entity_categories"

ENTITY_CATEGORY_STATUS = "status"
ENTITY_CATEGORY_SYSTEM_INFO = "system_info"
ENTITY_CATEGORY_SECURITY = "security"
ENTITY_CATEGORY_HARDWARE = "hardware"
ENTITY_CATEGORY_POWER_CONTROL = "power_control"

# Order here is the order shown in the options-flow multi-select.
ENTITY_CATEGORIES: list[str] = [
    ENTITY_CATEGORY_STATUS,
    ENTITY_CATEGORY_SYSTEM_INFO,
    ENTITY_CATEGORY_SECURITY,
    ENTITY_CATEGORY_HARDWARE,
    ENTITY_CATEGORY_POWER_CONTROL,
]

# unique_id suffix -> category, used only to classify already-registered
# entities during options-flow cleanup (#47) - entity creation itself gates
# on the category directly in each platform; this map exists purely so
# cleanup can recognize an existing registry entry without a live entity
# object. Hardware sensors aren't listed here since their suffixes vary
# (per-drive-letter, per-mount-point); they're matched by "_hw_" below
# instead. A unique_id that matches nothing here (server/group-level
# sensors, or anything future) is never touched by the category filter.
_ENTITY_CATEGORY_SUFFIXES: dict[str, str] = {
    "_online": ENTITY_CATEGORY_STATUS,
    "_tracker": ENTITY_CATEGORY_STATUS,
    "_av": ENTITY_CATEGORY_SECURITY,
    "_fw": ENTITY_CATEGORY_SECURITY,
    "_defender": ENTITY_CATEGORY_SECURITY,
    "_os": ENTITY_CATEGORY_SYSTEM_INFO,
    "_ip": ENTITY_CATEGORY_SYSTEM_INFO,
    "_lastboot": ENTITY_CATEGORY_SYSTEM_INFO,
    "_idletime": ENTITY_CATEGORY_SYSTEM_INFO,
    "_users": ENTITY_CATEGORY_SYSTEM_INFO,
    "_desc": ENTITY_CATEGORY_SYSTEM_INFO,
    "_agct": ENTITY_CATEGORY_SYSTEM_INFO,
    "_pwr": ENTITY_CATEGORY_SYSTEM_INFO,
    "_reboot": ENTITY_CATEGORY_POWER_CONTROL,
    "_shutdown": ENTITY_CATEGORY_POWER_CONTROL,
    "_sleep": ENTITY_CATEGORY_POWER_CONTROL,
    "_hibernate": ENTITY_CATEGORY_POWER_CONTROL,
    "_wol": ENTITY_CATEGORY_POWER_CONTROL,
}


def categorize_entity_unique_id(unique_id: str) -> str | None:
    """Classify a registered entity's unique_id into an entity category.

    Returns None for anything not covered by the filter (server-level and
    group-level sensors, or an unrecognized suffix) - cleanup leaves those
    alone regardless of the current category selection.
    """
    if "_hw_" in unique_id:
        return ENTITY_CATEGORY_HARDWARE
    for suffix, category in _ENTITY_CATEGORY_SUFFIXES.items():
        if unique_id.endswith(suffix):
            return category
    return None


def is_category_enabled(options: dict, category: str) -> bool:
    """True if `category` should have entities created, given options.

    An empty/missing selection means "all categories" - the pre-#47
    default, preserved for existing installs on upgrade.
    """
    active = options.get(CONF_ENTITY_CATEGORIES) or []
    return not active or category in active

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
