import logging

from verkada_api_clients import VerkadaExternalAPIClient, VerkadaInternalAPIClient
from verkada_utilities import get_datetime, get_env_var

logging.basicConfig(
    level=logging.INFO,
    format="(%(asctime)s) [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


def main():
    legal_api_key = get_env_var("LEGAL_API_KEY")
    legal_org_short_name = get_env_var("LEGAL_ORG_SHORT_NAME")
    admin_email = get_env_var("ADMIN_EMAIL")
    admin_pass = get_env_var("ADMIN_PASSWORD")
    org_short_name = get_env_var("ORG_SHORT_NAME")
    shard = get_env_var("SHARD", default="prod1")
    region = get_env_var("REGION", default="api")

    logger.info("Initializing Internal Client...")
    internal_client = VerkadaInternalAPIClient(
        admin_email, admin_pass, org_short_name, shard
    )
    internal_client.login()  # This might trigger an interactive 2FA prompt.

    legal_client = VerkadaExternalAPIClient(legal_api_key, legal_org_short_name, region)
    sites = legal_client.get_object("guest_sites")

    print("\n--- Available Sites ---")
    for index, site in enumerate(sites):
        print(f"{index + 1}. {site['name']}")

    while True:
        try:
            selection = int(
                input("\nEnter the number of the site you want to select: ")
            )

            # 3. Validate the input (must be within the list bounds)
            if 1 <= selection <= len(sites):
                # Convert back to 0-based index to grab the object
                selected_site = sites[selection - 1]
                site_id = selected_site["id"]
                date_input = input("Enter the date (MM/DD/YYYY) to fetch visits for: ")
                start, end = get_datetime(date_input)
                visits = legal_client.get_guest_visits(site_id, start, end)
                for visit in visits:
                    internal_client.invite_user(
                        visit["first_name"], visit["last_name"], visit["email"], True
                    )
                break
            else:
                print(f"Please enter a number between 1 and {len(sites)}.")
        except ValueError:
            print("Invalid input. Please enter a number.")


main()
