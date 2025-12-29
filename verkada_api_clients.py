import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Union

import requests
from requests.adapters import HTTPAdapter
from requests.exceptions import HTTPError, JSONDecodeError
from requests.models import Response
from urllib3.util.retry import Retry

from verkada_utilities import get_env_var, sanitize_list

logger = logging.getLogger(__name__)


class VerkadaInternalAPIClient:
    """
    A client to interact with the internal Verkada Provisioning and Response APIs.
    """

    BASE_URL_PROVISION = "https://vprovision.command.verkada.com/__v/"

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
    def user_id(self) -> Optional[str]:
        """
        Returns the User ID as a string if authenticated.
        """
        if self.auth_data:
            return self.auth_data.get("adminUserId")
        return None

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
        response = Response()

        try:
            response = self.session.post(login_url, json=payload)
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

    def _handle_mfa(
        self, login_url: str, base_payload: Dict[str, Any], mfa: Optional[str] = None
    ) -> None:
        """
        Internal method to handle the interactive MFA flow.
        Includes retry logic for incorrect codes.
        """
        try:
            # Prompt user
            if mfa:
                two_fa_code = mfa
            else:
                two_fa_code = input("Enter 2FA code: ").strip()
            if not two_fa_code or len(two_fa_code) < 6:
                raise ValueError("Invalid 2FA code format or Empty.")

            # Prepare payload
            mfa_payload = base_payload.copy()
            mfa_payload["otp"] = two_fa_code

            # Send request
            response = self.session.post(login_url, json=mfa_payload)

            # 1. Success Case
            if response.status_code == 200:
                logger.info("Successfully completed 2FA.")
                self.auth_data = self._parse_login_response(response.json())
                return

            # 2. Handle Errors
            try:
                error_data = response.json()
                error_msg = error_data.get("message", "")
            except JSONDecodeError:
                error_msg = response.text

            # Check specifically for "2FA invalid" in the server response
            if "2FA invalid" in error_msg:
                logger.error("Incorrect 2FA code. Please try again.")
                raise ConnectionError("Incorrect 2FA code. Please try again.")
            # If it's some other error (e.g. server down), raise immediately
            raise ConnectionError(f"MFA Failed with unexpected error: {error_msg}")

        except (EOFError, KeyboardInterrupt):
            # Allow user to Ctrl+C to exit cleanly
            print()  # Newline for cleaner output
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

    def set_access_system_admin(self) -> None:
        if not self.auth_data:
            raise PermissionError("Not authenticated. Please call login() first.")
        url = f"https://vcerberus.command.verkada.com/__v/{self.org_short_name}/access/v2/user/roles/modify"
        payload = {
            "grants": [
                {
                    "entityId": self.org_id,
                    "granteeId": self.user_id,
                    "roleKey": "ACCESS_CONTROL_SYSTEM_ADMIN",
                    "role": "ACCESS_CONTROL_SYSTEM_ADMIN",
                },
                {
                    "entityId": self.org_id,
                    "granteeId": self.user_id,
                    "roleKey": "ACCESS_CONTROL_USER_ADMIN",
                    "role": "ACCESS_CONTROL_USER_ADMIN",
                },
            ]
        }
        headers = self._get_headers()
        try:
            response = self.session.post(url, json=payload, headers=headers)
            response.raise_for_status()  # Raise error for 4xx/5xx
            data = response.json()
            logger.info(f"Escalated user to Access System Admin {data}")
        except (HTTPError, JSONDecodeError) as e:
            logger.error(f"Failed to escalate to Access System Admin: {e}")

    def get_object(
        self,
        categories: str,
    ) -> List[Dict[str, Any]]:
        """
        Get a list of objects of a given type.
        """
        if not self.auth_data:
            raise PermissionError("Not authenticated. Please call login() first.")
        payload = None
        match categories:
            case "intercoms":
                object_type = "intercoms"
                request_type = "GET"
                subdomain = "api"
                path = f"vinter/v1/user/organization/{self.org_id}/device"

                def mapping_func(x):
                    return {
                        "id": x["deviceId"],
                        "name": x["name"],
                        "serial_number": x["serialNumber"],
                    }

            case "access_controllers":
                object_type = "accessControllers"
                request_type = "GET"
                subdomain = "vcerberus"
                path = "access/v2/user/access_controllers"

                def mapping_func(x):
                    return {
                        "id": x["accessControllerId"],
                        "name": x["name"],
                        "serial_number": x["serialNumber"],
                    }

            case "sensors":
                object_type = "sensorDevice"
                request_type = "POST"
                subdomain = "vsensor"
                path = "devices/list"
                payload = {"organizationId": self.org_id}

                def mapping_func(x):
                    return {
                        "id": x["deviceId"],
                        "name": x["name"],
                        "serial_number": x["claimedSerialNumber"],
                    }

            case "mailroom_sites":
                object_type = "package_sites"
                request_type = "GET"
                subdomain = "vdoorman"
                path = f"package_site/org/{self.org_id}"

                def mapping_func(x):
                    return {"id": x["siteId"], "name": x["siteName"]}

            case "desk_stations":
                object_type = "deskApps"
                request_type = "GET"
                subdomain = "api"
                path = f"vinter/v1/user/organization/{self.org_id}/device"

                def mapping_func(x):
                    return {
                        "id": x["deviceId"],
                        "name": x["name"],
                        "serial_number": x["serialNumber"],
                    }

            case "alarm_sites":
                object_type = "responseSites"
                request_type = "POST"
                subdomain = "vproresponse"
                path = "response/site/list"
                payload = {"includeResponseConfigs": True}

                def mapping_func(x):
                    return {
                        "site_id": x["siteId"],
                        "alarm_site_id": x["id"],
                        "alarm_system_id": x.get("alarmSystemId"),
                        "name": x["businessName"],
                    }

            case "alarm_devices":
                object_type = "devices"
                request_type = "POST"
                subdomain = "vproconfig"
                path = "org/get_devices_and_alarm_systems"

                def mapping_func(x):
                    return {
                        "id": x["id"],
                        "name": x["name"],
                        "serial_number": x["verkadaDeviceConfig"]["serialNumber"],
                    }

            case "unassigned_devices":
                object_type = "devices"
                request_type = "GET"
                subdomain = "vconductor"
                path = f"org/{self.org_id}/unassigned_devices"

                def mapping_func(x):
                    return {
                        "id": x["deviceId"],
                        "name": x["name"],
                        "serial_number": x["serialNumber"],
                    }

            case _:
                raise ValueError(f"Unknown device type: {categories}")

        url = (
            f"https://{subdomain}.command.verkada.com/__v/{self.org_short_name}/{path}"
        )
        headers = self._get_headers()
        logger.info(f"Finding {categories}...")

        if request_type == "POST":
            response = self.session.post(url, headers=headers, json=payload)
        else:
            response = self.session.get(url, headers=headers)

        try:
            response.raise_for_status()
            data = response.json()
            results = [mapping_func(item) for item in data[object_type]]
            logger.info(f"Retrieved {len(results)} {categories}")
            return results
        except (HTTPError, JSONDecodeError) as e:
            logger.error(f"Failed to fetch {categories}: {e}")
            return []
        except Exception as e:
            logger.error(f"Unexpected error fetching {categories}: {e}")
            return []

    def delete_object(self, categories: str, object_id: Union[str, List[str]]):
        payload = None
        match categories:
            case "intercoms":
                request_type = "DELETE"
                subdomain = "api"
                path = f"vinter/v1/user/async/organization/{self.org_id}/device/{object_id}"
                # payload = {"sharding": True}

            case "access_controllers":
                request_type = "POST"
                subdomain = "vcerberus"
                path = "access_device/decommission"
                payload = {"deviceId": object_id, "sharding": True}

            case "sensors":
                request_type = "POST"
                subdomain = "vsensor"
                path = "devices/decommission"
                payload = {"deviceId": object_id, "sharding": True}

            case "mailroom_sites":
                request_type = "DELETE"
                subdomain = "vdoorman"
                path = f"package_site/org/{self.org_id}?siteId={object_id}"

            case "desk_stations":
                request_type = "DELETE"
                subdomain = "api"
                path = f"vinter/v1/user/async/organization/{self.org_id}/device/{object_id}"
                payload = {"sharding": True}

            case "alarm_systems":
                request_type = "POST"
                subdomain = "vproconfig"
                path = "alarm_system/delete"
                payload = {"alarmSystemId": object_id}

            case "alarm_devices":
                request_type = "POST"
                subdomain = "vproconfig"
                path = "device/decommission"
                payload = {"deviceId": object_id}

            case "alarm_sites":
                request_type = "POST"
                subdomain = "vproresponse"
                path = "response/site/delete"
                payload = {"responseSiteId": object_id[0], "siteId": object_id[1]}

            case "guest_sites":
                request_type = "DELETE"
                subdomain = "vdoorman"
                path = f"site/org/{self.org_id}?siteId={object_id}"

            case "cameras":
                request_type = "POST"
                subdomain = "vprovision"
                path = "camera/decommission"
                payload = {"cameraId": object_id}

            case _:
                raise ValueError(f"Unknown device type: {categories}")
        url = (
            f"https://{subdomain}.command.verkada.com/__v/{self.org_short_name}/{path}"
        )
        headers = self._get_headers()
        logger.info(f"Removing {categories} - {object_id}")

        if request_type == "POST":
            response = self.session.post(url, headers=headers, json=payload)
        else:
            response = self.session.delete(url, headers=headers)

        try:
            response.raise_for_status()
            if response.status_code in [200, 204]:
                logger.info(f"Successfully removed {categories} - {object_id}")
                return True
            else:
                logger.error(
                    f"Failed to remove {categories} - {object_id}: {response.status_code}"
                )
                return False
        except Exception as e:
            logger.error(f"Unexpected error removing {categories}: {e}")
            return []


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

    def get_object(
        self,
        categories: str,
    ) -> List[Dict[str, Any]]:
        error_signature = None
        match categories:
            case "cameras":
                object_type = "cameras"
                path = "cameras/v1/devices"
                error_signature = "must include cameras"

                def mapping_func(x):
                    return {
                        "id": x["camera_id"],
                        "name": x["name"],
                        "serial_number": x["serial"],
                    }

            case "guest_sites":
                object_type = "guest_sites"
                path = "guest/v1/sites"

                def mapping_func(x):
                    return {"id": x["site_id"], "name": x["site_name"]}

            case "users":
                object_type = "access_members"
                path = "access/v1/access_users"

                def mapping_func(x):
                    return {
                        "id": x["user_id"],
                        "name": x["full_name"],
                        "email": x["email"],
                    }

            case _:
                raise ValueError(f"Unknown device type: {categories}")

        url = f"https://{self.region}.verkada.com/{path}"
        headers = {"accept": "application/json", "x-verkada-auth": self.api_token}
        params = {"page_size": 200}
        logger.info(f"Finding {categories}...")

        response = self.session.get(url, headers=headers, params=params)

        if response.status_code == 400:
            if error_signature and error_signature in response.text:
                logger.info(f"Retrieved 0 {categories}")
                return []

        try:
            response.raise_for_status()
            data = response.json()
            results = [mapping_func(item) for item in data[object_type]]
            logger.info(f"Retrieved {len(results)} {categories}")
            return results
        except (HTTPError, JSONDecodeError) as e:
            logger.error(f"Failed to fetch {categories}: {e}")
            return []
        except Exception as e:
            logger.error(f"Unexpected error fetching {categories}: {e}")
            return []

    def get_users(
        self, exclude_user_id: Optional[str] = None, exclude_email: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Fetches a list of users using the generic fetcher pattern.
        Optionally filters out a specific user ID or emails (e.g., the current admin).
        """
        users = self.get_object("users")
        if exclude_user_id is not None:
            initial_count = len(users)
            clean_exclude_id = str(exclude_user_id).strip()
            users = [
                u for u in users if str(u.get("id", "")).strip() != clean_exclude_id
            ]
            if len(users) < initial_count:
                logger.info(f"Filtered out user ({exclude_user_id}) from inventory.")
                pass

        if exclude_email:
            initial_count = len(users)
            clean_exclude_email = exclude_email.strip().lower()
            users = [
                u
                for u in users
                if u.get("email", "").strip().lower() != clean_exclude_email
            ]
            if len(users) < initial_count:
                logger.info(f"Filtered out emails ({exclude_email}) from inventory.")
                pass
        return users


logging.basicConfig(
    level=logging.INFO,
    format="(%(asctime)s) [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)
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
external_client = VerkadaExternalAPIClient(external_api_key, org_short_name, region)

sensors = internal_client.get_object("sensors")
intercoms = internal_client.get_object("intercoms")
desk_stations = internal_client.get_object("desk_stations")
mailroom_sites = internal_client.get_object("mailroom_sites")
access_controllers = sanitize_list(
    intercoms, internal_client.get_object("access_controllers")
)
cameras = sanitize_list(intercoms, external_client.get_object("cameras"))
guest_sites = external_client.get_object("guest_sites")
users = external_client.get_users(exclude_user_id=internal_client.user_id)
alarm_sites = internal_client.get_object("alarm_sites")
alarm_devices = internal_client.get_object("alarm_devices")
unassigned_devices = internal_client.get_object("unassigned_devices")

for sensor in sensors:
    print(internal_client.delete_object("sensors", sensor["id"]))
for intercom in intercoms:
    print(internal_client.delete_object("intercoms", intercom["id"]))
for desk_station in desk_stations:
    print(internal_client.delete_object("desk_stations", desk_station["id"]))
for mailroom_site in mailroom_sites:
    print(internal_client.delete_object("mailroom_sites", mailroom_site["id"]))
for access_controller in access_controllers:
    print(internal_client.delete_object("access_controllers", access_controller["id"]))
for camera in cameras:
    print(internal_client.delete_object("cameras", camera["id"]))
for guest_site in guest_sites:
    print(internal_client.delete_object("guest_sites", guest_site["id"]))
for alarm_device in alarm_devices:
    print(internal_client.delete_object("alarm_devices", alarm_device["id"]))
for alarm_site in alarm_sites:
    if alarm_site["alarm_system_id"]:
        print(
            internal_client.delete_object(
                "alarm_systems", alarm_site["alarm_system_id"]
            )
        )
    print(
        internal_client.delete_object(
            "alarm_sites", [alarm_site["alarm_site_id"], alarm_site["site_id"]]
        )
    )
for unassigned_device in unassigned_devices:
    print("Please remove the following devices:")
    print(
        f"Device ID: {unassigned_device['id']}, Serial Number: {unassigned_device['serial_number']}"
    )

# Print serial numbers of intercoms and cameras
# for intercom in intercoms:
#     print(f"Intercom ID: {intercom['id']}, Serial Number: {intercom['serial_number']}")
# for sensor in sensors:
#     print(f"Sensor ID: {sensor['id']}, Serial Number: {sensor['serial_number']}")
# for access_controller in access_controllers:
#     print(
#         f"Access Controller ID: {access_controller['id']}, Serial Number: {access_controller['serial_number']}"
#     )
# for camera in cameras:
#     print(f"Camera ID: {camera['id']}, Serial Number: {camera['serial_number']}")
# for guest_site in guest_sites:
#     print(f"Guest Site ID: {guest_site['id']}, Name: {guest_site['name']}")
# for mailroom_site in mailroom_sites:
#     print(f"Mailroom Site ID: {mailroom_site['id']}, Name: {mailroom_site['name']}")
# for desk_station in desk_stations:
#     print(f"Desk Station ID: {desk_station['id']}, Name: {desk_station['name']}")
# for user in users:
#     print(f"User ID: {user['id']}, Email: {user['email']}")
# for alarm in alarm_sites:
#     print(
#         f"Alarms: \n Site ID: {alarm['site_id']}, Alarm Site ID: {alarm['alarm_site_id']}, Name: {alarm['name']}, Alarm System ID: {alarm['alarm_system_id']}"
#     )
# for device in alarm_devices:
#     print(f"AlarmDevices: \n Device ID: {device['id']}, Name: {device['name']}")
# for device in unassigned_devices:
#     print(f"Unassigned Device ID: {device['id']}, Serial Number: {device['name']}")
