import logging

from verkada_api_clients import VerkadaExternalAPIClient, VerkadaInternalAPIClient
from verkada_reporting import generate_report, print_inventory_details
from verkada_utilities import get_env_var, perform_bulk_deletion, sanitize_list

logging.basicConfig(
    level=logging.INFO,
    format="(%(asctime)s) [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


def main():
    # Load Environment Variables
    admin_email = get_env_var("ADMIN_EMAIL")
    admin_pass = get_env_var("ADMIN_PASSWORD")
    org_short_name = get_env_var("ORG_SHORT_NAME")
    shard = get_env_var("SHARD", default="prod1")
    region = get_env_var("REGION", default="api")

    # Initialize Internal Client
    logger.info("Initializing Internal Client...")
    internal_client = VerkadaInternalAPIClient(
        admin_email, admin_pass, org_short_name, shard
    )
    internal_client.login()

    # Initialize External Client
    logger.info("Initializing External Client...")
    external_api_key = internal_client.create_external_api_key()
    external_client = VerkadaExternalAPIClient(external_api_key, org_short_name, region)

    logger.info("Fetching device details...")
    # Fetch base objects
    intercoms = internal_client.get_object("intercoms")
    # Fetch and sanitize objects (dependent on previous fetches)
    # Note: sanitize_list removes items in the first arg from the second arg
    access_controllers = sanitize_list(
        intercoms, internal_client.get_object("access_controllers")
    )
    cameras = sanitize_list(intercoms, external_client.get_object("cameras"))

    # Build Inventory Dictionary
    inventory = {
        "Sensors": internal_client.get_object("sensors"),
        "Intercoms": intercoms,
        "Desk Stations": internal_client.get_object("desk_stations"),
        "Mailroom Sites": internal_client.get_object("mailroom_sites"),
        "Access Controllers": access_controllers,
        "Cameras": cameras,
        "Guest Sites": external_client.get_object("guest_sites"),
        "Users": external_client.get_users(exclude_user_id=internal_client.user_id),
        "Alarm Sites": internal_client.get_object("alarm_sites"),
        "Alarm Devices": internal_client.get_object("alarm_devices"),
        "Unassigned Devices": internal_client.get_object("unassigned_devices"),
    }

    # Generate Report
    logger.info("Generating report...")

    generate_report(org_short_name, inventory, save_to_file=True)

    # Print Details to Console
    print_inventory_details(inventory)

    # --- EXECUTE DELETION ---
    perform_bulk_deletion(internal_client, external_client, inventory)

    logger.info("Execution complete.")


if __name__ == "__main__":
    main()
