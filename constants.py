import json
from pathlib import Path

import flet as ft

# App Info
APP_VERSION = "3.1"
GITHUB_REPO = "not-mehul/vCommander"

_INTERNAL_MARKER = Path(__file__).parent / "assets" / "kits.internal.csv"
IS_INTERNAL_BUILD = _INTERNAL_MARKER.exists()
BUILD_VARIANT_LABEL = "(Internal) " if IS_INTERNAL_BUILD else ""
_INVITE_DEFAULTS_FILE = Path(__file__).parent / "assets" / "users_invite.internal.json"


def load_internal_invite_defaults() -> dict | None:
    """Return baked-in API key + org short name for the internal build, or None."""
    if not _INVITE_DEFAULTS_FILE.exists():
        return None
    try:
        with _INVITE_DEFAULTS_FILE.open() as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return None


# Development flag — set True to skip real authentication and go straight to Home.
# Flip back to False before any real testing or deployment.
DEV_SKIP_LOGIN = False

# Colors - Dark Theme with Pastel Accents
BG = "#1a1a1a"
SURFACE = "#2a2a2a"
BORDER = "#3a3a3a"
PRIMARY = "#7eb8da"
SECONDARY = "#8fd4b0"
WARNING = "#f0b87e"
ERROR = "#e8827a"
TEXT_PRIMARY = "#e0e0e0"
TEXT_SECONDARY = "#a0a0a0"

# Window
MIN_WIDTH = 1100
MIN_HEIGHT = 800

# Layout
PAGE_PADDING = 30
CARD_PADDING = 20
FIELD_SPACING = 15

# Session
SESSION_TIMEOUT_MINUTES = 30
SESSION_WARNING_MINUTES = 5

# API
# Used as a prefix for generated External API key names. The internal client
# appends a unique suffix (e.g. a unix timestamp) at call time, producing
# names like "vCommander - Automation API - v2.0.1 - 1714316400".
API_NAME = "vCommander - Automation API - v" + APP_VERSION + " - "

# Card Shadow
CARD_SHADOW = ft.BoxShadow(
    spread_radius=0,
    blur_radius=12,
    color=ft.Colors.with_opacity(0.3, "#000000"),
    offset=ft.Offset(0, 4),
)

# ----------------------------------------------------------------------
# Commission constants
# ----------------------------------------------------------------------
# Address tuples are accepted as-is by:
#   - create_building     (3-tuple: label, lat, lon)
#   - create_alarm_site   (8-tuple: city, country, lat, lon, state, street1,
#                          timezone, zipcode)
#   - create_guest_site   (4-tuple: full_address, lat, lon, country_code)
#   - configure_camera / configure_connector (3-tuple: label, lat, lon)
# These calls unpack tuples into the matching NamedTuple internally.

# ESS commission constants — all fixed for the HQ reference setup
ESS_SITE_NAME = "HQ"
ESS_CAMERA_NAME = "HQ CD62"
ESS_PANEL_NAME = "HQ Alarm Panel"
ESS_BUILDING_NAME = "HQ"
ESS_FLOORS = ["G"]
ESS_ADDRESS = (
    "406 E 3rd Ave, San Mateo, CA 94401, USA",
    37.56613979999999,
    -122.3210929,
)
ESS_ALARM_ADDRESS = (
    "San Mateo",
    "US",
    37.56613979999999,
    -122.3210929,
    "CA",
    "406 East 3rd Avenue",
    "America/Los_Angeles",
    "94401",
)
ESS_GUEST_ADDRESS = (
    "406 East 3rd Avenue, San Mateo, CA, USA",
    37.56613979999999,
    -122.3210929,
    "US",
)
ESS_PARTITION_NAME = "VCE Partition"

VSS_SITE_NAME = "HQ"
VSS_BULLET_NAME = "HQ Bullet"
VSS_CONTROLLER_NAME = "HQ Controller"
VSS_CONNECTOR_NAME = "HQ Command Connector"
VSS_PTZ_NAME = "HQ PTZ"
VSS_ADDRESS = (
    "406 E 3rd Ave, San Mateo, CA 94401, USA",
    37.56613979999999,
    -122.3210929,
)
VSS_BUILDING_NAME = "HQ"
VSS_FLOORS = ["G"]
VSS_DOOR_NAME = "Garage Door"
VSS_ACCESS_GROUP_NAME = "VCE Access Group"
VSS_ACCESS_LEVEL_NAME = "VCE Access Level"

VSS_EXAM_SITE_NAME = "Satellite Office"
VSS_EXAM_BULLET_NAME = "Bullet"
VSS_EXAM_FISHEYE_NAME = "Fisheye"
VSS_EXAM_DOME_NAME = "Dome"

AS_SITE_NAME = "HQ"
AS_DOME_NAME = "HQ CD62"
AS_CONTROLLER_NAME = "HQ Controller [DO NOT TOUCH]"
AS_PANEL_NAME = "HQ Alarm Panel"
AS_KEYPAD_NAME = "HQ Keypad"
AS_DOOR_NAME = "HQ Door"
AS_ACCESS_LEVEL_NAME = "HQ 24/7 Access"

AS_BUILDING_NAME = "HQ"
AS_FLOORS = ["G"]
AS_ADDRESS = (
    "406 E 3rd Ave, San Mateo, CA 94401, USA",
    37.56613979999999,
    -122.3210929,
)
AS_ALARM_ADDRESS = (
    "San Mateo",
    "US",
    37.56613979999999,
    -122.3210929,
    "CA",
    "406 East 3rd Avenue",
    "America/Los_Angeles",
    "94401",
)

# Default IANA timezone for HQ-located devices. Passed to
# configure_access_controller() in the view.
HQ_TIMEZONE = "America/Los_Angeles"

# Template field requirements per template code.
# NOTE: "AS" was previously defined twice in this dict — Python silently
# kept only the last definition. Kept the 4-device version since it
# matches the AS commission flow in commission_view.
TEMPLATE_FIELDS = {
    "ESS": {"devices": ["Dome", "Alarm Panel"], "face_analytics": True},
    "ACS": {"devices": [], "face_analytics": False},
    "VSSL": {
        "devices": [
            "Bullet",
            "PTZ",
            "Command Connector",
            "Access Controller",
            "License Plate",
        ],
        "face_analytics": True,
    },
    "VSSE": {
        "devices": ["Dome", "Fisheye", "Bullet"],
        "face_analytics": True,
    },
    "AS": {
        "devices": ["Dome", "Access Controller", "Alarm Panel", "Keypad"],
        "face_analytics": False,
    },
}


TEMPLATE_DISPLAY_NAMES = {
    "ESS": "Essentials",
    "ACS": "Access Control Specialist",
    "VSSL": "Video Security Specialist - Lab",
    "VSSE": "Video Security Specialist - Exam",
    "AS": "Alarms Specialist",
}

# Decommission asset categories (display order)
# Intercoms must come before Cameras and Access Controllers so that
# intercom serial numbers can be used to filter duplicates from those lists.
ASSET_CATEGORIES = [
    "Intercoms",
    "Cameras",
    "Sensors",
    "Desk Stations",
    "Mailroom Sites",
    "Access Controllers",
    "Command Connectors",
    "Guest Sites",
    "Command Users",
    "Alarm Sites",
    "Alarm Devices",
    "Unassigned Devices",
]

# Dependency-aware deletion order
# Intercoms before Cameras before Access Controllers (intercom deletion must
# precede the other two to avoid dependency conflicts).
# Alarm Devices before Alarm Sites; users/sites before hardware.
# Unassigned Devices are informational only — no delete endpoint exists.
DELETION_ORDER = [
    "Command Users",
    "Sensors",
    "Desk Stations",
    "Mailroom Sites",
    "Guest Sites",
    "Alarm Devices",
    "Alarm Sites",
    "Intercoms",
    "Cameras",
    "Command Connectors",
    "Access Controllers",
]

ROLE_PROPAGATION_SECONDS = 3
BUILDING_PROVISION_SECONDS = 3

# Default HTTP timeout for every internal-API request (seconds).
DEFAULT_TIMEOUT = 30

# Maps a UI category label to the VerkadaInternalAPIClient method that
# fetches/deletes that category. decommission_view uses these for dynamic
# dispatch when iterating over the user's category selection.
#
# When you add a new category, add the entry here AND implement the
# matching get_<x>() / delete_<x>() on VerkadaInternalAPIClient.
_INTERNAL_GETTERS = {
    "Sensors": "get_sensor",
    "Intercoms": "get_intercom",
    "Desk Stations": "get_desk_station",
    "Mailroom Sites": "get_mailroom_site",
    "Command Connectors": "get_connector",
    "Access Controllers": "get_access_controller",
    "Alarm Devices": "get_alarm_device",
    "Alarm Sites": "get_alarm_site",
    "Unassigned Devices": "get_unassigned_device",
}

_INTERNAL_DELETERS = {
    "Cameras": "delete_camera",
    "Sensors": "delete_sensor",
    "Desk Stations": "delete_desk_station",
    "Mailroom Sites": "delete_mailroom_site",
    "Command Connectors": "delete_connector",
    "Access Controllers": "delete_access_controller",
    "Guest Sites": "delete_guest_site",
    "Alarm Devices": "delete_alarm_device",
    "Alarm Sites": "delete_alarm_site",
    "Intercoms": "delete_intercom",
}

_EXTERNAL_GETTERS = {
    "Cameras": "get_cameras",
    "Guest Sites": "get_guest_sites",
}

_EXTERNAL_DELETERS = {
    "Command Users": "delete_access_user",
}
