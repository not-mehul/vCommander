import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Union

import requests
from requests.adapters import HTTPAdapter
from requests.exceptions import HTTPError, JSONDecodeError
from requests.models import Response
from urllib3.util.retry import Retry

logger = logging.getLogger(__name__)


class MFARequiredError(Exception):
    """Raised when the API requires 2FA to complete login."""

    def __init__(self, message, sms_contact=None):
        super().__init__(message)
        self.sms_contact = sms_contact


class VerkadaInternalAPIClient:
    """
    A client to interact with the internal Verkada Provisioning and Response APIs.

    This client simulates the behavior of the web interface (Command) by using
    user credentials (email/password) to obtain a session cookie and CSRF token.
    It handles 2FA/MFA if required by the organization.
    """

    BASE_URL_PROVISION = "https://vprovision.command.verkada.com/__v/"

    def __init__(self, email: str, password: str, org_short_name: str, shard: str):
        """
        Initializes the internal client with credentials.

        Args:
            email: Admin email address.
            password: Admin password.
            org_short_name: The short identifier for the organization (e.g., "myorg").
            shard: The specific backend shard to connect to (e.g., "prod1").
        """
        self.email = email
        self.password = password
        self.org_short_name = org_short_name
        self.shard = shard

        # Initialize a persistent session to maintain cookies across requests
        self.session = requests.Session()

        # Storage for auth tokens (CSRF, User ID, Org ID, etc.) populated after login
        self.auth_data: Optional[Dict[str, str]] = None
        self._pending_login_url = None
        self._pending_payload = None

    @property
    def user_id(self) -> Optional[str]:
        """
        Returns the authenticated User ID as a string.
        Returns None if login() has not been called successfully yet.
        """
        if self.auth_data:
            return self.auth_data.get("adminUserId")
        return None

    @property
    def org_id(self) -> Optional[str]:
        """
        Returns the Organization ID as a string.
        Returns None if login() has not been called successfully yet.
        """
        if self.auth_data:
            return self.auth_data.get("organizationId")
        return None

    def _get_headers(self) -> Dict[str, str]:
        """
        Constructs the specific HTTP headers required for internal API calls.

        These headers mimic a browser session. Crucially, it includes the
        'Cookie' string and custom 'x-verkada-*' headers derived from auth data.
        """
        if not self.auth_data:
            return {}

        return {
            "Accept": "*/*",
            "Cookie": self.auth_data.get("cookie", ""),
            "x-verkada-organization-id": self.auth_data.get("organizationId", ""),
            "x-verkada-token": self.auth_data.get("csrfToken", ""),
            "x-verkada-user-id": self.auth_data.get("adminUserId", ""),
            # Origin and Referer are often checked by backend security policies
            "origin": f"https://{self.org_short_name}.command.verkada.com",
            "referer": f"https://{self.org_short_name}.command.verkada.com/",
        }

    def _parse_login_response(self, json_data: Dict[str, Any]) -> Dict[str, str]:
        """
        Extracts critical session data from a successful login API response.

        It manually constructs the cookie string expected by subsequent requests.
        """
        try:
            csrf_token = str(json_data["csrfToken"])
            user_token = str(json_data["userToken"])
            organization_id = str(json_data["organizationId"])
            admin_user_id = str(json_data["userId"])

            # Manually constructing the cookie string required for internal APIs
            # This combines the user token, org ID, user ID, and CSRF token.
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
        Authenticates with the Verkada Provisioning API.

        Flow:
        1. Sends POST request with credentials.
        2. Checks if 2FA (MFA) is required (HTTP 400 with specific message).
        3. If 2FA is required, triggers the interactive _handle_mfa() method.
        4. Parses the successful response to store session data in self.auth_data.
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
        # The API typically returns 400 if credentials are correct but 2FA is needed
        if response.status_code == 400:
            msg = data.get("message", "") or response.text
            if "mfa_required_for_org_admin" in msg or "2FA invalid" in msg:
                logger.info(f"2FA is required for {self.email}")
                # Store state for Step 2
                self._pending_login_url = login_url
                self._pending_payload = payload

                sms_contact = data.get("data", {}).get("smsSent")

                # Signal the GUI to switch screens
                raise MFARequiredError("MFA Required", sms_contact)

        # 3. Failure Scenario
        raise ConnectionError(
            f"Login failed with status {response.status_code}: {response.text}"
        )

    def verify_mfa(self, otp_code: str) -> None:
        if not self._pending_payload:
            raise ValueError(
                "No pending login attempt found. Please call login() first."
            )

        # Prepare payload: original credentials + the OTP code
        mfa_payload = self._pending_payload.copy()
        mfa_payload["otp"] = otp_code

        logger.info("Submitting OTP code...")

        try:
            response = self.session.post(self._pending_login_url, json=mfa_payload)

            # 1. Success Case
            if response.status_code == 200:
                logger.info("Successfully completed 2FA.")
                self.auth_data = self._parse_login_response(response.json())

                # Clear pending data
                self._pending_login_url = None
                self._pending_payload = None
                return

            # 2. Handle Errors
            try:
                error_data = response.json()
                error_msg = error_data.get("message", "")
            except JSONDecodeError:
                error_msg = response.text

            if "2FA invalid" in error_msg:
                raise ValueError("Incorrect 2FA code.")

            raise ConnectionError(f"MFA Failed: {error_msg}")

        except Exception as e:
            logger.error(f"Error during MFA verification: {e}")
            raise

    # def _handle_mfa(
    #     self, login_url: str, base_payload: Dict[str, Any], mfa: Optional[str] = None
    # ) -> None:
    #     """
    #     Internal method to handle the interactive MFA flow.

    #     Args:
    #         login_url: The URL to post the MFA code to.
    #         base_payload: The original login payload (email, password, etc.).
    #         mfa: Optional pre-supplied MFA code (useful for testing or automation).
    #     """
    #     try:
    #         # Prompt user for code via console
    #         if mfa:
    #             two_fa_code = mfa
    #         else:
    #             two_fa_code = input("Enter 2FA code: ").strip()

    #         if not two_fa_code or len(two_fa_code) < 6:
    #             raise ValueError("Invalid 2FA code format or Empty.")

    #         # Prepare payload: original credentials + the OTP code
    #         mfa_payload = base_payload.copy()
    #         mfa_payload["otp"] = two_fa_code

    #         # Send request
    #         response = self.session.post(login_url, json=mfa_payload)

    #         # 1. Success Case
    #         if response.status_code == 200:
    #             logger.info("Successfully completed 2FA.")
    #             self.auth_data = self._parse_login_response(response.json())
    #             return

    #         # 2. Handle Errors
    #         try:
    #             error_data = response.json()
    #             error_msg = error_data.get("message", "")
    #         except JSONDecodeError:
    #             error_msg = response.text

    #         # Check specifically for "2FA invalid" in the server response
    #         if "2FA invalid" in error_msg:
    #             logger.error("Incorrect 2FA code.")
    #             raise SystemExit()
    #         # If it's some other error (e.g. server down), raise immediately
    #         raise ConnectionError(f"MFA Failed with unexpected error: {error_msg}")

    #     except (EOFError, KeyboardInterrupt):
    #         # Allow user to Ctrl+C to exit cleanly without a traceback explosion
    #         print()  # Newline for cleaner output
    #         raise InterruptedError("User canceled 2FA prompt.")

    def create_external_api_key(self) -> str:
        """
        Generates a temporary External API Key.

        This key is required to initialize the `VerkadaExternalAPIClient`.
        It creates a key with specific read/write permissions for Decommissioning.
        The key is set to expire in 1 hour.
        """
        if not self.auth_data:
            raise PermissionError("Not authenticated. Please call login() first.")

        url = f"https://apiadmin.command.verkada.com/__v/{self.org_short_name}/admin/orgs/{self.org_id}/v2/granular_apikeys"

        payload = {
            "api_key_name": "Decommissioning API Key - " + str(datetime.now()),
            "expires_at": int((datetime.now() + timedelta(hours=1)).timestamp()),
            # Grants full permissions needed for decommissioning assets
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
            response.raise_for_status()

            data = response.json()
            api_key = data.get("apiKey")
            logger.info(f"Generated API key: {api_key}")
            return api_key

        except HTTPError as e:
            if e.response is not None and e.response.status_code == 400:
                try:
                    err_data = e.response.json()
                    if err_data.get("message") == "Would exceed 10 api keys limit":
                        logger.error(
                            "Failed to generate API key: Exceeded 10 API Keys Limit"
                        )
                        raise SystemExit()
                except JSONDecodeError:
                    pass
            logger.error(f"Failed to generate API key: {e}")
            raise SystemExit()
        except JSONDecodeError as e:
            logger.error(f"Failed to parse response: {e}")
            raise SystemExit()

    def set_access_system_admin(self) -> None:
        """
        Escalates the current user's privileges to Access System Admin.

        Required because standard admin privileges might not be enough to
        delete certain access control hardware.
        """
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
            # data = response.json()
            logger.info("Escalated user to Access System Admin")
        except (HTTPError, JSONDecodeError) as e:
            logger.error(f"Failed to escalate to Access System Admin: {e}")

    def enable_global_site_admin(self):
        """
        Updates the organization's Global Site Admin toggle to True.

        Ensures that the org admins are site admins for all sites in the organization
        """
        if not self.auth_data:
            raise PermissionError("Not authenticated. Please call login() first.")

        url = f"https://vprovision.command.verkada.com/__v/{self.org_short_name}/org/settings/update"
        payload = {"organizationId": self.org_id, "settings": {"globalSiteAdmin": True}}
        headers = self._get_headers()
        try:
            response = self.session.post(url, json=payload, headers=headers)
            response.raise_for_status()  # Raise error for 4xx/5xx
            # data = response.json()
            logger.info("Enabled Global Site Admin")
        except (HTTPError, JSONDecodeError) as e:
            logger.error(f"Failed to enable Global Site Admin: {e}")

    def invite_user(self, first_name: str, last_name: str, email: str, org_admin: bool):
        if not self.auth_data:
            raise PermissionError("Not authenticated. Please call login() first.")
        url = f"https://vprovision.command.verkada.com/__v/{self.org_short_name}/org/invite"
        payload = {
            "organizationId": self.org_id,
            "email": email,
            "orgAdmin": org_admin,
            "commandUserAdmin": False,
            "firstName": first_name,
            "lastName": last_name,
            "inviteFf": True,
        }
        headers = self._get_headers()
        try:
            response = self.session.post(url, json=payload, headers=headers)
            response.raise_for_status()  # Raise error for 4xx/5xx
            logger.info(
                f"Invited user {first_name} {last_name} ({email}) to organization"
            )
        except (HTTPError, JSONDecodeError) as e:
            logger.error(
                f"Failed to invite user {first_name} {last_name} ({email}): {e}"
            )

    def get_object(
        self,
        categories: str,
    ) -> List[Dict[str, Any]]:
        """
        Generic fetch method for various Verkada device types via Internal API.

        Args:
            categories: The type of object to fetch (e.g., 'intercoms', 'sensors').

        Returns:
            A list of dictionaries, where each dict represents a device
            and contains standardized keys: 'id', 'name', 'serial_number'.
        """
        if not self.auth_data:
            raise PermissionError("Not authenticated. Please call login() first.")

        payload = None

        # Configure request details based on the category
        match categories:
            case "intercoms":
                object_type = "intercoms"
                request_type = "GET"
                subdomain = "api"
                path = f"vinter/v1/user/organization/{self.org_id}/device"

                # Standardize output
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
                        "id": x["id"],
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

        # Execute Request
        if request_type == "POST":
            response = self.session.post(url, headers=headers, json=payload)
        else:
            response = self.session.get(url, headers=headers)

        try:
            response.raise_for_status()
            data = response.json()
            # Apply mapping function to normalize data structure
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
        """
        Decommissions or deletes a specific object by ID via Internal API.

        Args:
            categories: The type of object to delete.
            object_id: The ID (or list of IDs for some types) of the object to delete.
        """
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
                # Alarm sites require both responseSiteId and siteId
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

    This client uses an API Key (created by the Internal Client) to generate
    a short-lived token for authenticated requests.
    """

    def __init__(self, api_key: str, org_short_name: str, region: str = "api"):
        """
        Args:
            api_key: The granular API key string.
            org_short_name: The organization's short identifier.
            region: The API region (default "api").
        """
        self.api_key = api_key
        self.org_short_name = org_short_name
        self.region = region

        # Initialize session FIRST so it can be used by _generate_api_token
        self.session = requests.Session()

        # Configure automatic retries for robust network handling
        # Retries on 429 (Too Many Requests) and 5xx (Server Errors)
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
        This token is required for the 'x-verkada-auth' header in public API calls.
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
        """
        Fetches objects via the External API.

        Args:
            categories: Type of object (cameras, guest_sites, users).
        """
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

        # Handle edge case where API returns 400 if no objects exist (e.g. no cameras)
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

    def get_guest_visits(
        self, site_id: str, start_time: int, end_time: int
    ) -> List[Dict[str, Any]]:
        """
        Fetches a list of guest visits for a given site within a time range.

        Args:
            site_id: The ID of the site to fetch guest visits for.
            start_time: The start time of the time range in UNIX format.
            end_time: The end time of the time range in UNIX format.
        """
        url = f"https://api.verkada.com/guest/v1/visits?site_id={site_id}&start_time={start_time}&end_time={end_time}&page_size=100"
        headers = {"accept": "application/json", "x-verkada-auth": self.api_token}

        def mapping_func(x):
            guest_data = x.get("guest", {})
            full_name = guest_data.get("full_name", "")
            email = guest_data.get("email")

            # Initialize defaults
            first_name = full_name
            last_name = full_name

            if full_name:
                # Check if there is at least one space to split by
                if " " in full_name:
                    # rsplit(' ', 1) splits the string starting from the right, max 1 split
                    # "Alpha Beta Gamma" -> ["Alpha Beta", "Gamma"]
                    first_name, last_name = full_name.rsplit(" ", 1)
                else:
                    # No spaces found: First and Last name are the same
                    first_name = full_name
                    last_name = full_name

            return {
                "first_name": first_name,
                "last_name": last_name,
                "email": email,
            }

        try:
            response = self.session.get(url, headers=headers)
            response.raise_for_status()
            data = response.json()
            results = [mapping_func(item) for item in data.get("visits", [])]
            return results
        except HTTPError as e:
            logger.error(f"Failed to retrieve Guest visits for: {site_id}: {e}")
            return []
        except Exception as e:
            logger.error(
                f"Unexpected error retrieving Guest visits for: {site_id}: {e}"
            )
            return []

    def get_users(
        self, exclude_user_id: Optional[str] = None, exclude_email: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Fetches a list of users, with optional filtering to prevent deleting self.

        Args:
            exclude_user_id: The ID of a user to filter out (usually the admin running the script).
            exclude_email: An email address to filter out.
        """
        users = self.get_object("users")

        # Filter by ID
        if exclude_user_id is not None:
            initial_count = len(users)
            clean_exclude_id = str(exclude_user_id).strip()
            users = [
                u for u in users if str(u.get("id", "")).strip() != clean_exclude_id
            ]
            if len(users) < initial_count:
                logger.info(f"Filtered out user ({exclude_user_id}) from inventory.")
                pass

        # Filter by Email
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

    def delete_user(self, user_id: str) -> bool:
        """
        Deletes a user from the organization via Public API.
        """
        url = "https://api.verkada.com/core/v1/user"
        headers = {"accept": "application/json", "x-verkada-auth": self.api_token}
        params = {"user_id": user_id}
        try:
            response = self.session.delete(url, headers=headers, params=params)
            response.raise_for_status()
            logger.info(f"Deleted User: {user_id}")
            return True
        except HTTPError as e:
            logger.error(f"Failed to delete user: {user_id}: {e}")
            return False
        except Exception as e:
            logger.error(f"Unexpected error deleting user: {user_id}: {e}")
            return False
