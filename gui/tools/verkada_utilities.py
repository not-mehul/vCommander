# Verkada Utilities
# This module provides utility functions for ProjectDecommission.
import logging
import os
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

import dotenv

logger = logging.getLogger(__name__)


def get_env_var(key: str, default: Optional[str] = None) -> str:
    """
    Safely retrieves a required environment variable.

    Args:
        key: The name of the environment variable.
        default: An optional default value to return if the key is missing.

    Returns:
        The value of the environment variable.

    Raises:
        EnvironmentError: If the variable is missing and no default is provided.
    """
    dotenv.load_dotenv()
    value = os.environ.get(key, default)
    if not value:
        raise EnvironmentError(f"Missing required environment variable: {key}")
    return value


def get_datetime(date_input):
    # Parse the string into a datetime object
    dt_start = datetime.strptime(date_input, "%m/%d/%Y")
    dt_end = dt_start + timedelta(days=1)
    start_unix = int(dt_start.timestamp())
    end_unix = int(dt_end.timestamp())
    return start_unix, end_unix


def sanitize_list(
    base_list: List[Dict[str, Any]], unsanitized_list: List[Dict[str, Any]]
) -> List[Dict[str, Any]]:
    """
    Filters a list of devices to exclude those already present in a base list.

    This is primarily used to prevent double-counting or double-deleting devices
    that appear in multiple categories (e.g., an Intercom that also lists as a
    Camera or Access Controller).

    Args:
        base_list: The 'authoritative' list of devices (e.g., Intercoms).
        unsanitized_list: The list to filter (e.g., Cameras).

    Returns:
        A new list containing only items from unsanitized_list that DO NOT
        share a serial number with any item in base_list.
    """
    sanitized_list = []
    # Create a set of serial numbers from the base list for efficient lookup
    base_serials = {device["serial_number"] for device in base_list}

    for item in unsanitized_list:
        # Only keep the item if its serial number is NOT in the base list
        if item["serial_number"] not in base_serials:
            sanitized_list.append(item)

    return sanitized_list


def perform_bulk_deletion(internal_client, external_client, inventory):
    """
    Executes the bulk deletion process for all items in the inventory.

    CRITICAL: This function includes a blocking user input prompt to confirm
    deletion. It is destructive and cannot be undone.

    Args:
        internal_client: Instance of VerkadaInternalAPIClient.
        external_client: Instance of VerkadaExternalAPIClient.
        inventory: Dictionary containing lists of devices/users to delete.
    """
    print("\n" + "!" * 60)
    print("WARNING: This action cannot be undone.")
    print("!" * 60 + "\n")

    # Force user confirmation before proceeding
    confirm = input("Delete ALL assets? (y/n): ").strip().lower()
    if confirm != "y":
        logger.info("Deletion cancelled by user.")
        return

    logger.info("Starting bulk deletion process...")

    # The order of deletion is specific to minimize dependency errors.

    # 1. Users (External API)
    # Removing users first ensures no access during the decommissioning of hardware.
    for user in inventory.get("Users", []):
        external_client.delete_user(user["id"])

    # 2. Sensors (Internal API)
    for sensor in inventory.get("Sensors", []):
        internal_client.delete_object("sensors", sensor["id"])

    # 3. Intercoms (Internal API)
    for intercom in inventory.get("Intercoms", []):
        internal_client.delete_object("intercoms", intercom["id"])

    # 4. Desk Stations (Internal API)
    for desk_station in inventory.get("Desk Stations", []):
        internal_client.delete_object("desk_stations", desk_station["id"])

    # 5. Mailroom Sites (Internal API)
    for mailroom_site in inventory.get("Mailroom Sites", []):
        internal_client.delete_object("mailroom_sites", mailroom_site["id"])

    # 6. Access Controllers (Internal API)
    for ac in inventory.get("Access Controllers", []):
        internal_client.delete_object("access_controllers", ac["id"])

    # 7. Cameras (Internal API)
    for camera in inventory.get("Cameras", []):
        internal_client.delete_object("cameras", camera["id"])

    # 8. Guest Sites (Internal API)
    for guest_site in inventory.get("Guest Sites", []):
        internal_client.delete_object("guest_sites", guest_site["id"])

    # 9. Alarm Devices (Internal API)
    for alarm_device in inventory.get("Alarm Devices", []):
        internal_client.delete_object("alarm_devices", alarm_device["id"])

    # 10. Alarm Sites (Includes Alarm Systems)
    # Alarm sites are complex; they often contain an Alarm System which must
    # be deleted before the site itself can be removed.
    for alarm_site in inventory.get("Alarm Sites", []):
        # Delete the system first if it exists
        if alarm_site.get("alarm_system_id"):
            internal_client.delete_object(
                "alarm_systems", alarm_site["alarm_system_id"]
            )
        # Delete the site itself (requires both site ID and alarm site ID)
        internal_client.delete_object(
            "alarm_sites", [alarm_site["alarm_site_id"], alarm_site["site_id"]]
        )

    # 11. Unassigned Devices
    # These cannot be deleted automatically via this script usually, so we warn the user.
    unassigned = inventory.get("Unassigned Devices", [])
    if unassigned:
        print(
            "\n*** WARNING: Unassigned Devices identified. "
            "Please ensure they are removed manually or claimed and decommissioned. ***"
        )

    logger.info("Bulk deletion process complete.")
