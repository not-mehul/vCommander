# Verkada Utilities
# This module provides utility functions for ProjectDecommission.
import logging
import os
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


def get_env_var(key: str, default: Optional[str] = None) -> str:
    """Safely gets a required environment variable with optional default."""
    value = os.environ.get(key, default)
    if not value:
        raise EnvironmentError(f"Missing required environment variable: {key}")
    return value


def sanitize_list(
    base_list: List[Dict[str, Any]], unsanitized_list: List[Dict[str, Any]]
) -> List[Dict[str, Any]]:
    """Sanitizes the camera list by removing any cameras that are not associated with an intercom."""
    sanitized_list = []
    for item in unsanitized_list:
        if item["serial_number"] not in [
            device["serial_number"] for device in base_list
        ]:
            sanitized_list.append(item)
    return sanitized_list


def perform_bulk_deletion(internal_client, external_client, inventory):
    """
    Prompts user for confirmation and then deletes all devices in the inventory.
    """
    print("\n" + "!" * 60)
    print("WARNING: This action cannot be undone.")
    print("!" * 60 + "\n")

    confirm = input("Delete ALL assets? (y/n): ").strip().lower()
    if confirm != "y":
        logger.info("Deletion cancelled by user.")
        return

    logger.info("Starting bulk deletion process...")

    # 1. Users
    for user in inventory.get("Users", []):
        external_client.delete_user(user["id"])

    # 2. Sensors
    for sensor in inventory.get("Sensors", []):
        internal_client.delete_object("sensors", sensor["id"])

    # 3. Intercoms
    for intercom in inventory.get("Intercoms", []):
        internal_client.delete_object("intercoms", intercom["id"])

    # 4. Desk Stations
    for desk_station in inventory.get("Desk Stations", []):
        internal_client.delete_object("desk_stations", desk_station["id"])

    # 5. Mailroom Sites
    for mailroom_site in inventory.get("Mailroom Sites", []):
        internal_client.delete_object("mailroom_sites", mailroom_site["id"])

    # 6. Access Controllers
    for ac in inventory.get("Access Controllers", []):
        internal_client.delete_object("access_controllers", ac["id"])

    # 7. Cameras
    for camera in inventory.get("Cameras", []):
        internal_client.delete_object("cameras", camera["id"])

    # 8. Guest Sites
    for guest_site in inventory.get("Guest Sites", []):
        internal_client.delete_object("guest_sites", guest_site["id"])

    # 9. Alarm Devices
    for alarm_device in inventory.get("Alarm Devices", []):
        internal_client.delete_object("alarm_devices", alarm_device["id"])

    # 10. Alarm Sites (Includes Alarm Systems)
    for alarm_site in inventory.get("Alarm Sites", []):
        # Delete the system first if it exists
        if alarm_site.get("alarm_system_id"):
            internal_client.delete_object(
                "alarm_systems", alarm_site["alarm_system_id"]
            )
        # Delete the site itself
        internal_client.delete_object(
            "alarm_sites", [alarm_site["alarm_site_id"], alarm_site["site_id"]]
        )

    # 11. Unassigned Devices
    unassigned = inventory.get("Unassigned Devices", [])
    if unassigned:
        print(
            "\n*** WARNING: Unassigned Devices identified. "
            "Please ensure they are removed manually or claimed and decommissioned. ***"
        )

    logger.info("Bulk deletion process complete.")
