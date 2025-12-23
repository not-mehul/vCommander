import logging
from datetime import datetime, timedelta
from typing import Any, Callable, Dict, List, Optional, Union

import requests
from requests.adapters import HTTPAdapter
from requests.exceptions import HTTPError, JSONDecodeError
from requests.models import Response
from urllib3.util.retry import Retry

from verkada_utilities import get_env_var

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
internal_client.create_external_api_key()
internal_client.set_access_system_admin()
