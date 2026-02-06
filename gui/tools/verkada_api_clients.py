import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Union

import requests
from requests.adapters import HTTPAdapter
from requests.exceptions import HTTPError, JSONDecodeError
from requests.models import Response
from urllib3.util.retry import Retry

# Initialize logger for this module
logger = logging.getLogger(__name__)


class MFARequiredError(Exception):
    """
    Raised when the API requires 2FA/MFA to complete login.

    This exception is used by the GUI to detect when to switch to the MFA
    entry screen. It includes optional SMS contact info if a code was sent.
    """

    def __init__(self, message, sms_contact=None):
        super().__init__(message)
        self.sms_contact = sms_contact


class VerkadaInternalAPIClient:
    """
    A client to interact with the internal Verkada Provisioning and Response APIs.

    This client simulates the behavior of the web interface (Command) by using
    user credentials (email/password) to obtain a session cookie and CSRF token.
    It handles 2FA/MFA if required by the organization.

    The "internal" APIs are the same endpoints used by the Verkada web interface,
    which require cookie-based authentication rather than API keys.
    """

    # Base URL for the provisioning API (used for login and org management)
    BASE_URL_PROVISION = "https://vprovision.command.verkada.com/__v/"

    def __init__(self, email: str, password: str, org_short_name: str, shard: str):
        """
        Initializes the internal client with credentials.

        Args:
            email: Admin email address for authentication.
            password: Admin password for authentication.
            org_short_name: The short identifier for the organization (e.g., "myorg").
                           This is the subdomain used in Command URLs.
            shard: The specific backend shard to connect to (e.g., "prod1").
                   Verkada uses sharding to distribute load across data centers.
        """
        # Store authentication credentials
        self.email = email
        self.password = password
        self.org_short_name = org_short_name
        self.shard = shard

        # Initialize a persistent session to maintain cookies across requests
        # This is crucial for internal API authentication which relies on cookies
        self.session = requests.Session()

        # Storage for auth tokens (CSRF, User ID, Org ID, etc.) populated after login
        self.auth_data: Optional[Dict[str, str]] = None

        # Store pending login state for MFA verification
        self._pending_login_url = None
        self._pending_payload = None

    @property
    def user_id(self) -> Optional[str]:
        """
        Returns the authenticated User ID as a string.

        Returns:
            The user ID if authenticated, None otherwise.
        """
        if self.auth_data:
            return self.auth_data.get("adminUserId")
        return None

    @property
    def org_id(self) -> Optional[str]:
        """
        Returns the Organization ID as a string.

        Returns:
            The organization ID if authenticated, None otherwise.
        """
        if self.auth_data:
            return self.auth_data.get("organizationId")
        return None

    def _get_headers(self) -> Dict[str, str]:
        """
        Constructs the specific HTTP headers required for internal API calls.

        These headers mimic a browser session. Crucially, it includes the
        'Cookie' string and custom 'x-verkada-*' headers derived from auth data.
        Without these headers, internal API requests will be rejected.

        Returns:
            Dictionary of HTTP headers for authenticated requests.
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
            # They must match the organization's Command URL
            "origin": f"https://{self.org_short_name}.command.verkada.com",
            "referer": f"https://{self.org_short_name}.command.verkada.com/",
        }

    def _parse_login_response(self, json_data: Dict[str, Any]) -> Dict[str, str]:
        """
        Extracts critical session data from a successful login API response.

        It manually constructs the cookie string expected by subsequent requests.
        The cookie string format is specific to Verkada's internal API.

        Args:
            json_data: The JSON response from the login API.

        Returns:
            Dictionary containing extracted auth data (CSRF token, org ID, etc.).

        Raises:
            ValueError: If expected keys are missing from the response.
        """
        try:
            # Extract key fields from the login response
            csrf_token = str(json_data["csrfToken"])
            user_token = str(json_data["userToken"])
            organization_id = str(json_data["organizationId"])
            admin_user_id = str(json_data["userId"])

            # Manually constructing the cookie string required for internal APIs
            # This combines the user token, org ID, user ID, and CSRF token.
            # Format: auth={user_token}; org={org_id}; usr={user_id}; token={csrf_token};
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
        1. Sends POST request with credentials to the login endpoint.
        2. Checks if 2FA (MFA) is required (HTTP 400 with specific message).
        3. If 2FA is required, raises MFARequiredError to signal the GUI.
        4. Parses the successful response to store session data in self.auth_data.

        Raises:
            MFARequiredError: If 2FA is required (contains SMS contact info).
            ConnectionError: If login fails for other reasons.
        """
        # Construct the login URL using the organization's short name
        login_url = f"{self.BASE_URL_PROVISION}{self.org_short_name}/user/login"

        # Prepare the login payload with credentials
        payload = {
            "email": self.email,
            "org_short_name": self.org_short_name,
            "termsAcked": True,  # User has accepted terms of service
            "password": self.password,
            "shard": self.shard,
            "subdomain": True,
        }

        logger.info(f"Logging in as {self.email}...")
        response = Response()

        try:
            # Send the login request
            response = self.session.post(login_url, json=payload)
            data = response.json()
        except JSONDecodeError:
            # Handle case where API returns non-JSON (usually an error page)
            logger.error(
                f"Login failed: API returned non-JSON response. {response.text}"
            )
            raise

        # 1. Success Scenario (No MFA required)
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
                # Store state for Step 2 (MFA verification)
                self._pending_login_url = login_url
                self._pending_payload = payload

                # Extract SMS contact info if available (for UI display)
                sms_contact = data.get("data", {}).get("smsSent")

                # Signal the GUI to switch to MFA screen
                raise MFARequiredError("MFA Required", sms_contact)

        # 3. Failure Scenario - credentials incorrect or other error
        raise ConnectionError(
            f"Login failed with status {response.status_code}: {response.text}"
        )

    def verify_mfa(self, otp_code: str) -> None:
        """
        Verifies a 2FA/MFA code to complete the login process.

        This method should be called after login() raises MFARequiredError.
        It uses the stored pending login state to complete authentication.

        Args:
            otp_code: The one-time password/code entered by the user.

        Raises:
            ValueError: If no pending login attempt exists or code is invalid.
            ConnectionError: If MFA verification fails for other reasons.
        """
        if not self._pending_payload or not self._pending_login_url:
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

                # Clear pending data to prevent reuse
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

    def create_external_api_key(self) -> str:
        """
        Generates a temporary External API Key.

        This key is required to initialize the `VerkadaExternalAPIClient`.
        It creates a key with specific read/write permissions for Decommissioning.
        The key is set to expire in 1 hour for security.

        Returns:
            The generated API key string.

        Raises:
            PermissionError: If not authenticated.
            SystemExit: If API key limit (10) is exceeded or other errors occur.
        """
        if not self.auth_data:
            raise PermissionError("Not authenticated. Please call login() first.")

        # URL for the granular API key creation endpoint
        url = f"https://apiadmin.command.verkada.com/__v/{self.org_short_name}/admin/orgs/{self.org_id}/v2/granular_apikeys"

        # Prepare payload with key name, expiration, and permissions
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
            # Special handling for API key limit exceeded
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
        delete certain access control hardware. This grants the user:
        - ACCESS_CONTROL_SYSTEM_ADMIN role
        - ACCESS_CONTROL_USER_ADMIN role

        Raises:
            PermissionError: If not authenticated.
        """
        if not self.auth_data:
            raise PermissionError("Not authenticated. Please call login() first.")

        url = f"https://vcerberus.command.verkada.com/__v/{self.org_short_name}/access/v2/user/roles/modify"

        # Grant both system admin and user admin roles to the current user
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
            logger.info("Escalated user to Access System Admin")
        except (HTTPError, JSONDecodeError) as e:
            logger.error(f"Failed to escalate to Access System Admin: {e}")

    def enable_global_site_admin(self):
        """
        Updates the organization's Global Site Admin toggle to True.

        Ensures that org admins are site admins for all sites in the organization.
        This is necessary to have permission to modify/delete all sites.

        Raises:
            PermissionError: If not authenticated.
        """
        if not self.auth_data:
            raise PermissionError("Not authenticated. Please call login() first.")

        url = f"https://vprovision.command.verkada.com/__v/{self.org_short_name}/org/settings/update"
        payload = {"organizationId": self.org_id, "settings": {"globalSiteAdmin": True}}
        headers = self._get_headers()
        try:
            response = self.session.post(url, json=payload, headers=headers)
            response.raise_for_status()
            logger.info("Enabled Global Site Admin")
        except (HTTPError, JSONDecodeError) as e:
            logger.error(f"Failed to enable Global Site Admin: {e}")

    def invite_user(self, first_name: str, last_name: str, email: str, org_admin: bool):
        """
        Invites a new user to the organization.

        Sends an invitation email to the specified address with a link to
        join the organization.

        Args:
            first_name: User's first name.
            last_name: User's last name.
            email: User's email address (invitation sent here).
            org_admin: Whether to grant org admin privileges to the user.

        Raises:
            PermissionError: If not authenticated.
        """
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
            response.raise_for_status()
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

        Uses pattern matching to determine the correct API endpoint, request method,
        and data mapping function for each device type. This centralizes device
        fetching logic in a single method.

        Args:
            categories: The type of object to fetch (e.g., 'intercoms', 'sensors',
                       'access_controllers', 'alarm_sites', etc.).

        Returns:
            A list of dictionaries, where each dict represents a device
            and contains standardized keys: 'id', 'name', 'serial_number'.
        """
        if not self.auth_data:
            raise PermissionError("Not authenticated. Please call login() first.")

        # Payload for POST requests (some endpoints require POST with body)
        payload = None

        # Configure request details based on the category using pattern matching
        # Each case defines: object_type, request_type, subdomain, path, and mapping_func
        match categories:
            case "intercoms":
                object_type = "intercoms"
                request_type = "GET"
                subdomain = "api"
                path = f"vinter/v1/user/organization/{self.org_id}/device"

                # Standardize output to common format
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
                # Raise error for unknown device types
                raise ValueError(f"Unknown device type: {categories}")

        # Construct the full URL with subdomain and path
        url = (
            f"https://{subdomain}.command.verkada.com/__v/{self.org_short_name}/{path}"
        )
        headers = self._get_headers()
        logger.info(f"Finding {categories}...")

        # Execute the HTTP request (GET or POST based on device type)
        if request_type == "POST":
            response = self.session.post(url, headers=headers, json=payload)
        else:
            response = self.session.get(url, headers=headers)

        try:
            response.raise_for_status()
            data = response.json()
            # Apply mapping function to normalize data structure for each item
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

        Similar to get_object(), uses pattern matching to determine the correct
        API endpoint and request method for each device type. Different device
        types require different HTTP methods (DELETE vs POST).

        Args:
            categories: The type of object to delete.
            object_id: The ID (or list of IDs for some types) of the object to delete.

        Returns:
            True if deletion succeeded, False otherwise.
        """
        # Payload for POST-based deletion requests
        payload = None

        # Pattern matching for each device type's deletion endpoint
        match categories:
            case "intercoms":
                request_type = "DELETE"
                subdomain = "api"
                path = f"vinter/v1/user/async/organization/{self.org_id}/device/{object_id}"

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

        # Construct full URL
        url = (
            f"https://{subdomain}.command.verkada.com/__v/{self.org_short_name}/{path}"
        )
        headers = self._get_headers()
        logger.info(f"Removing {categories} - {object_id}")

        # Execute the appropriate HTTP method
        if request_type == "POST":
            response = self.session.post(url, headers=headers, json=payload)
        else:
            response = self.session.delete(url, headers=headers)

        try:
            response.raise_for_status()
            # Check for success status codes
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
    a short-lived token for authenticated requests. The external API is the
    officially documented API for third-party integrations.
    """

    def __init__(self, api_key: str, org_short_name: str, region: str = "api"):
        """
        Initializes the external API client.

        Args:
            api_key: The granular API key string (created via internal client).
            org_short_name: The organization's short identifier.
            region: The API region (default "api" for US).
        """
        self.api_key = api_key
        self.org_short_name = org_short_name
        self.region = region

        # Initialize session FIRST so it can be used by _generate_api_token
        self.session = requests.Session()

        # Configure automatic retries for robust network handling
        # Retries on 429 (Too Many Requests) and 5xx (Server Errors)
        # Uses exponential backoff to avoid overwhelming the API
        retries = Retry(
            total=4,  # Maximum retry attempts
            backoff_factor=0.5,  # Wait 0.5s, 1s, 2s, 4s between retries
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
        Tokens are typically valid for a short period (e.g., 1 hour).

        Returns:
            The generated API token string.

        Raises:
            HTTPError: If token generation fails.
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

        Uses pattern matching to handle different object types with their
        specific endpoints and data mapping functions.

        Args:
            categories: Type of object (cameras, guest_sites, users).

        Returns:
            List of objects with standardized fields.
        """
        # Some APIs return 400 when no objects exist - this signature helps detect that
        error_signature = None

        match categories:
            case "cameras":
                object_type = "cameras"
                path = "cameras/v1/devices"
                # This string appears in 400 error when no cameras exist
                error_signature = "must include cameras"

                def mapping_func(x):
                    return {
                        "id": x["camera_id"],
                        "name": x["name"],
                        "serial": x["serial"],
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

        # Construct URL and headers for external API
        url = f"https://{self.region}.verkada.com/{path}"
        headers = {"accept": "application/json", "x-verkada-auth": self.api_token}
        params = {"page_size": 200}  # Request up to 200 items per page
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
            # Apply mapping to normalize data structure
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

        This is used to retrieve visitor information for importing as users.

        Args:
            site_id: The ID of the site to fetch guest visits for.
            start_time: The start time of the time range in UNIX timestamp format.
            end_time: The end time of the time range in UNIX timestamp format.

        Returns:
            List of guest visit records with first_name, last_name, and email.
        """
        # Build URL with query parameters for site and time range
        url = f"https://api.verkada.com/guest/v1/visits?site_id={site_id}&start_time={start_time}&end_time={end_time}&page_size=100"
        headers = {"accept": "application/json", "x-verkada-auth": self.api_token}

        def mapping_func(x):
            """Extract and split guest name into first and last name."""
            guest_data = x.get("guest", {})
            full_name = guest_data.get("full_name", "")
            email = guest_data.get("email")

            # Initialize defaults - use full name for both if can't split
            first_name = full_name
            last_name = full_name

            if full_name:
                # Check if there is at least one space to split by
                if " " in full_name:
                    # rsplit(' ', 1) splits the string starting from the right, max 1 split
                    # Example: "Alpha Beta Gamma" -> ["Alpha Beta", "Gamma"]
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

        This is used during decommissioning to get the list of users to delete,
        while optionally excluding the admin running the script to prevent
        accidental self-deletion.

        Args:
            exclude_user_id: The ID of a user to filter out (usually the admin).
            exclude_email: An email address to filter out.

        Returns:
            Filtered list of users.
        """
        # Get all users from the API
        users = self.get_object("users")

        # Filter by ID if specified
        if exclude_user_id is not None:
            initial_count = len(users)
            clean_exclude_id = str(exclude_user_id).strip()
            users = [
                u for u in users if str(u.get("id", "")).strip() != clean_exclude_id
            ]
            if len(users) < initial_count:
                logger.info(f"Filtered out user ({exclude_user_id}) from inventory.")

        # Filter by Email if specified
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

        return users

    def delete_user(self, user_id: str) -> bool:
        """
        Deletes a user from the organization via Public API.

        Permanently removes the user and revokes their access to the organization.
        This action cannot be undone.

        Args:
            user_id: The unique identifier of the user to delete.

        Returns:
            True if deletion succeeded, False otherwise.
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
