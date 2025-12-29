import logging
import os
import sys
from datetime import datetime, timedelta
from typing import Any, Callable, Dict, List, Optional, Union

import requests
from requests.adapters import HTTPAdapter
from requests.exceptions import HTTPError, JSONDecodeError
from requests.models import Response
from urllib3.util.retry import Retry

logging.basicConfig(
    level=logging.INFO,
    format="(%(asctime)s) [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


class VerkadaInternalAPIClient:
    """
    A client to interact with the internal Verkada Provisioning and Response APIs.
    """

    BASE_URL_PROVISION = "https://vprovision.command.verkada.com/__v/"
    BASE_URL_RESPONSE = "https://vproresponse.command.verkada.com/__v/"
    BASE_URL_SENSOR = "https://vsensor.command.verkada.com/__v/"
    BASE_URL_INTERCOM = "https://api.command.verkada.com/__v/"
    BASE_URL_MAILROOM = "https://vdoorman.command.verkada.com/__v/"

    def __init__(self, email: str, password: str, org_short_name: str, shard: str):
        self.email = email
        self.password = password
        self.org_short_name = org_short_name
        self.shard = shard

        # Initialize session
        self.session = requests.Session()

        # Storage for auth tokens
        self.auth_data: Optional[Dict[str, str]] = None

    @property
    def org_id(self) -> Optional[str]:
        """
        Returns the Organization ID as a string if authenticated.
        """
        if self.auth_data:
            return self.auth_data.get("organizationId")
        return None

    def _get_headers(self) -> Dict[str, str]:
        """Constructs headers required for internal API calls."""
        if not self.auth_data:
            return {}

        return {
            "Accept": "*/*",
            "Cookie": self.auth_data.get("cookie", ""),
            "x-verkada-organization-id": self.auth_data.get("organizationId", ""),
            "x-verkada-token": self.auth_data.get("csrfToken", ""),
            "x-verkada-user-id": self.auth_data.get("adminUserId", ""),
            "origin": f"https://{self.org_short_name}.command.verkada.com",
            "referer": f"https://{self.org_short_name}.command.verkada.com/",
        }

    def _parse_login_response(self, json_data: Dict[str, Any]) -> Dict[str, str]:
        """Extracts session data from a successful login response."""
        try:
            csrf_token = str(json_data["csrfToken"])
            user_token = str(json_data["userToken"])
            organization_id = str(json_data["organizationId"])
            admin_user_id = str(json_data["userId"])

            # Manually constructing the cookie string required for internal APIs
            cookie = (
                f"auth={user_token}; "
                f"org={organization_id}; "
                f"usr={admin_user_id}; "
                f"token={csrf_token};"
            )

            logger.debug(
                f"Logged in successfully. orgID: {organization_id}, UserID: {admin_user_id}"
            )

            return {
                "csrfToken": csrf_token,
                "organizationId": organization_id,
                "adminUserId": admin_user_id,
                "cookie": cookie,
            }
        except KeyError as e:
            raise ValueError(f"Failed to parse login response, missing key: {e}")

    def login(self) -> None:
        """
        Login to the Verkada Provisioning API. Handles standard login and MFA.
        Sets self.auth_data upon success.
        """
        login_url = f"{self.BASE_URL_PROVISION}{self.org_short_name}/user/login"

        payload = {
            "email": self.email,
            "org_short_name": self.org_short_name,
            "termsAcked": True,
            "password": self.password,
            "shard": self.shard,
            "subdomain": True,
        }

        logger.info(f"Logging in as {self.email}...")
        response = Response

        try:
            response = self.session.post(login_url, json=payload)
            # We don't raise_for_status immediately because 400 is used for MFA challenges

            data = response.json()
        except JSONDecodeError:
            logger.error(
                f"Login failed: API returned non-JSON response. {response.text}"
            )
            raise

        # 1. Success Scenario (No MFA)
        if response.status_code == 200 and data.get("loggedIn"):
            logger.info("Successfully logged in (No MFA required).")
            self.auth_data = self._parse_login_response(data)
            return

        # 2. MFA Required Scenario
        if response.status_code == 400:
            msg = data.get("message", "") or response.text

            if "mfa_required_for_org_admin" in msg or "2FA invalid" in msg:
                logger.info(f"2FA is required for {self.email}")

                sms_contact = data.get("data", {}).get("smsSent")
                if sms_contact:
                    logger.info(f"SMS sent to device ending in {sms_contact}")

                # Handle MFA Input
                self._handle_mfa(login_url, payload)
                return

        # 3. Failure Scenario
        raise ConnectionError(
            f"Login failed with status {response.status_code}: {response.text}"
        )

    def _handle_mfa(self, login_url: str, base_payload: Dict[str, Any]) -> None:
        """Internal method to handle the interactive MFA flow."""
        try:
            two_fa_code = input("Enter 2FA code: ").strip()
            if not two_fa_code or len(two_fa_code) < 6:
                raise ValueError("Invalid 2FA code format.")

            # Add OTP to the existing payload
            mfa_payload = base_payload.copy()
            mfa_payload["otp"] = two_fa_code

            response = self.session.post(login_url, json=mfa_payload)

            if response.status_code == 200:
                logger.info("Successfully completed 2FA.")
                self.auth_data = self._parse_login_response(response.json())
            else:
                raise ConnectionError(f"Failed to complete 2FA: {response.text}")

        except (EOFError, KeyboardInterrupt):
            raise InterruptedError("User canceled 2FA prompt.")

    def create_external_api_key(self) -> str:
        if not self.auth_data:
            raise PermissionError("Not authenticated. Please call login() first.")
        url = f"https://apiadmin.command.verkada.com/__v/{self.org_short_name}/admin/orgs/{self.org_id}/v2/granular_apikeys"
        payload = {
            "api_key_name": "Decommissioning API Key - " + str(datetime.now()),
            "expires_at": int((datetime.now() + timedelta(hours=1)).timestamp()),
            "roles": [
                "PUBLIC_API_CAMERA_READ_WRITE",
                "PUBLIC_API_SENSORS_READ_WRITE",
                "PUBLIC_API_ACCESS_READ_WRITE",
                "PUBLIC_API_ALARMS_READ_WRITE",
                "PUBLIC_API_CORE_READ_WRITE",
                "PUBLIC_API_WORKPLACE_READ_WRITE",
                "PUBLIC_API_INTERCOM_READ_WRITE",
            ],
            # YTQyOGFhNGMtOGE5MS00Zjc1LWFhZTgtNjM4MTFkMDA2MzQ1fDg0MTdiNDBjLTYzOTAtNGNlOC1hYzJjLTc3MzRhYjBjZmQ1YQ==
        }
        headers = self._get_headers()
        try:
            response = self.session.post(url, json=payload, headers=headers)
            response.raise_for_status()  # Raise error for 4xx/5xx
            data = response.json()
            api_key = data.get("apiKey")
            logger.info(f"Generated API key: {api_key}")
            return api_key
        except (HTTPError, JSONDecodeError) as e:
            logger.error(f"Failed to generate API key: {e}")
            return ""

    def get_alarm_sites(self) -> List[Dict[str, Any]]:
        """Fetches the list of alarm sites for the organization."""
        if not self.auth_data:
            raise PermissionError("Not authenticated. Please call login() first.")

        url = f"{self.BASE_URL_RESPONSE}{self.org_short_name}/response/site/list"
        payload = {"includeResponseConfigs": True}
        headers = self._get_headers()

        logger.debug("Getting Alarm Sites...")

        try:
            response = self.session.post(url, json=payload, headers=headers)
            response.raise_for_status()  # Raise error for 4xx/5xx

            data = response.json()
            raw_sites = data.get("responseSites", [])

            # Clean up the data
            alarm_sites = [
                {
                    "id": [site.get("id"), site.get("siteId")],
                    "businessName": site.get("businessName"),
                }
                for site in raw_sites
            ]

            logger.info(f"Found {len(alarm_sites)} alarm sites.")
            return alarm_sites

        except (HTTPError, JSONDecodeError) as e:
            logger.error(f"Failed to fetch alarm sites: {e}")
            return []

    def get_sensors(self) -> List[Dict[str, Any]]:
        """
        Fetches a list of sensors using the generic fetcher pattern.

        Returns:
            List[Dict[str, Any]]: A list of sensor data.
        """
        if not self.auth_data:
            raise PermissionError("Not authenticated. Please call login() first.")

        url = f"{self.BASE_URL_SENSOR}{self.org_short_name}/devices/list"

        payload = {"organizationId": self.org_id}
        headers = self._get_headers()

        try:
            response = self.session.post(url, json=payload, headers=headers)
            response.raise_for_status()
            data = response.json()
            raw_sensors = data.get("sensorDevice", [])
            sensors = [
                {
                    "id": sensor.get("deviceId"),
                    "name": sensor.get("name"),
                }
                for sensor in raw_sensors
            ]
            logger.info(f"Found {len(sensors)} sensors.")
            return sensors
        except (HTTPError, JSONDecodeError) as e:
            logger.error(f"Failed to fetch sensors: {e}")
            return []

    def get_mailroom_sites(self) -> List[Dict[str, Any]]:
        """Fetches a list of mailroom sites."""
        if not self.auth_data:
            raise PermissionError("Not authenticated. Please call login() first.")
        url = f"{self.BASE_URL_MAILROOM}{self.org_short_name}/package_site/org/{self.org_id}"
        headers = self._get_headers()

        try:
            response = self.session.get(url, headers=headers)
            response.raise_for_status()
            data = response.json()
            raw_mailroom_sites = data.get("package_sites", [])
            mailroom_sites = [
                {
                    "id": mailroom_site.get("siteId"),
                    "name": mailroom_site.get("siteName"),
                }
                for mailroom_site in raw_mailroom_sites
            ]
            logger.info(f"Found {len(mailroom_sites)} mailroom sites.")
            return mailroom_sites
        except (HTTPError, JSONDecodeError) as e:
            logger.error(f"Failed to fetch mailroom sites: {e}")
            return []

    def get_desk_stations(self) -> List[Dict[str, Any]]:
        """Fetches a list of desk stations."""
        if not self.auth_data:
            raise PermissionError("Not authenticated. Please call login() first.")

        url = f"{self.BASE_URL_INTERCOM}{self.org_short_name}/vinter/v1/user/organization/{self.org_id}/device"
        headers = self._get_headers()

        try:
            response = self.session.get(url, headers=headers)
            response.raise_for_status()
            data = response.json()
            raw_desk_stations = data.get("deskApps", [])
            desk_stations = [
                {
                    "id": desk_station.get("deviceId"),
                    "name": desk_station.get("name"),
                }
                for desk_station in raw_desk_stations
            ]
            logger.info(f"Found {len(desk_stations)} desk stations.")
            return desk_stations
        except (HTTPError, JSONDecodeError) as e:
            logger.error(f"Failed to fetch desk stations: {e}")
            return []

    def get_intercoms(self) -> List[Dict[str, Any]]:
        """Fetches a list of intercoms."""
        if not self.auth_data:
            raise PermissionError("Not authenticated. Please call login() first.")

        url = f"{self.BASE_URL_INTERCOM}{self.org_short_name}/vinter/v1/user/organization/{self.org_id}/device"
        headers = self._get_headers()

        try:
            # FIX: Using GET instead of POST. The curl command had no data payload, implying GET.
            response = self.session.get(url, headers=headers)
            response.raise_for_status()
            data = response.json()
            raw_intercoms = data.get("intercoms", [])
            intercoms = [
                {
                    "id": intercom.get("deviceId"),
                    "name": intercom.get("name"),
                }
                for intercom in raw_intercoms
            ]
            logger.info(f"Found {len(intercoms)} intercoms.")
            return intercoms
        except (HTTPError, JSONDecodeError) as e:
            logger.error(f"Failed to fetch intercoms: {e}")
            return []

    def remove_object(self, object_type: str, object_id: Union[str, List[str]]) -> bool:
        """Removes an object from the system."""
        match object_type:
            case "sensor":
                subdomain = "vsensor"
                path = "devices/decommission"
                method = "POST"
                payload = {"deviceId": object_id, "sharding": True}
            case "intercom":
                subdomain = "api"
                path = f"vinter/v1/user/async/organization/{self.org_id}/device/{object_id}?sharding=true"
                method = "DELETE"
                payload = {}
            case "camera":
                subdomain = "vprovision"
                path = "camera/decommission"
                method = "POST"
                payload = {"cameraId": object_id}
            case "access_controller":
                subdomain = "vcerberus"
                path = "access_device/decommission"
                method = "POST"
                payload = {"deviceId": object_id, "sharding": True}
            case "mailroom_site":
                subdomain = "vdoorman"
                path = f"package_site/org/{self.org_id}?siteId={object_id}"
                method = "DELETE"
                payload = {}
            case "alarm_site":
                subdomain = "vproresponse"
                path = "response/site/delete"
                method = "POST"
                payload = {"responseSiteId": object_id[0], "siteId": object_id[1]}
            case "guest_site":
                subdomain = "vdoorman"
                path = f"site/org/{self.org_id}?siteId={object_id}"
                method = "DELETE"
                payload = {}
            case "desk_station":
                subdomain = "api"
                path = f"vinter/v1/user/async/organization/{self.org_id}/device/{object_id}"
                method = "DELETE"
                payload = {"sharding": True}

            case _:
                raise ValueError(f"Unknown device type: {object_type}")
        url = (
            f"https://{subdomain}.command.verkada.com/__v/{self.org_short_name}/{path}"
        )
        headers = self._get_headers()
        res = Response
        logger.debug(f"Removing {object_type} - {object_id}...")
        try:
            if method == "POST":
                res = self.session.post(url, json=payload, headers=headers)
            elif method == "DELETE":
                res = self.session.delete(url, headers=headers)

            if res.status_code in [200, 204]:
                logger.info(f"Successfully removed {object_type} - {object_id}.")
                return True
            else:
                logger.error(f"Failed to remove {object_type} - {object_id}.")
                logger.debug(f"Response: {res.text}")
                return False
        except Exception as e:
            logger.error(f"Exception removing {object_type}: {e}")
            return False

    def logout(self) -> None:
        """Logs out the current session."""
        url = f"{self.BASE_URL_PROVISION}{self.org_short_name}/user/logout"
        payload = {
            "logoutCurrentEmailOnly": False,
            "orgShortName": self.org_short_name,
        }

        logger.info(f"Logging out {self.email}...")
        try:
            response = self.session.post(url, json=payload)
            if response.status_code == 200:
                logger.info("Logout successful.")
            else:
                logger.warning(
                    f"Logout returned unexpected status: {response.status_code}"
                )
        except Exception as e:
            logger.error(f"Error during logout: {e}")
        finally:
            self.session.close()


class VerkadaExternalAPIClient:
    """
    A client to interact with the PUBLIC (External) Verkada API endpoints.
    Documentation: https://apidocs.verkada.com/
    """

    def __init__(self, api_key: str, org_short_name: str, region: str = "api"):
        self.api_key = api_key
        self.org_short_name = org_short_name
        self.region = region

        # Initialize session FIRST so it can be used by _generate_api_token
        self.session = requests.Session()

        retries = Retry(
            total=4,
            backoff_factor=0.5,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods={"POST", "GET", "DELETE"},
        )
        adapter = HTTPAdapter(max_retries=retries)
        self.session.mount("https://", adapter)
        self.session.mount("http://", adapter)

        # Generate the token immediately upon initialization
        self.api_token = self._generate_api_token()

    def _generate_api_token(self) -> str:
        """
        Exchanges the long-lived API Key for a short-lived API Token.
        """
        url = f"https://{self.region}.verkada.com/token"
        headers = {"accept": "application/json", "x-api-key": self.api_key}

        logger.debug("Attempting to generate External API Token...")

        try:
            response = self.session.post(url, headers=headers)
            response.raise_for_status()

            data = response.json()
            token = data.get("token")

            if not token:
                raise ValueError("External token response missing 'token' key")

            logger.info(f"API Token successfully generated: {token}")
            return token

        except HTTPError as e:
            logger.error(f"Failed to generate token: {e.response.text}")
            raise
        except Exception as e:
            logger.error(f"Error during token generation: {e}")
            raise

    def _fetch_objects_generic(
        self,
        url: str,
        list_key: str,
        error_signature: str,
        mapping_func: Callable[[Dict], Dict],
    ) -> List[Dict[str, Any]]:
        """
        Generic fetcher for Cameras and Controllers to reduce code duplication.
        Handles specific Verkada API edge cases (like 400 for empty lists).
        """
        headers = {"accept": "application/json", "x-verkada-auth": self.api_token}
        # Note: Pagination logic is omitted as per request, just setting page_size
        params = {"page_size": 200}

        logger.debug(f"Fetching data from {url}...")
        res = self.session.get(url, headers=headers, params=params)

        # --- HANDLE 0 DEVICES EDGE CASE ---
        # Verkada sometimes returns 400 if the list is empty (e.g. "must include cameras")
        if res.status_code == 400:
            if error_signature in res.text:
                logger.info(f"Found 0 {list_key}.")
                return []
        # ----------------------------------

        try:
            res.raise_for_status()
            json_data = res.json()

            if list_key not in json_data or not isinstance(json_data[list_key], list):
                # If the key is missing but the call succeeded, it might just be empty or unexpected format
                logger.warning(
                    f"Response missing '{list_key}' array. Response keys: {list(json_data.keys())}"
                )
                return []

            # Apply the mapping function to standardize output
            results = [mapping_func(item) for item in json_data[list_key]]
            logger.info(f"Found {len(results)} {list_key}.")
            return results

        except HTTPError as e:
            logger.error(f"HTTP Error fetching devices: {e.response.text}")
            return []
        except Exception as e:
            logger.error(f"Unexpected error in generic fetcher: {e}")
            return []

    def get_cameras(self) -> List[Dict[str, Any]]:
        """
        Fetches a list of cameras using the generic fetcher pattern.
        """
        return self._fetch_objects_generic(
            url=f"https://{self.region}.verkada.com/cameras/v1/devices",
            list_key="cameras",
            error_signature="must include cameras",
            mapping_func=lambda x: {
                "id": x.get("camera_id"),
                "name": x.get("name"),
            },
        )

    def get_access_controllers(self) -> List[Dict[str, Any]]:
        """
        Fetches a list of access controllers using the generic fetcher pattern.
        """
        return self._fetch_objects_generic(
            url=f"https://{self.region}.verkada.com/access/v1/doors",
            list_key="doors",
            error_signature="must include controllers",
            mapping_func=lambda x: {
                "id": x.get("acu_id"),
                "name": x.get("acu_name"),
            },
        )

    def get_guest_sites(self) -> List[Dict[str, Any]]:
        """
        Fetches a list of guest sites using the generic fetcher pattern.
        """
        return self._fetch_objects_generic(
            url=f"https://{self.region}.verkada.com/guest/v1/sites",
            list_key="guest_sites",
            error_signature="must include guest sites",
            mapping_func=lambda x: {
                "id": x.get("site_id"),
                "name": x.get("site_name"),
            },
        )

    def get_users(
        self, exclude_user_id: Optional[str] = None, exclude_email: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Fetches a list of users using the generic fetcher pattern.
        Optionally filters out a specific user ID (e.g., the current admin).
        """
        users = self._fetch_objects_generic(
            url=f"https://{self.region}.verkada.com/access/v1/access_users",
            list_key="access_members",
            error_signature="must include users",
            mapping_func=lambda x: {
                "id": x.get("user_id"),
                "email": x.get("email"),
            },
        )

        if exclude_user_id:
            initial_count = len(users)
            users = [u for u in users if str(u["id"]) != str(exclude_user_id)]
            if len(users) < initial_count:
                logger.info(
                    f"Filtered out admin user ({exclude_user_id}) from inventory."
                )

        if exclude_email:
            initial_count = len(users)
            users = [u for u in users if u["email"] != exclude_email]
            if len(users) < initial_count:
                logger.info(
                    f"Filtered out user with email ({exclude_email}) from inventory."
                )
        return users

    def remove_user(self, user_id: str) -> bool:
        """
        Removes a user from the system.
        """
        url = "https://api.verkada.com/core/v1/user"
        headers = {"accept": "application/json", "x-verkada-auth": self.api_token}
        params = {"user_id": user_id}

        res = self.session.delete(url, headers=headers, params=params)

        if res.status_code == 200:
            logger.info(f"Successfully deleted user {user_id}")
            return True
        else:
            logger.error(f"Failed to delete user {user_id}: {res.text}")
            return False


def get_env_var(key: str, default: Optional[str] = None) -> str:
    """Safely gets a required environment variable with optional default."""
    value = os.environ.get(key, default)
    if not value:
        raise EnvironmentError(f"Missing required environment variable: {key}")
    return value


def print_console_report(org_name: str, inventory: Dict[str, List[Dict[str, Any]]]):
    """
    Prints a detailed, formatted inventory report to the console.
    """
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # Helper for printing separators
    def print_sep(char="=", length=80):
        print(char * length)

    # Header
    print("\n")
    print_sep("=")
    print("  VERKADA INVENTORY REPORT".center(80))
    print(f"  Organization: {org_name}".center(80))
    print(f"  Generated on: {timestamp}".center(80))
    print_sep("=")
    print("\n")

    # Dashboard Summary
    print("  SUMMARY BREAKDOWN")
    print_sep("-", 40)

    total_devices = 0
    for category, items in inventory.items():
        count = len(items)
        total_devices += count
        print(f"  • {category.replace('_', ' '):<25} : {count:>5}")

    print_sep("-", 40)
    print(f"  • {'TOTAL ASSETS':<25} : {total_devices:>5}")
    print("\n")

    # Detailed Listings
    for category, items in inventory.items():
        title = category.replace("_", " ").title()

        print_sep("=")
        print(f"  CATEGORY: {title} ({len(items)})")
        print_sep("=")

        if not items:
            print("  (No items found in this category)")
            print("\n")
            continue

        # Determine column widths dynamically
        # Default min widths
        max_name_len = 20
        max_id_len = 15

        # Prepare data for printing and calculate max lengths
        rows = []
        for item in items:
            obj_id = item.get("id")
            if isinstance(obj_id, list):
                obj_id = ", ".join(map(str, obj_id))

            obj_id_str = str(obj_id)
            # FIX: Fallback logic for items that don't have "email" (cameras, sensors, etc)
            name_str = (
                item.get("email")
                or item.get("name")
                or item.get("businessName")
                or "(No Name)"
            )

            rows.append((name_str, obj_id_str))

            if len(name_str) > max_name_len:
                max_name_len = min(len(name_str), 60)  # Cap at 60 chars
            if len(obj_id_str) > max_id_len:
                max_id_len = len(obj_id_str)

        # Create format string
        # Name column | ID column
        # Add padding
        col_name_w = max_name_len + 2
        col_id_w = max_id_len + 2

        header_fmt = f"  {{:<{col_name_w}}} | {{:<{col_id_w}}}"
        row_fmt = f"  {{:<{col_name_w}}} | {{:<{col_id_w}}}"
        divider = f"  {'-' * col_name_w}-+-{'-' * col_id_w}"

        # Print Table
        print(header_fmt.format("Name / Description", "ID"))
        print(divider)

        for name, obj_id in rows:
            # Truncate if still too long for the column (should match max_name_len cap)
            if len(name) > max_name_len:
                name = name[: max_name_len - 3] + "..."

            print(row_fmt.format(name, obj_id))

        print("\n")

    print_sep("=")
    print("  End of Report".center(80))
    print_sep("=")
    print("\n")
    logger.info("Report printing complete.")


def perform_mass_deletion(
    internal_client: VerkadaInternalAPIClient,
    external_client: VerkadaExternalAPIClient,
    inventory: Dict[str, List[Dict[str, Any]]],
):
    """
    Iterates through the inventory based on a hardcoded order,
    allows for mass 'Nuclear' deletion, or per-category confirmation.
    """

    # --- HARDCODED DELETION ORDER ---
    # Rearrange this list to change the order of operations.
    DELETION_ORDER = [
        "Users",
        "Cameras",
        "Sensors",
        "Access_Controllers",
        "Intercoms",
        "Alarm_Sites",
        "Mailroom_Sites",
        "Guest_Sites",
        "Desk_Stations",
    ]

    # Map Inventory Category Keys -> Decommission Function args
    RESOURCE_MAPPING = {
        "Cameras": {"type": "camera", "client": "internal"},
        "Access_Controllers": {"type": "access_controller", "client": "internal"},
        "Sensors": {"type": "sensor", "client": "internal"},
        "Intercoms": {"type": "intercom", "client": "internal"},
        "Guest_Sites": {"type": "guest_site", "client": "internal"},
        "Mailroom_Sites": {"type": "mailroom_site", "client": "internal"},
        "Alarm_Sites": {"type": "alarm_site", "client": "internal"},
        "Users": {"type": "user", "client": "external"},
        "Desk_Stations": {"type": "desk_station", "client": "internal"},
    }

    print("\n" + "!" * 80)
    print("!" * 80)
    print("    DESTRUCTION SEQUENCE INITIATED")
    print("!" * 80 + "\n")

    # --- MODE SELECTION ---
    print("SELECT DELETION MODE:")
    print("1. Interactive Mode (Confirm each category separately)")
    print("2. NUCLEAR MODE (Delete EVERYTHING without further prompts)")

    skip_confirmations = False
    mode = input("\nSelect Mode [1/2]: ").strip()

    if mode == "2":
        print("\n⚠️  WARNING: NUCLEAR MODE SELECTED ⚠️")
        print("This will delete ALL devices and users listed in the report above.")
        print("There is NO UNDO.")
        confirm = input("Type 'DESTROY EVERYTHING' to confirm: ")
        if confirm == "DESTROY EVERYTHING":
            skip_confirmations = True
            print("\n🚨 NUCLEAR LAUNCH DETECTED. BYPASSING SAFETY LOCKS. 🚨")
        else:
            print("\nConfirmation failed. Reverting to Interactive Mode.")

    # --- EXECUTION LOOP ---
    for category in DELETION_ORDER:
        items = inventory.get(category, [])

        # Skip if empty
        if not items:
            continue

        count = len(items)
        display_name = category.replace("_", " ")

        # If not in nuclear mode, ask for permission
        if not skip_confirmations:
            print("\n⚠️ \t DANGER - PLEASE CONFIRM")
            print(f"You are about to decommission ALL {count} {display_name}.")
            confirmation = input(
                f"Type '{category}' to confirm deletion, or anything else to skip: "
            )

            if confirmation.strip() != category:
                print(f"Skipping {display_name}...")
                continue

        print(f"\n🚀 Proceeding to delete {count} {display_name}...")

        config = RESOURCE_MAPPING.get(category)
        if not config:
            logger.error(f"No deletion logic mapped for {category}")
            continue

        success_count = 0
        fail_count = 0

        for item in items:
            item_id = item["id"]
            name = item.get("name") or item.get("email") or "Unknown"

            result = False

            # Route to appropriate client
            if config["client"] == "external":
                if config["type"] == "user":
                    result = external_client.remove_user(item_id)
            else:
                # Internal Client
                result = internal_client.remove_object(config["type"], item_id)

            if result:
                success_count += 1
                print(f"  [✓] Deleted: {name} ({item_id})")
            else:
                fail_count += 1
                print(f"  [X] FAILED: {name} ({item_id})")

        print(
            f"\nFinished {display_name}. Success: {success_count}, Failed: {fail_count}"
        )


def main():
    try:
        # Load configuration
        admin_email = get_env_var("ADMIN_EMAIL")
        admin_pass = get_env_var("ADMIN_PASSWORD")
        org_short_name = get_env_var("ORG_SHORT_NAME")
        shard = get_env_var("SHARD", default="prod1")
        region = get_env_var("REGION", default="api")

        # Initialize Clients
        internal_client = VerkadaInternalAPIClient(
            admin_email, admin_pass, org_short_name, shard
        )

        # Login to internal API
        internal_client.login()
        external_api_key = internal_client.create_external_api_key()
        external_client = VerkadaExternalAPIClient(
            external_api_key, org_short_name, region
        )

        logger.info("Starting inventory gathering...")

        # Gather all data into a dictionary
        # We fetch the admin ID from the internal client to ensure we don't delete ourselves
        current_admin_id = (
            internal_client.auth_data.get("adminUserId")
            if internal_client.auth_data
            else None
        )

        inventory = {
            "Cameras": external_client.get_cameras(),
            "Access_Controllers": external_client.get_access_controllers(),
            "Sensors": internal_client.get_sensors(),
            "Intercoms": internal_client.get_intercoms(),
            "Guest_Sites": external_client.get_guest_sites(),
            "Mailroom_Sites": internal_client.get_mailroom_sites(),
            "Alarm_Sites": internal_client.get_alarm_sites(),
            "Users": external_client.get_users(exclude_user_id=current_admin_id),
            "Desk_Stations": internal_client.get_desk_stations(),
        }

        # Generate the Report
        print_console_report(org_short_name, inventory)

        # --- TRIGGER DELETION FLOW ---
        perform_mass_deletion(internal_client, external_client, inventory)

        # Logout
        internal_client.logout()

    except KeyboardInterrupt:
        print("\nOperation cancelled by user.")
        sys.exit(0)
    except Exception as err:
        logger.exception(f"An unexpected error occurred: {err}")
        sys.exit(1)


if __name__ == "__main__":
    main()
