import json
from pathlib import Path

# App Info
APP_VERSION = "3.5"
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

# Colors — now sourced from the design system in `theme.py`. These names are
# re-exported aliases kept for backwards compatibility so existing views keep
# working unchanged; new code should import semantic tokens from `theme`
# directly (theme.ACCENT, theme.SUCCESS, theme.DANGER, …). The dark-mode
# values are identical to the originals, so this is a pure indirection with
# no visual change — but it routes every view through a single, swappable
# palette (enabling the light/dark toggle later).
from theme import (  # noqa: E402, F401  (intentional re-exports; see comment above)
    BG,
    BORDER,
    ERROR,
    PRIMARY,
    SECONDARY,
    SURFACE,
    TEXT_PRIMARY,
    TEXT_SECONDARY,
    WARNING,
)

# Window
MIN_WIDTH = 1100
MIN_HEIGHT = 800

# Layout
CARD_PADDING = 20
FIELD_SPACING = 15

# Session
SESSION_TIMEOUT_MINUTES = 30
SESSION_WARNING_MINUTES = 5
# Bounded "Extend session": each extension adds this many minutes, capped at
# SESSION_MAX_EXTENSIONS per session so the absolute-limit model still holds
# (it can't be reset indefinitely by navigating/clicking).
SESSION_EXTENSION_MINUTES = 15
SESSION_MAX_EXTENSIONS = 2

# Earliest Search Duration
SEARCH_DURATION = 7

# API
# Page size for the internal list endpoints that only return one page
# (visitors, visits, archives, incidents). See PAGED_CATEGORIES.
INTERNAL_PAGE_SIZE = 99

# Used as a prefix for generated External API key names. The internal client
# appends a unique suffix (e.g. a unix timestamp) at call time, producing
# names like "vCommander - Automation API - v2.0.1 - 1714316400".
API_NAME = "vCommander - Automation API - v" + APP_VERSION + " - "

# Card Shadow — re-exported from the design system (elevation level 1).
from theme import CARD_SHADOW  # noqa: E402,F401

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

# ESS commission constants
ESS_SITE_NAME = "HQ"
ESS_CAMERA_NAME = "HQ CD62"
ESS_PANEL_NAME = "HQ Alarm Panel"
ESS_ACCESS_STATION_PRO_NAME = "HQ AF64"
ESS_ACCESS_STATION_PRO_DOOR_NAME = "HQ Door"
# Access level on the AF64 door, granted to the participants access group.
ESS_AF64_ACCESS_LEVEL_NAME = "[DO NOT TOUCH] AF64"
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

# ACSL commission constants
ACSL_SITE_NAME = "HQ"
ACSL_ACCESS_STATION_PRO_NAME = "[DO NOT TOUCH] HQ AF64"
ACSL_MFA_DOOR_SCHEDULE_NAME = "[DO NOT TOUCH] AF64 2FA"
ACSL_ACCESS_STATION_PRO_DOOR_NAME = "HQ Door"
ACSL_BUILDING_NAME = "HQ"
ACSL_FLOORS = ["G"]
ACSL_ADDRESS = (
    "406 E 3rd Ave, San Mateo, CA 94401, USA",
    37.56613979999999,
    -122.3210929,
)

# VSSL commission constants
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

# VSSE commission constants
VSS_EXAM_SITE_NAME = "Satellite Office"
VSS_EXAM_BULLET_NAME = "Bullet"
VSS_EXAM_FISHEYE_NAME = "Fisheye"
VSS_EXAM_DOME_NAME = "Dome"

# AS commission constants
AS_SITE_NAME = "HQ"
AS_DOME_NAME = "HQ CD62"
AS_CONTROLLER_NAME = "HQ Controller [DO NOT TOUCH]"
AS_PANEL_NAME = "HQ Alarm Panel"
AS_KEYPAD_NAME = "HQ Keypad"
AS_DOOR_NAME = "HQ Door"
AS_ACCESS_LEVEL_NAME = "HQ 24/7 Access"
AS_INSTRUCTOR_KEYCODE_NAME = "VCE Instructor Keycode"
AS_INSTRUCTOR_KEYCODE = "123456"
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

# Strobe on the alarm panel (ESS, AS), activated by the Default Response.
STROBE_OUTPUT_NAME = "Strobe Light"
# pinNum is 0-based: 0 is the panel's "Output 1" in Command.
STROBE_OUTPUT_PIN = 0

# USER INVITE Constants
# Name of both the Command group and the access group the Users tool
# puts participants in.
PARTICIPANTS_GROUP_NAME = "All Participants"

# Default IANA timezone for HQ-located devices. Passed to
# configure_access_controller() in the view.
HQ_TIMEZONE = "America/Los_Angeles"

# The one device field that is not a device serial number: it holds a
# license plate string, so it is exempt from the serial mask/validation.
LICENSE_PLATE_FIELD = "License Plate"

# Template field requirements per template code.
# NOTE: "AS" was previously defined twice in this dict — Python silently
# kept only the last definition. Kept the 4-device version since it
# matches the AS commission flow in commission_view.
TEMPLATE_FIELDS = {
    "ESS": {"devices": ["Dome", "Alarm Panel", "Access Station Pro"], "face_analytics": True},
    "ACSL": {"devices": ["Access Station Pro"], "face_analytics": False},
    # reset_permissions: offer the "remove existing user permissions" switch
    # (on by default), run before anything else is commissioned.
    "ACSE": {"devices": [], "face_analytics": False, "reset_permissions": True},
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
        "face_analytics": True,
    },
}


TEMPLATE_DISPLAY_NAMES = {
    "ESS": "Essentials",
    "ACSL": "Access Control Specialist - Lab",
    "ACSE": "Access Control Specialist - Exam",
    "VSSL": "Video Security Specialist - Lab",
    "VSSE": "Video Security Specialist - Exam",
    "AS": "Alarms Specialist",
}

# Decommission asset categories (scan + display order)
# Intercoms and Access Station Pros must come before Cameras so their
# serial numbers can be used to filter duplicates from the camera list
# (an Access Station Pro is surfaced by both the camera and access-
# controller endpoints). Doors come even earlier — they reference the
# Access Station Pro as their access controller.
# Access Control and Alarms sub-categories are grouped in the SELECT UI
# via CATEGORY_GROUPS below; that grouping is independent of scan order.
ASSET_CATEGORIES = [
    "Doors",
    # Devices
    "Access Station Pro",
    "Intercoms",
    "Desk Stations",
    "Sensors",
    "Cameras",
    # Camera-tied watchlist (public API), scanned/deleted alongside Cameras.
    "Persons of Interest",
    "Command Connectors",
    # Footage / investigations (Archives look-back window =
    # constants.SEARCH_DURATION days). Incidents reference footage, so they
    # precede Archives; Alerts (alert rules) are independent org-level rules.
    "Incidents",
    "Archives",
    "Alerts",
    "Guest Sites",
    "Mailroom Sites",
    # Access Control
    "Access Controllers",
    "Floors",
    "Buildings",
    "Visitor Access Templates",
    "Schedules",
    "Access Levels",
    "Access Groups",
    "Scenarios",
    # Alarms
    "Keypads",
    "Expanders",
    "Wireless Contact Sensors",
    "Wireless Panic Buttons",
    "Wireless Universal Transmitters",
    "Wired Inputs",
    "Wired Outputs",
    "Guards",
    "Partitions",
    "Alarm Panels",
    "Alarm Systems",
    "Alarm Sites",
    # Sites (camera groups) go last — everything above lives inside one.
    "Sites",
    # Users & misc — Visits reference Visitors, and both precede Command
    # Users in the deletion order.
    "Visits",
    "Visitors",
    "Command Users",
    # Security entity groups (only non-Verkada-managed are surfaced)
    "Groups",
    "Unassigned Devices",
]

# Parent groups for the SELECT UI. Each parent renders one collapsible
# tile with a checkbox that toggles all of its (non-empty) children.
# Children are listed in display order; DELETION_ORDER (below) decides the
# order they are actually deleted in.
CATEGORY_GROUPS = {
    "Access Control": [
        "Doors",
        "Access Station Pro",
        "Access Controllers",
        "Floors",
        "Buildings",
        "Visitor Access Templates",
        "Schedules",
        "Access Levels",
        "Access Groups",
        "Scenarios",
    ],
    "Alarms": [
        "Keypads",
        "Expanders",
        "Wireless Contact Sensors",
        "Wireless Panic Buttons",
        "Wireless Universal Transmitters",
        "Wired Inputs",
        "Wired Outputs",
        "Guards",
        "Partitions",
        "Alarm Panels",
        "Alarm Systems",
        "Alarm Sites",
    ],
}

# Dependency-aware deletion order — edit with care, the sequence matters.
#   - Visits first, then Visitors, then Command Users: a visit references a
#     visitor, and a visitor is an access user, so tear them down from the
#     most dependent to the least. The running user is excluded at scan time.
#   - Intercoms, Doors and Access Station Pros before Cameras: intercoms
#     and ASPs are also surfaced by the camera endpoint, so deleting them
#     via their proper endpoints first avoids the camera-side delete
#     failing on a half-gone device. Doors precede ASPs (door references
#     ASP as its access controller).
#   - Rest of Access Control: controllers → floors → buildings → visitor
#     access templates → schedules → levels → scenarios → groups. Schedules must
#     precede Access Levels (same backing endpoint, different object).
#     Scenarios (lockdowns) hold release-group references, so they must
#     be deleted BEFORE Access Groups — otherwise the server rejects
#     the group delete with "Cannot delete only release group for
#     lockdown". Visually, Scenarios still render at the end of the
#     Access Control group via CATEGORY_GROUPS.
#   - Alarms: devices before partitions before panel before system before site.
#   - Sites (camera groups) are deleted last — every other asset lives
#     inside one. If a site delete fails, the decommission tool falls
#     back to renaming it ("<name>-<mm/dd/yy>") to free the name.
#   - Unassigned Devices are informational only — no delete endpoint exists,
#     so they are intentionally absent here.
DELETION_ORDER = [
    # Visits reference Visitors reference Command Users — delete in that order.
    "Visits",
    "Visitors",
    "Command Users",
    # Security entity groups — after Command Users, before Doors.
    "Groups",
    # Persons of Interest first among the camera assets: the internal
    # people endpoints (videntity) refuse every call once the org has no
    # cameras left (403 "Insufficient permissions", even with GSA on).
    "Persons of Interest",
    # Access devices that must precede Cameras
    "Doors",
    "Access Station Pro",
    # Devices
    "Intercoms",
    "Desk Stations",
    "Sensors",
    "Cameras",
    "Command Connectors",
    # Footage / investigations — after Command Connectors, before Guest
    # Sites. Incidents reference footage, so delete them before Archives;
    # Alerts (alert rules) are independent.
    "Incidents",
    "Archives",
    "Alerts",
    "Guest Sites",
    "Mailroom Sites",
    # Rest of Access Control
    "Access Controllers",
    "Floors",
    "Buildings",
    "Visitor Access Templates",
    "Schedules",
    "Access Levels",
    # Scenarios before Access Groups: a lockdown holds a release-group
    # ref on a user group; deleting the group first 403s with
    # "Cannot delete only release group for lockdown". CATEGORY_GROUPS
    # keeps Scenarios visually at the end of the Access Control tile.
    "Scenarios",
    "Access Groups",
    # Alarms
    "Keypads",
    "Expanders",
    "Wireless Contact Sensors",
    "Wireless Panic Buttons",
    "Wireless Universal Transmitters",
    "Wired Inputs",
    "Wired Outputs",
    "Guards",
    "Partitions",
    "Alarm Panels",
    "Alarm Systems",
    "Alarm Sites",
    # Sites last of all
    "Sites",
]

# Scanned for visibility but impossible to delete (Verkada exposes no delete
# endpoint). Shown read-only in the SELECT step and never counted as
# selected, so the Confirm total always matches what is deleted.
READ_ONLY_CATEGORIES = frozenset({"Unassigned Devices"})

# Categories whose getter returns at most INTERNAL_PAGE_SIZE items per call.
# When a scan comes back full, the delete loop re-lists the category after
# each pass and keeps deleting until nothing new appears, so larger orgs are
# cleaned out completely.
PAGED_CATEGORIES = frozenset({"Visits", "Visitors", "Archives", "Incidents"})

ROLE_PROPAGATION_SECONDS = 3

# Default HTTP timeout for every internal-API request (seconds).
DEFAULT_TIMEOUT = 30

# Maps a UI category label to the VerkadaInternalAPIClient method that
# fetches/deletes that category. decommission_view uses these for dynamic
# dispatch when iterating over the user's category selection.
#
# When you add a new category, add the entry here AND implement the
# matching get_<x>() / delete_<x>() on VerkadaInternalAPIClient.
_INTERNAL_GETTERS = {
    # Devices
    "Intercoms": "get_intercom",
    "Desk Stations": "get_desk_station",
    "Sensors": "get_sensor",
    "Command Connectors": "get_connector",
    "Incidents": "get_incident",
    "Archives": "get_archive",
    "Alerts": "get_alert",
    "Mailroom Sites": "get_mailroom_site",
    "Cameras": "get_camera",
    "Persons of Interest": "get_person_of_interest",
    "Guest Sites": "get_guest_site",
    "Command Users": "get_command_users",
    # Access Control
    "Doors": "get_door",
    "Access Station Pro": "get_access_station_pro",
    "Access Controllers": "get_access_controller",
    "Floors": "get_floor",
    "Buildings": "get_building",
    "Visits": "get_visit",
    "Visitors": "get_visitor",
    "Visitor Access Templates": "get_visitor_access_template",
    "Schedules": "get_schedule",
    "Access Levels": "get_access_level",
    "Scenarios": "get_scenario",
    "Access Groups": "get_access_group",
    # Sites (camera groups)
    "Sites": "get_site",
    # Alarms (org-wide aggregators — no system/site arg)
    "Keypads": "get_alarm_keypad_all",
    "Expanders": "get_alarm_expander_all",
    "Wireless Contact Sensors": "get_wireless_contact_sensor_all",
    "Wireless Panic Buttons": "get_wireless_panic_button_all",
    "Wireless Universal Transmitters": "get_wireless_universal_transmitter_all",
    "Wired Inputs": "get_wired_input_all",
    "Wired Outputs": "get_wired_output_all",
    "Guards": "get_alarm_guard_all",
    "Partitions": "get_alarm_partition_all",
    "Alarm Panels": "get_alarm_panel_all",
    "Alarm Systems": "get_alarm_system",
    "Alarm Sites": "get_alarm_site",
    # Security entity groups
    "Groups": "get_group",
    # Misc
    "Unassigned Devices": "get_unassigned_device",
}

_INTERNAL_DELETERS = {
    # Devices
    "Intercoms": "delete_intercom",
    "Desk Stations": "delete_desk_station",
    "Sensors": "delete_sensor",
    "Cameras": "delete_camera",
    "Command Connectors": "delete_connector",
    "Incidents": "delete_incident",
    "Archives": "delete_archive",
    "Alerts": "delete_alert",
    "Guest Sites": "delete_guest_site",
    "Mailroom Sites": "delete_mailroom_site",
    # Security entity groups
    "Groups": "delete_group",
    # Access Control
    "Doors": "delete_door",
    "Access Station Pro": "delete_access_station_pro",
    "Access Controllers": "delete_access_controller",
    "Floors": "delete_floor",
    "Buildings": "delete_building",
    "Visits": "delete_visit",
    "Visitors": "delete_visitor",
    "Visitor Access Templates": "delete_visitor_access_template",
    "Schedules": "delete_schedule",
    "Access Levels": "delete_access_level",
    "Scenarios": "delete_scenario",
    "Access Groups": "delete_access_group",
    # Sites (camera groups) — _delete_one falls back to rename_site
    # ("<name>-<mm/dd/yy>") when the delete is rejected.
    "Sites": "delete_site",
    # Alarms
    "Keypads": "delete_alarm_keypad",
    "Expanders": "delete_alarm_expander",
    "Wireless Contact Sensors": "delete_wireless_contact_sensor",
    "Wireless Panic Buttons": "delete_wireless_panic_button",
    "Wireless Universal Transmitters": "delete_wireless_universal_transmitter",
    "Wired Inputs": "delete_wired_input",
    "Wired Outputs": "delete_wired_output",
    "Guards": "delete_alarm_guard",
    "Partitions": "delete_alarm_partition",
    "Alarm Panels": "delete_alarm_panel",
    "Alarm Systems": "delete_alarm_system",
    "Alarm Sites": "delete_alarm_site",
}

# Categories deleted one item at a time: alarm devices share their alarm
# system's configuration, and schedules are written back as a set. Every
# other category deletes PARALLEL_REQUESTS items at once, as the Command web
# app's bulk delete does.
SEQUENTIAL_DELETE_CATEGORIES = frozenset(
    {
        "Schedules",
        "Keypads",
        "Expanders",
        "Wireless Contact Sensors",
        "Wireless Panic Buttons",
        "Wireless Universal Transmitters",
        "Wired Inputs",
        "Wired Outputs",
        "Guards",
        "Partitions",
        "Alarm Panels",
        "Alarm Systems",
        "Alarm Sites",
    }
)

# Categories deleted many-at-once by one internal call taking a list of ids
# (as the Command web app does): category -> client method.
# Ids per batch delete call (Command users, persons of interest).
BATCH_DELETE_SIZE = 100

_BATCH_DELETERS = {
    "Command Users": "delete_users",
    "Persons of Interest": "delete_persons_of_interest",
}
