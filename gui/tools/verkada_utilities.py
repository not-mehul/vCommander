# Verkada Utilities
# This module provides utility functions for ProjectDecommission.
# It contains helper functions for environment variables, date/time conversion,
# list sanitization, and bulk deletion operations.
import logging
import os
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

import dotenv

# Import our app_path helper to locate .env file relative to executable
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app_path import get_env_file_path

# Initialize logger for this module
logger = logging.getLogger(__name__)


def get_env_var(key: str, default: Optional[str] = None) -> str:
    """
    Safely retrieves a required environment variable.

    This function loads environment variables from a .env file if present,
    then attempts to retrieve the specified key. If the key is not found
    and no default is provided, it raises an EnvironmentError.

    The .env file is loaded from the application's directory (where the 
    executable or script is located), not the current working directory.

    Args:
        key: The name of the environment variable to retrieve.
        default: An optional default value to return if the key is missing.

    Returns:
        The value of the environment variable as a string.

    Raises:
        EnvironmentError: If the variable is missing and no default is provided.
    """
    # Get the path to the .env file in the application directory
    env_path = get_env_file_path()
    
    # Load environment variables from .env file (if it exists)
    # We use dotenv.load_dotenv with the specific path to ensure the .env
    # file is loaded from the application directory, not the current working dir
    if os.path.exists(env_path):
        dotenv.load_dotenv(env_path)
        logger.debug(f"Loaded .env file from: {env_path}")
    else:
        logger.debug(f"No .env file found at: {env_path}")

    # Attempt to get the value from environment
    value = os.environ.get(key, default)

    # If no value found and no default provided, raise an error
    if not value:
        raise EnvironmentError(f"Missing required environment variable: {key}")

    return value


def get_datetime(date_input):
    """
    Converts a date string to UNIX timestamps for a full day range.

    This function takes a date string in MM/DD/YYYY format and returns
    the start and end UNIX timestamps for that day. The end timestamp
    is set to the very end of the day (start of next day).

    Args:
        date_input: A date string in the format "MM/DD/YYYY".

    Returns:
        A tuple containing:
            - start_unix: UNIX timestamp for the start of the day (00:00:00)
            - end_unix: UNIX timestamp for the end of the day (23:59:59)
    """
    # Parse the input string into a datetime object
    dt_start = datetime.strptime(date_input, "%m/%d/%Y")

    # Calculate the start of the next day (end of current day)
    dt_end = dt_start + timedelta(days=1)

    # Convert both datetimes to UNIX timestamps (integers)
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
    Camera or Access Controller). The function uses serial numbers as the unique
    identifier for deduplication.

    Args:
        base_list: The 'authoritative' list of devices (e.g., Intercoms).
        unsanitized_list: The list to filter (e.g., Cameras).

    Returns:
        A new list containing only items from unsanitized_list that DO NOT
        share a serial number with any item in base_list.
    """
    # Initialize the list that will hold the filtered results
    sanitized_list = []

    # Create a set of serial numbers from the base list for efficient O(1) lookup
    # Using a set makes the lookup operation much faster than iterating a list
    base_serials = {device["serial_number"] for device in base_list}

    # Iterate through each item in the unsanitized list
    for item in unsanitized_list:
        # Only keep the item if its serial number is NOT in the base list
        # This prevents duplicate processing of the same physical device
        if item["serial_number"] not in base_serials:
            sanitized_list.append(item)

    return sanitized_list


def perform_bulk_deletion(internal_client, external_client, inventory):
    """
    Executes the bulk deletion process for all items in the inventory.

    CRITICAL: This function includes a blocking user input prompt to confirm
    deletion. It is destructive and cannot be undone. The deletion follows a
    specific order to handle dependencies between different device types.

    The order matters because some devices depend on others. For example,
    users should be deleted first to prevent access during hardware removal,
    and alarm systems must be deleted before alarm sites.

    Args:
        internal_client: Instance of VerkadaInternalAPIClient for internal API calls.
        external_client: Instance of VerkadaExternalAPIClient for external API calls.
        inventory: Dictionary containing lists of devices/users to delete,
                  keyed by category name.
    """
    # Display prominent warning header to alert the user
    print("\n" + "!" * 60)
    print("WARNING: This action cannot be undone.")
    print("!" * 60 + "\n")

    # Force user confirmation before proceeding
    # This blocking input ensures the user explicitly confirms the action
    confirm = input("Delete ALL assets? (y/n): ").strip().lower()
    if confirm != "y":
        logger.info("Deletion cancelled by user.")
        return

    logger.info("Starting bulk deletion process...")

    # The order of deletion is specific to minimize dependency errors.
    # Deleting items in the wrong order can cause API errors.

    # 1. Users (External API)
    # Removing users first ensures no access during the decommissioning of hardware.
    # Users are deleted via the external API using their user ID.
    for user in inventory.get("Users", []):
        external_client.delete_user(user["id"])

    # 2. Sensors (Internal API)
    # Sensors are environmental monitoring devices (air quality, temperature, etc.)
    for sensor in inventory.get("Sensors", []):
        internal_client.delete_object("sensors", sensor["id"])

    # 3. Intercoms (Internal API)
    # Intercoms are communication devices at entry points
    for intercom in inventory.get("Intercoms", []):
        internal_client.delete_object("intercoms", intercom["id"])

    # 4. Desk Stations (Internal API)
    # Desk Stations are intercom/desk communication devices
    for desk_station in inventory.get("Desk Stations", []):
        internal_client.delete_object("desk_stations", desk_station["id"])

    # 5. Mailroom Sites (Internal API)
    # Mailroom Sites are package management sites
    for mailroom_site in inventory.get("Mailroom Sites", []):
        internal_client.delete_object("mailroom_sites", mailroom_site["id"])

    # 6. Access Controllers (Internal API)
    # Access Controllers manage door access hardware
    for ac in inventory.get("Access Controllers", []):
        internal_client.delete_object("access_controllers", ac["id"])

    # 7. Cameras (Internal API)
    # Cameras are video surveillance devices
    for camera in inventory.get("Cameras", []):
        internal_client.delete_object("cameras", camera["id"])

    # 8. Guest Sites (Internal API)
    # Guest Sites are visitor management locations
    for guest_site in inventory.get("Guest Sites", []):
        internal_client.delete_object("guest_sites", guest_site["id"])

    # 9. Alarm Devices (Internal API)
    # Alarm Devices are intrusion detection sensors and panels
    for alarm_device in inventory.get("Alarm Devices", []):
        internal_client.delete_object("alarm_devices", alarm_device["id"])

    # 10. Alarm Sites (Includes Alarm Systems)
    # Alarm sites are complex; they often contain an Alarm System which must
    # be deleted before the site itself can be removed.
    for alarm_site in inventory.get("Alarm Sites", []):
        # Delete the alarm system first if it exists
        # Alarm systems are the central monitoring units for alarm sites
        if alarm_site.get("alarm_system_id"):
            internal_client.delete_object(
                "alarm_systems", alarm_site["alarm_system_id"]
            )
        # Delete the site itself (requires both alarm site ID and regular site ID)
        internal_client.delete_object(
            "alarm_sites", [alarm_site["alarm_site_id"], alarm_site["site_id"]]
        )

    # 11. Unassigned Devices
    # These are devices that haven't been assigned to a specific location/site.
    # They cannot be deleted automatically via this script usually, so we warn the user.
    unassigned = inventory.get("Unassigned Devices", [])
    if unassigned:
        print(
            "\n*** WARNING: Unassigned Devices identified. "
            "Please ensure they are removed manually or claimed and decommissioned. ***"
        )

    logger.info("Bulk deletion process complete.")
