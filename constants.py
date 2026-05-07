import flet as ft

# App Info
APP_VERSION = "2.0.1"

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
# These calls unpack tuples into the matching NamedTuple internally.
#
# For configure_object, callers must wrap these tuples in a dict — e.g.
# {"address": ESS_ADDRESS} for cameras/connectors, or
# {"floor_id": ..., "timezone": ...} for controllers — because
# configure_object expects object_parameters to be a dict with named keys.

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

# Default IANA timezone for HQ-located devices. Used when constructing
# configure_object("controller", ...) parameter dicts in the view.
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
