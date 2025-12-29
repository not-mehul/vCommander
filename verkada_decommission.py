"""
Verkada Decommissioning Script
------------------------------
This is the main entry point for the ProjectDecommission tool.

Workflow:
1. Authenticates with Verkada using Admin credentials (handling 2FA if needed).
2. Generates a temporary API key to access public API endpoints.
3. Scans the organization for all assets (Cameras, Access Controllers, Users, etc.).
4. Generates a comprehensive inventory report (saved to disk and console).
5. Prompts the user for confirmation before performing a bulk deletion of all assets.

Usage:
    Ensure required environment variables are set (ADMIN_EMAIL, ADMIN_PASSWORD, ORG_SHORT_NAME).
    Run the script: python verkada_decommission.py
"""

import logging

from verkada_api_clients import VerkadaExternalAPIClient, VerkadaInternalAPIClient
from verkada_reporting import generate_report, print_inventory_details
from verkada_utilities import get_env_var, perform_bulk_deletion, sanitize_list

# Configure global logging
# We use a timestamped format to make tracing the execution flow easier in logs.
logging.basicConfig(
    level=logging.INFO,
    format="(%(asctime)s) [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


def main():
    """
    Main execution flow.
    """
    # -------------------------------------------------------------------------
    # 1. Configuration Loading
    # -------------------------------------------------------------------------
    # Retrieve credentials and config from environment variables.
    # This prevents hardcoding sensitive secrets in the source code.
    admin_email = get_env_var("ADMIN_EMAIL")
    admin_pass = get_env_var("ADMIN_PASSWORD")
    org_short_name = get_env_var("ORG_SHORT_NAME")
    # 'shard' and 'region' usually default to 'prod1' and 'api' unless overridden.
    shard = get_env_var("SHARD", default="prod1")
    region = get_env_var("REGION", default="api")

    # -------------------------------------------------------------------------
    # 2. Internal Client Initialization
    # -------------------------------------------------------------------------
    logger.info("Initializing Internal Client...")
    # The Internal Client mimics a browser login. It is required to:
    # a) Perform actions not available in the public API (like deleting sites).
    # b) Generate the API key needed for the External Client.
    internal_client = VerkadaInternalAPIClient(
        admin_email, admin_pass, org_short_name, shard
    )
    internal_client.login()  # This might trigger an interactive 2FA prompt.

    # -------------------------------------------------------------------------
    # 3. External Client Initialization
    # -------------------------------------------------------------------------
    logger.info("Initializing External Client...")
    # We dynamically create a granular API key valid for 1 hour.
    # This avoids the need to manage permanent API keys in the Verkada dashboard.
    external_api_key = internal_client.create_external_api_key()
    external_client = VerkadaExternalAPIClient(external_api_key, org_short_name, region)

    # -------------------------------------------------------------------------
    # 4. Asset Discovery
    # -------------------------------------------------------------------------
    logger.info("Fetching device details...")

    # Priority Fetch: Intercoms
    # Intercoms often contain embedded cameras or controllers. We fetch them first
    # so we can filter those embedded devices out of the main lists to avoid
    # double-counting or double-deletion attempts.
    intercoms = internal_client.get_object("intercoms")

    # Fetch dependent objects
    # sanitize_list(base, target) removes items in 'base' from 'target'.

    # Remove Access Controllers that are actually part of Intercoms
    access_controllers = sanitize_list(
        intercoms, internal_client.get_object("access_controllers")
    )

    # Remove Cameras that are actually part of Intercoms
    cameras = sanitize_list(intercoms, external_client.get_object("cameras"))

    # Build the Master Inventory Dictionary
    # This aggregates all fetch operations into a single structure for reporting and deletion.
    inventory = {
        "Sensors": internal_client.get_object("sensors"),
        "Intercoms": intercoms,
        "Desk Stations": internal_client.get_object("desk_stations"),
        "Mailroom Sites": internal_client.get_object("mailroom_sites"),
        "Access Controllers": access_controllers,
        "Cameras": cameras,
        "Guest Sites": external_client.get_object("guest_sites"),
        # We exclude the current admin user to prevent locking ourselves out mid-script.
        "Users": external_client.get_users(exclude_user_id=internal_client.user_id),
        "Alarm Sites": internal_client.get_object("alarm_sites"),
        "Alarm Devices": internal_client.get_object("alarm_devices"),
        "Unassigned Devices": internal_client.get_object("unassigned_devices"),
    }

    # -------------------------------------------------------------------------
    # 5. Reporting
    # -------------------------------------------------------------------------
    logger.info("Generating report...")

    # Generates a pretty ASCII table and saves it to a .txt file
    generate_report(org_short_name, inventory, save_to_file=True)

    # Also print raw details to console for debugging/verification
    print_inventory_details(inventory)

    # -------------------------------------------------------------------------
    # 6. Execution
    # -------------------------------------------------------------------------
    # Pass the clients and the inventory to the bulk deletion handler.
    # This function contains the final "Are you sure?" safety prompt.
    perform_bulk_deletion(internal_client, external_client, inventory)

    logger.info("Execution complete.")


if __name__ == "__main__":
    main()
