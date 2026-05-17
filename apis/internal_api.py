import time
from typing import Any, NamedTuple, Optional

import requests
from requests.exceptions import JSONDecodeError, RequestException

from constants import API_NAME, DEV_SKIP_LOGIN
from utils.logger import log_api_call

# ----------------------------------------------------------------------
# Address types
# ----------------------------------------------------------------------


class Address(NamedTuple):
    """Simple geo location used by cameras, connectors, and buildings."""

    label: str
    latitude: float
    longitude: float


class AlarmAddress(NamedTuple):
    """Full structured address used by alarm response sites."""

    city: str
    country: str
    latitude: float
    longitude: float
    state: str
    street1: str
    timezone: str
    zipcode: str


class GuestAddress(NamedTuple):
    """Address used by guest/visitor management sites."""

    full_address: str
    latitude: float
    longitude: float
    country_code: str


class MFARequiredError(Exception):
    """
    Raised when the API requires 2FA to complete login.
    sms_contact contains the last digits of the SMS-receiving number, if provided.
    """

    def __init__(self, message: str = "MFA Required", sms_contact: str | None = None):
        super().__init__(message)
        self.sms_contact = sms_contact


class VerkadaInternalAPIClient:
    """
    Client for the Verkada internal (Command) API.

    Uses cookie-based session auth (same flow as the Command web interface).
    login() handles the initial credential check; if 2FA is required it raises
    MFARequiredError so the GUI can prompt for the OTP.  verify_mfa() completes
    the flow using the same endpoint with the otp field added.
    """

    BASE_URL_PROVISION = "https://vprovision.command.verkada.com/__v/"
    DEFAULT_TIMEOUT = 30  # seconds — applied to every HTTP request

    def __init__(
        self, email: str, password: str, org_short_name: str, shard: str = "prod1"
    ):
        self.email = email
        self.password = password
        self.org_short_name = org_short_name
        self.shard = shard

        # Persistent session keeps cookies alive across requests
        self.session = requests.Session()

        # Populated by _parse_login_response() after successful auth
        self.auth_data: dict[str, str] | None = None

        # Saved during login() so verify_mfa() can replay the same request
        self._pending_login_url: str | None = None
        self._pending_payload: dict | None = None

    @property
    def user_id(self) -> str | None:
        return self.auth_data.get("adminUserId") if self.auth_data else None

    @property
    def org_id(self) -> str | None:
        return self.auth_data.get("organizationId") if self.auth_data else None

    def _get_headers(self) -> dict[str, str]:
        """
        Build the CSRF + identity headers required by all internal endpoints.

        Cookies are NOT set here — they live on the session jar (set by
        _parse_login_response). Mixing a manual Cookie header with the session
        jar can cause merge surprises if the server ever issues Set-Cookie
        for the same names.
        """
        if not self.auth_data:
            return {}
        return {
            "Accept": "*/*",
            "x-verkada-organization-id": self.auth_data.get("organizationId", ""),
            "x-verkada-token": self.auth_data.get("csrfToken", ""),
            "x-verkada-user-id": self.auth_data.get("adminUserId", ""),
            "origin": f"https://{self.org_short_name}.command.verkada.com",
            "referer": f"https://{self.org_short_name}.command.verkada.com/",
        }

    def _request(
        self,
        method: str,
        url: str,
        *,
        json: dict | None = None,
        error_context: str,
    ) -> dict:
        """
        Execute an authenticated request and return parsed JSON data.

        Centralizes the auth check, request execution, JSON-decode handling,
        empty-body tolerance, and error-message extraction that every
        authenticated endpoint in this client needs.

        Args:
            method: HTTP verb ('GET', 'POST', 'DELETE', etc.).
            url: Full request URL.
            json: Optional JSON body to send.
            error_context: Human-readable prefix used in raised
                ConnectionError messages, e.g. "Failed to create site 'HQ'".
                The server's error message (or response text) is appended.

        Returns:
            The parsed JSON response body, or an empty dict if the response
            has no body or is unparseable on a 2xx response.

        Raises:
            PermissionError: If not authenticated.
            ConnectionError: On any HTTP, transport, or decode failure. The
                message starts with error_context.
        """
        if not self.auth_data:
            raise PermissionError("Not authenticated. Please call login() first.")

        try:
            response = self.session.request(
                method,
                url,
                json=json,
                headers=self._get_headers(),
                timeout=self.DEFAULT_TIMEOUT,
            )
        except RequestException as e:
            raise ConnectionError(f"{error_context}: {e}")

        # Tolerate empty bodies (some DELETEs and a few POSTs return nothing).
        if response.content:
            try:
                data = response.json()
            except JSONDecodeError:
                if not response.ok:
                    raise ConnectionError(
                        f"{error_context}: {response.text or 'non-JSON response.'}"
                    )
                # 2xx with non-JSON body — let caller see {} rather than crash;
                # if caller needs a specific field it will surface its own error.
                data = {}
        else:
            data = {}

        if isinstance(data, list):
            data = {"items": list(data)}
        data_dict: dict = data

        if not response.ok:
            msg = (
                data_dict.get("message", response.text) if data_dict else response.text
            )
            raise ConnectionError(f"{error_context}: {msg or 'unknown error'}")

        # Stash status code on the data dict so callers can log it without
        # holding onto the Response object. Use a key unlikely to collide.
        data_dict.setdefault("__status_code__", response.status_code)
        return data_dict

    @staticmethod
    def _status(data: dict) -> str:
        """Pull the helper-stashed HTTP status code as a string for logging."""
        return str(data.get("__status_code__", ""))

    def _parse_login_response(self, json_data: dict[str, Any]) -> dict[str, str]:
        """
        Extract session tokens from a successful login response and install them
        on the requests session as cookies. Subsequent internal API calls then
        get the cookies automatically from the session jar.
        """
        try:
            csrf_token = str(json_data["csrfToken"])
            user_token = str(json_data["userToken"])
            organization_id = str(json_data["organizationId"])
            admin_user_id = str(json_data["userId"])

            # Install cookies on the session jar (single source of truth).
            self.session.cookies.set("auth", user_token)
            self.session.cookies.set("org", organization_id)
            self.session.cookies.set("usr", admin_user_id)
            self.session.cookies.set("token", csrf_token)

            log_api_call(
                "POST",
                f"{self.org_short_name}/user/login",
                f'{{"email": "{self.email}"}}',
                "200",
                f'{{"userId": "{admin_user_id}", "organizationId": "{organization_id}"}}',
            )

            return {
                "csrfToken": csrf_token,
                "organizationId": organization_id,
                "adminUserId": admin_user_id,
            }
        except KeyError as e:
            raise ValueError(f"Unexpected login response format, missing key: {e}")

    def login(self) -> None:
        """
        Authenticate with the Verkada Provisioning API.

        Successful (no MFA):  response has loggedIn=true  → auth_data populated
        MFA required:         response has "2FA invalid"  → MFARequiredError raised
        Bad credentials:      response has "Wrong user"   → ConnectionError raised

        The pending URL and payload are stored so verify_mfa() can reuse them.
        """
        if DEV_SKIP_LOGIN:
            self.auth_data = {
                "csrfToken": "dev-csrf",
                "organizationId": "dev-org-id",
                "adminUserId": "dev-user-id",
            }
            self.session.cookies.set("auth", "dev")
            self.session.cookies.set("org", "dev-org-id")
            self.session.cookies.set("usr", "dev-user-id")
            self.session.cookies.set("token", "dev-csrf")
            return

        login_url = f"{self.BASE_URL_PROVISION}{self.org_short_name}/user/login"

        payload = {
            "email": self.email,
            "orgShortName": self.org_short_name,
            "termsAcked": False,
            "password": self.password,
            "loginMethod": "password",
            "shard": self.shard,
            "subdomain": True,
        }

        # login() runs before auth_data is populated, so it cannot use
        # _request (which enforces authentication). Inline by design.
        try:
            response = self.session.post(
                login_url, json=payload, timeout=self.DEFAULT_TIMEOUT
            )
            data = response.json()
        except JSONDecodeError:
            log_api_call(
                "POST",
                f"{self.org_short_name}/user/login",
                f'{{"email": "{self.email}"}}',
                "200",
                "non-JSON response",
            )
            raise ConnectionError("Login failed: server returned a non-JSON response.")

        msg = data.get("message", "")

        # ── Success (no MFA) ──────────────────────────────────────────
        if response.status_code == 200 and data.get("loggedIn"):
            self.auth_data = self._parse_login_response(data)
            return

        # ── MFA required ──────────────────────────────────────────────
        # Server returns HTTP 200 with a "2FA invalid for {userId}" message
        # when credentials are correct but the org enforces 2FA.
        if "2FA invalid" in msg:
            self._pending_login_url = login_url
            self._pending_payload = payload
            sms_contact = data.get("data", {}).get("smsSent")
            log_api_call(
                "POST",
                f"{self.org_short_name}/user/login",
                f'{{"email": "{self.email}"}}',
                "200 (MFA)",
                msg,
            )
            raise MFARequiredError("MFA Required", sms_contact)

        # ── Credentials failure or unexpected error ───────────────────
        log_api_call(
            "POST",
            f"{self.org_short_name}/user/login",
            f'{{"email": "{self.email}"}}',
            str(response.status_code),
            msg,
        )
        raise ConnectionError(f"Login failed: {msg or response.text}")

    def verify_mfa(self, otp_code: str) -> None:
        """
        Complete login by submitting the 2FA OTP code.

        Must be called after login() has raised MFARequiredError.  Replays
        the original login payload with the otp field added.

        Success:  loggedIn=true → auth_data populated, pending state cleared
        Failure:  "2FA invalid" in message → ValueError (wrong code)
        """
        if not self._pending_payload or not self._pending_login_url:
            raise ValueError("No pending login. Call login() first.")

        mfa_payload = self._pending_payload.copy()
        mfa_payload["otp"] = otp_code

        # Like login(), runs pre-auth and uses the bare session.
        try:
            response = self.session.post(
                self._pending_login_url,
                json=mfa_payload,
                timeout=self.DEFAULT_TIMEOUT,
            )
            data = response.json()
        except JSONDecodeError:
            raise ConnectionError(
                "MFA verification failed: server returned a non-JSON response."
            )

        msg = data.get("message", "")

        # ── Success ───────────────────────────────────────────────────
        if response.status_code == 200 and data.get("loggedIn"):
            self.auth_data = self._parse_login_response(data)
            self._pending_login_url = None
            self._pending_payload = None
            return

        # ── Wrong code ────────────────────────────────────────────────
        # Server re-returns the same "2FA invalid" response on a bad OTP
        if "2FA invalid" in msg:
            log_api_call(
                "POST",
                f"{self.org_short_name}/user/login (MFA)",
                '{"otp": "***"}',
                "200 (bad OTP)",
                msg,
            )
            raise ValueError("Incorrect 2FA code. Please try again.")

        log_api_call(
            "POST",
            f"{self.org_short_name}/user/login (MFA)",
            '{"otp": "***"}',
            str(response.status_code),
            msg,
        )
        raise ConnectionError(f"MFA verification failed: {msg or response.text}")

    def create_site(self, site_name: str) -> str:
        """
        Creates a camera group (site) in the organization.

        Returns:
            The site ID string on success.

        Raises:
            PermissionError: If not authenticated.
            ConnectionError: If the API call fails or the response contains no site.
        """
        url = f"https://vprovision.command.verkada.com/__v/{self.org_short_name}/org/camera_group/create"
        data = self._request(
            "POST",
            url,
            json={"organizationId": self.org_id, "name": site_name},
            error_context=f"Failed to create site '{site_name}'",
        )

        camera_groups = data.get("cameraGroups", [])
        if not camera_groups:
            raise ConnectionError(
                f"Failed to create site '{site_name}': no site data in response."
            )

        site_id = camera_groups[0].get("cameraGroupId")
        if not site_id:
            raise ConnectionError(
                f"Failed to create site '{site_name}': no cameraGroupId in response."
            )

        log_api_call(
            "POST",
            f"{self.org_short_name}/org/camera_group/create",
            f'{{"name": "{site_name}"}}',
            self._status(data),
            f'{{"cameraGroupId": "{site_id}"}}',
        )
        return site_id

    def add_supporting_user(
        self, first_name: str, last_name: str, email: str, role: str
    ) -> dict:
        """
        Invites a user to the organization via the provisioning API.

        Maps the role string to org_admin: "Org Admin" → True, everything else → False.

        Returns a dict with user_id, email, and name on success. user_id and
        name are None if the response did not include user details.

        Raises ValueError if the user is already in the org.
        Raises ConnectionError for other API failures.
        """
        if not self.auth_data:
            raise PermissionError("Not authenticated. Please call login() first.")

        url = f"https://vprovision.command.verkada.com/__v/{self.org_short_name}/org/invite"
        org_admin = role == "Org Admin"
        payload = {
            "organizationId": self.org_id,
            "email": email,
            "orgAdmin": org_admin,
            "commandUserAdmin": False,
            "firstName": first_name,
            "lastName": last_name,
            "inviteFf": True,
        }

        try:
            response = self.session.post(
                url,
                json=payload,
                headers=self._get_headers(),
                timeout=self.DEFAULT_TIMEOUT,
            )
            data = response.json()
        except JSONDecodeError:
            raise ConnectionError(f"Invite failed for {email}: non-JSON response.")
        except RequestException as e:
            raise ConnectionError(f"Invite failed for {email}: {e}")

        if not response.ok:
            err_id = data.get("id", "")
            msg = data.get("message", response.text)
            if err_id == "cannot_invite_existing":
                raise ValueError(f"User already exists in this org: {email}")
            raise ConnectionError(f"Invite failed for {email}: {msg}")

        invitation_id = (data.get("orgInvitation") or [{}])[0].get(
            "orgInvitationId", ""
        )
        log_api_call(
            "POST",
            f"{self.org_short_name}/org/invite",
            f'{{"email": "{email}", "firstName": "{first_name}", "lastName": "{last_name}"}}',
            str(response.status_code),
            f'{{"orgInvitationId": "{invitation_id}"}}',
        )

        users = data.get("users") or []
        if users:
            u = users[0]
            return {
                "user_id": u.get("userId"),
                "email": u.get("email"),
                "name": u.get("name"),
            }
        # Always return the same shape so callers can rely on .get('user_id').
        return {"user_id": None, "email": email, "name": None}

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
            ConnectionError: If the API key limit (10) is exceeded or other errors occur.
        """
        if not self.auth_data:
            raise PermissionError("Not authenticated. Please call login() first.")

        url = f"https://apiadmin.command.verkada.com/__v/{self.org_short_name}/admin/orgs/{self.org_id}/v2/granular_apikeys"
        payload = {
            "api_key_name": API_NAME + str(int(time.time())),
            "expires_at": int(time.time() + 3600),
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

        try:
            response = self.session.post(
                url,
                json=payload,
                headers=self._get_headers(),
                timeout=self.DEFAULT_TIMEOUT,
            )
            data = response.json()
        except JSONDecodeError:
            raise ConnectionError(
                "Failed to create external API key: non-JSON response."
            )
        except RequestException as e:
            raise ConnectionError(f"Failed to create external API key: {e}")

        if not response.ok:
            msg = data.get("message", response.text)
            if response.status_code == 400 and msg == "Would exceed 10 api keys limit":
                raise ConnectionError(
                    "Failed to create external API key: exceeded 10 API keys limit."
                )
            raise ConnectionError(f"Failed to create external API key: {msg}")

        api_key = data.get("apiKey", "")
        log_api_call(
            "POST",
            f"{self.org_short_name}/admin/orgs/{self.org_id}/v2/granular_apikeys",
            f'{{"api_key_name": "{payload["api_key_name"]}"}}',
            str(response.status_code),
            f'{{"apiKey": "{api_key}"}}',
        )
        return api_key

    def set_access_system_admin(self) -> None:
        """
        Escalates the current user's privileges to Access System Admin.

        Required because standard admin privileges might not be enough to
        delete certain access control hardware. This grants the user:
        - ACCESS_CONTROL_SYSTEM_ADMIN role
        - ACCESS_CONTROL_USER_ADMIN role

        Raises:
            PermissionError: If not authenticated.
            ConnectionError: If the API call fails.
        """
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

        data = self._request(
            "POST",
            url,
            json=payload,
            error_context="Failed to set Access System Admin",
        )

        log_api_call(
            "POST",
            f"{self.org_short_name}/access/v2/user/roles/modify",
            f'{{"granteeId": "{self.user_id}", "roles": ["ACCESS_CONTROL_SYSTEM_ADMIN", "ACCESS_CONTROL_USER_ADMIN"]}}',
            self._status(data),
            "{}",
        )

    def _set_global_site_admin(self, enabled: bool) -> dict:
        """Internal helper: toggle the globalSiteAdmin org setting."""
        action = "enable" if enabled else "disable"
        url = f"https://vprovision.command.verkada.com/__v/{self.org_short_name}/org/settings/update"
        payload = {
            "organizationId": self.org_id,
            "settings": {"globalSiteAdmin": enabled},
        }

        data = self._request(
            "POST",
            url,
            json=payload,
            error_context=f"Failed to {action} Global Site Admin",
        )

        log_api_call(
            "POST",
            f"{self.org_short_name}/org/settings/update",
            f'{{"organizationId": "{self.org_id}", "settings": {{"globalSiteAdmin": {str(enabled).lower()}}}}}',
            self._status(data),
            str(data),
        )
        return data

    def enable_global_site_admin(self) -> dict:
        """
        Enables the Global Site Admin org setting.

        When enabled, org admins implicitly inherit access to all sites in
        the organization without explicit per-site grants.

        Raises:
            PermissionError: If not authenticated.
            ConnectionError: If the API call fails.
        """
        return self._set_global_site_admin(True)

    def disable_global_site_admin(self) -> dict:
        """
        Disables the Global Site Admin org setting.

        After disabling, org admins must be explicitly granted access to
        each site they need to manage.

        Raises:
            PermissionError: If not authenticated.
            ConnectionError: If the API call fails.
        """
        return self._set_global_site_admin(False)

    def _enable_org_feature(
        self,
        agreement_key: str,
        feature_flags: dict[str, bool],
        feature_label: str,
    ) -> None:
        """
        Internal helper: sign an org agreement and enable a set of feature flags.

        Both steps must succeed. If the agreement step fails, the feature flags
        are NOT touched. If the feature flag step fails, the agreement remains
        signed (this is acceptable — agreements are idempotent).

        Args:
            agreement_key: e.g. 'CV_ANALYTICS' or 'LPR'.
            feature_flags: Dict of feature flag name → bool to set on the org.
            feature_label: Human-readable label used in error messages.
        """
        # Step 1: Sign the agreement
        url_agree = f"https://vcorgi.command.verkada.com/__v/{self.org_short_name}/{self.org_id}/sign_agreement"
        agree_data = self._request(
            "POST",
            url_agree,
            json={"agreementKey": agreement_key, "userEmail": self.email},
            error_context=(
                f"Failed to enable {feature_label} "
                f"(step 1: sign {agreement_key} agreement)"
            ),
        )
        log_api_call(
            "POST",
            f"{self.org_short_name}/{self.org_id}/sign_agreement",
            f'{{"agreementKey": "{agreement_key}"}}',
            self._status(agree_data),
            "{}",
        )

        # Step 2: Enable feature flags
        url_feat = f"https://vdeviceconfig.command.verkada.com/__v/{self.org_short_name}/user/org/feature/set"
        feat_data = self._request(
            "POST",
            url_feat,
            json={
                "organizationId": self.org_id,
                "params": feature_flags,
                "annotations": {"timestamp": int(time.time()), "userId": self.user_id},
            },
            error_context=f"Failed to enable {feature_label} (step 2: feature flags)",
        )
        log_api_call(
            "POST",
            f"{self.org_short_name}/user/org/feature/set",
            "{}",
            self._status(feat_data),
            "{}",
        )

    def enable_org_analytics(self) -> None:
        """
        Signs the CV_ANALYTICS agreement and enables org-level analytics features
        (face detection, people history, person attributes, POI notifications,
        vehicle history).

        Raises:
            PermissionError: If not authenticated.
            ConnectionError: If either step fails. The error message identifies
                which step (sign agreement / feature flags) failed.
        """
        self._enable_org_feature(
            agreement_key="CV_ANALYTICS",
            feature_flags={
                "face-detection": True,
                "people-history": True,
                "person-attributes": True,
            },
            feature_label="org analytics",
        )

    def enable_lpr_mode(self) -> None:
        """
        Signs the LPR agreement and enables the org-level
        license-plate-recognition feature flag.

        Raises:
            PermissionError: If not authenticated.
            ConnectionError: If either step fails. The error message identifies
                which step (sign agreement / feature flags) failed.
        """
        self._enable_org_feature(
            agreement_key="LPR",
            feature_flags={"license-plate-recognition": True},
            feature_label="LPR mode",
        )

    def _set_camera_features(
        self,
        camera_ids: list[str],
        feature_flags: dict[str, bool],
        feature_label: str,
    ) -> None:
        """Internal helper: set a batch of camera feature flags."""
        url = f"https://vdeviceconfig.command.verkada.com/__v/{self.org_short_name}/user/camera/feature/set"
        data = self._request(
            "POST",
            url,
            json={"cameraIds": camera_ids, "params": feature_flags},
            error_context=f"Failed to enable {feature_label}",
        )
        log_api_call(
            "POST",
            f"{self.org_short_name}/user/camera/feature/set",
            f'{{"cameraIds": {camera_ids}}}',
            self._status(data),
            "{}",
        )

    def enable_camera_analytics(self, camera_ids: list[str]) -> None:
        """
        Enables analytics features (people history, person attributes, face
        detection, live POI alerts, vehicle history) on a list of cameras.

        Args:
            camera_ids: List of camera IDs to enable analytics on.

        Raises:
            PermissionError: If not authenticated.
            ConnectionError: If the API call fails.
        """
        self._set_camera_features(
            camera_ids,
            feature_flags={
                "people-history": True,
                "person-attributes": True,
                "face-detection": True,
            },
            feature_label="camera analytics",
        )

    def enable_camera_lpr(self, camera_ids: list[str]) -> None:
        """
        Enables LPR features on a list of cameras and sets their operating
        mode to 'lpr'.

        Args:
            camera_ids: List of camera IDs to enable LPR on.

        Raises:
            PermissionError: If not authenticated.
            ConnectionError: If either step fails. The error message identifies
                which step (feature flag / operating mode) failed.
        """
        # Step 1: Enable the LPR feature flag
        self._set_camera_features(
            camera_ids,
            feature_flags={"license-plate-recognition": True},
            feature_label="camera LPR (step 1: feature flag)",
        )

        # Step 2: Set operating mode to LPR (one camera at a time — the
        # vprovision/.../config/set endpoint takes a singular cameraId).
        url_provision = f"https://vprovision.command.verkada.com/__v/{self.org_short_name}/user/camera/config/set"

        for camera_id in camera_ids:
            data = self._request(
                "POST",
                url_provision,
                json={
                    "cameraId": camera_id,
                    "params": {"camera-config.operating-mode": "lpr"},
                },
                error_context="Failed to enable camera LPR (step 2: operating mode)",
            )
            log_api_call(
                "POST",
                f"{self.org_short_name}/user/camera/config/set",
                f'{{"cameraId": "{camera_id}"}}',
                self._status(data),
                "{}",
            )

    def link_lpr_camera_to_door(self, door_id: str, lpr_camera_id: str) -> None:
        """
        Links an LPR camera to a door so the camera can trigger door unlocks.

        Performs two steps:
          1. Grants the 'lpr-unlock-enabled' door config param.
          2. Registers the LPR camera as an IO device on the door.

        Args:
            door_id: The ID of the door to configure.
            lpr_camera_id: The ID of the LPR-enabled camera to bind to the door.

        Raises:
            PermissionError: If not authenticated.
            ConnectionError: If either step fails. The error message identifies
                which step (config grant / device_io) failed.
        """
        # Step 1: Grant lpr-unlock-enabled on the door
        config_url = (
            f"https://api.command.verkada.com/__v/{self.org_short_name}/door/config/set"
        )
        config_payload = {
            "doorId": door_id,
            "action": "grant",
            "paramName": "lpr-unlock-enabled",
            "paramValue": "True",
        }
        config_data = self._request(
            "POST",
            config_url,
            json=config_payload,
            error_context=(
                f"Failed to link LPR camera to door '{door_id}' "
                f"(step 1: grant lpr-unlock-enabled)"
            ),
        )
        log_api_call(
            "POST",
            f"{self.org_short_name}/door/config/set",
            f'{{"doorId": "{door_id}", "paramName": "lpr-unlock-enabled"}}',
            self._status(config_data),
            "{}",
        )

        # Step 2: Register the LPR camera as a device_io on the door
        io_url = (
            f"https://api.command.verkada.com/__v/{self.org_short_name}"
            f"/door/{door_id}/device_io"
        )
        io_payload = {
            "configs": {"lprCameraId": lpr_camera_id},
            "ioDeviceTypeName": "lpr-camera",
            "ioSlotType": "lpr-camera",
            "ioSlotIndex": 0,
        }
        io_data = self._request(
            "POST",
            io_url,
            json=io_payload,
            error_context=(
                f"Failed to link LPR camera to door '{door_id}' "
                f"(step 2: register device_io)"
            ),
        )
        log_api_call(
            "POST",
            f"{self.org_short_name}/door/{door_id}/device_io",
            f'{{"lprCameraId": "{lpr_camera_id}"}}',
            self._status(io_data),
            "{}",
        )

    def invite_user(
        self, email: str, first_name: str, last_name: str, role: str = "Org Admin"
    ) -> dict:
        """
        Convenience wrapper around add_supporting_user() with kwargs reordered
        to match the more conventional (email, first, last, role) signature.

        Returns a dict with user_id, email, and name on success.
        Raises ValueError if the user is already in the org.
        Raises ConnectionError for other API failures.
        """
        return self.add_supporting_user(first_name, last_name, email, role)

    def enable_custom_roles(self) -> None:
        """
        Enables custom roles for the organization.

        Raises:
            PermissionError: If not authenticated.
            ConnectionError: If the API call fails.
        """
        url = f"https://vauth.command.verkada.com/__v/{self.org_short_name}/org/{self.org_id}/custom_roles/enable"
        data = self._request(
            "POST",
            url,
            json={},
            error_context="Failed to enable custom roles",
        )
        log_api_call(
            "POST",
            f"{self.org_short_name}/org/{self.org_id}/custom_roles/enable",
            "{}",
            self._status(data),
            "{}",
        )

    def create_building(
        self, building_name: str, address: Address, floors: list
    ) -> str:
        """
        Creates a building with the given address and floor list.

        Args:
            building_name: Display name for the building.
            address: An Address (label, latitude, longitude). Plain 3-tuples
                are also accepted for backward compatibility.
            floors: List of floor definitions to include in the building.

        Raises:
            PermissionError: If not authenticated.
            ConnectionError: If the API call fails.
        """
        # Accept either Address or a plain 3-tuple
        addr = address if isinstance(address, Address) else Address(*address)

        url = f"https://vprovision.command.verkada.com/__v/{self.org_short_name}/building/create"
        data = self._request(
            "POST",
            url,
            json={
                "name": building_name,
                "organizationId": self.org_id,
                "address": addr.label,
                "latitude": addr.latitude,
                "longitude": addr.longitude,
                "floors": floors,
            },
            error_context=f"Failed to create building '{building_name}'",
        )

        floors_resp = data.get("floors") or []
        if not floors_resp:
            raise ConnectionError(
                f"Failed to create building '{building_name}': no floors in response."
            )
        floor_id = floors_resp[0].get("floorId")
        if not floor_id:
            raise ConnectionError(
                f"Failed to create building '{building_name}': no floorId in response."
            )

        log_api_call(
            "POST",
            f"{self.org_short_name}/building/create",
            f'{{"name": "{building_name}"}}',
            self._status(data),
            "{}",
        )
        return floor_id

    def create_alarm_site(
        self,
        business_name: str,
        alarm_address: AlarmAddress,
        site_id: str,
    ) -> str:
        """
        Creates an alarm response site and enables its software trial.

        Args:
            business_name: Business name for the alarm site.
            alarm_address: An AlarmAddress (city, country, latitude, longitude,
                state, street1, timezone, zipcode). Plain 8-tuples are also
                accepted for backward compatibility.
            site_id: The camera group site ID to link the alarm site to.

        Returns:
            The response_site_id created in step 1.

        Raises:
            PermissionError: If not authenticated.
            ConnectionError: If either step fails. The error message identifies
                which step (alarm site / trial) failed.
        """
        addr = (
            alarm_address
            if isinstance(alarm_address, AlarmAddress)
            else AlarmAddress(*alarm_address)
        )

        base_url = f"https://vagent.command.verkada.com/__v/{self.org_short_name}"
        payload_site = {
            "adminContactUserId": self.user_id,
            "businessName": business_name,
            "dispatchEnabled": True,
            "locationRequest": {
                "apt": "",
                "city": addr.city,
                "country": addr.country,
                "latitude": addr.latitude,
                "longitude": addr.longitude,
                "state": addr.state,
                "street1": addr.street1,
                "street2": "",
                "timezone": addr.timezone,
                "zipcode": addr.zipcode,
            },
            "permitNumber": "",
            "siteId": site_id,
        }
        configurations = [
            ("alarm site", f"{base_url}/response/site/create", payload_site),
            ("trial", f"{base_url}/site/software_trial/create", {"siteId": site_id}),
        ]

        response_site_id = ""
        for config_step, url, payload in configurations:
            data = self._request(
                "POST",
                url,
                json=payload,
                error_context=(
                    f"Failed to configure {config_step} for "
                    f"alarm site '{business_name}'"
                ),
            )

            response_site = data.get("responseSite") or {}
            response_site_id = response_site.get("id") or response_site_id

            log_api_call(
                "POST",
                url.split("/__v/")[1],
                f'{{"siteId": "{site_id}"}}',
                self._status(data),
                "{}",
            )

        return response_site_id

    def create_guest_site(self, guest_address: GuestAddress, site_id: str) -> str:
        """
        Creates a guest (visitor management) site and enables its trial.

        Args:
            guest_address: A GuestAddress (full_address, latitude, longitude,
                country_code). Plain 4-tuples are also accepted for backward
                compatibility.
            site_id: The camera group site ID to link the guest site to.

        Raises:
            PermissionError: If not authenticated.
            ConnectionError: If either step fails. The error message identifies
                which step (guest site / trial) failed.
        """
        addr = (
            guest_address
            if isinstance(guest_address, GuestAddress)
            else GuestAddress(*guest_address)
        )

        base_url = f"https://vdoorman.command.verkada.com/__v/{self.org_short_name}"
        configurations = [
            (
                "guest site",
                f"{base_url}/site/org/{self.org_id}",
                {
                    "siteId": site_id,
                    "fullAddress": addr.full_address,
                    "latitude": addr.latitude,
                    "longitude": addr.longitude,
                    "countryCode": addr.country_code,
                },
            ),
            (
                "trial",
                f"{base_url}/guest/trial/org/{self.org_id}/site/{site_id}",
                {"productType": "GUEST"},
            ),
        ]

        guest_site_id = ""
        for config_step, url, payload in configurations:
            data = self._request(
                "POST",
                url,
                json=payload,
                error_context=(
                    f"Failed to configure {config_step} for guest site '{site_id}'"
                ),
            )

            guest_site_id = data.get("siteId") or guest_site_id

            log_api_call(
                "POST",
                url.split("/__v/")[1],
                f'{{"siteId": "{site_id}"}}',
                self._status(data),
                "{}",
            )

        return guest_site_id

    def add_object(self, device_name: str, serial_number: str) -> str:
        """
        Commissions a new device into the organization.

        Args:
            device_name: Display name for the device.
            serial_number: Hardware serial number.

        Returns:
            The device ID string on success.

        Raises:
            PermissionError: If not authenticated.
            ConnectionError: If the API call fails, no successful devices are
                returned, or the response is missing a deviceId.
        """
        url = (
            f"https://vconductor.command.verkada.com/__v/{self.org_short_name}"
            f"/vconductor/command/device/batch/commission"
        )
        data = self._request(
            "POST",
            url,
            json={
                "organizationId": self.org_id,
                "devices": [
                    {
                        "deferUpdate": True,
                        "name": device_name,
                        "serialNumber": serial_number,
                        "updateSchedule": None,
                    }
                ],
            },
            error_context=f"Failed to add device '{device_name}'",
        )

        successful = data.get("successfulDevices", [])
        if not successful:
            failed = data.get("failedSerials", [])
            raise ConnectionError(
                f"Failed to add device '{device_name}': "
                f"no successful devices returned. Failed serials: {failed}"
            )

        device_id = successful[0].get("deviceId")
        if not device_id:
            raise ConnectionError(
                f"Failed to add device '{device_name}': "
                "successful response missing deviceId."
            )

        log_api_call(
            "POST",
            f"{self.org_short_name}/vconductor/command/device/batch/commission",
            f'{{"serialNumber": "{serial_number}", "name": "{device_name}"}}',
            self._status(data),
            f'{{"deviceId": "{device_id}"}}',
        )
        return device_id

    def configure_object(
        self,
        category: str,
        device_id: str,
        device_name: str,
        site_id: str,
        object_parameters: dict,
    ) -> Optional[str]:
        """
        Configures a newly commissioned device.

        Args:
            category: Device category — 'camera', 'controller', 'connector',
                'alarm_panel', or 'keypad'.
            device_id: The device ID returned by add_object().
            device_name: Display name for the device.
            site_id: The site to assign the device to.
            object_parameters: A dictionary of object-specific parameters.
                For cameras/connectors: must include 'address' as an Address
                (or 3-tuple of label, lat, lon).
                For controllers: must include 'floor_id', 'timezone', and
                'door_name'.
                For keypads: must include 'alarm_system_id' and 'serial_number'.

        Returns:
            For 'controller': the door_id of the door created in step 2.
            For 'alarm_panel': the alarm_system_id created in step 1.
            For all other categories: None.

        Raises:
            PermissionError: If not authenticated.
            ValueError: If an unknown category is given or required parameters
                are missing.
            ConnectionError: If any configuration step fails. The error message
                identifies which step failed; remaining steps are NOT executed.
        """
        if not self.auth_data:
            raise PermissionError("Not authenticated. Please call login() first.")

        match category:
            case "camera":
                if "address" not in object_parameters:
                    raise ValueError(
                        "Missing 'address' in object_parameters for camera"
                    )
                raw_addr = object_parameters["address"]
                addr = raw_addr if isinstance(raw_addr, Address) else Address(*raw_addr)
                base_url = f"https://vprovision.command.verkada.com/__v/{self.org_short_name}/camera"
                configurations = [
                    (
                        "name",
                        f"{base_url}/name/set",
                        {"cameraId": device_id, "name": device_name},
                    ),
                    (
                        "site assignment",
                        f"{base_url}/site/batch/set",
                        {"cameraIds": [device_id], "destinationSiteId": site_id},
                    ),
                    (
                        "location",
                        f"{base_url}/location/set",
                        {
                            "cameraId": device_id,
                            "angle": 0,
                            "label": addr.label,
                            "lat": addr.latitude,
                            "lon": addr.longitude,
                        },
                    ),
                ]
                for config_step, url, payload in configurations:
                    data = self._request(
                        "POST",
                        url,
                        json=payload,
                        error_context=(
                            f"Failed to configure {config_step} for '{device_name}'"
                        ),
                    )
                    log_api_call(
                        "POST",
                        url.split("/__v/")[1],
                        f'{{"deviceId": "{device_id}"}}',
                        self._status(data),
                        "{}",
                    )

            case "controller":
                floor_id = object_parameters.get("floor_id")
                timezone = object_parameters.get("timezone")
                door_name = object_parameters.get("door_name")
                if floor_id is None or timezone is None or door_name is None:
                    raise ValueError(
                        "Missing 'floor_id' or 'timezone' or 'door_name' in object_parameters for controller"
                    )

                # Step 1: Set up the access controller
                setup_url = (
                    f"https://vcerberus.command.verkada.com/__v/{self.org_short_name}"
                    f"/access/v2/user/access_device/setup"
                )
                setup_data = self._request(
                    "POST",
                    setup_url,
                    json={
                        "configs": {"acu-mode": "normal"},
                        "deviceId": device_id,
                        "floorId": floor_id,
                        "name": device_name,
                        "siteId": site_id,
                        "timezone": timezone,
                    },
                    error_context=(
                        f"Failed to configure controller '{device_name}' "
                        f"(step 1: controller setup)"
                    ),
                )

                # Use a separate name; do NOT shadow the device_id parameter.
                controller_id = setup_data.get("accessControllerId")
                if not controller_id:
                    raise ConnectionError(
                        f"Failed to configure controller '{device_name}' "
                        f"(step 1: controller setup): no accessControllerId returned."
                    )

                log_api_call(
                    "POST",
                    setup_url.split("/__v/")[1],
                    f'{{"deviceId": "{device_id}"}}',
                    self._status(setup_data),
                    f'{{"accessControllerId": "{controller_id}"}}',
                )

                # Step 2: Create the door bound to this controller
                door_url = f"https://api.command.verkada.com/__v/{self.org_short_name}/door/create"
                door_payload = {
                    "accessControllerId": controller_id,
                    "configs": [
                        {"paramName": "default-unlock-time", "paramValue": "10"},
                        {"paramName": "assa-extended-unlock-time", "paramValue": "20"},
                        {"paramName": "has-door-sensor", "paramValue": "True"},
                        {"paramName": "ignore-dpi-relock", "paramValue": "False"},
                        {"paramName": "passthrough-dpi-enabled", "paramValue": "False"},
                        {"paramName": "dho-enabled", "paramValue": "False"},
                        {"paramName": "dho-trigger-time", "paramValue": "60"},
                        {"paramName": "has-rex", "paramValue": "True"},
                        {"paramName": "rex-unlock-time", "paramValue": "3"},
                        {"paramName": "has-rex2", "paramValue": "False"},
                        {"paramName": "rex2-unlock-time", "paramValue": "3"},
                        {"paramName": "dfo-rex-cooloff-time", "paramValue": "10"},
                        {"paramName": "ble-unlock-enabled", "paramValue": "True"},
                        {"paramName": "ble-unlock-rssi", "paramValue": "-45"},
                        {"paramName": "ble-connect-rssi", "paramValue": "-55"},
                        {"paramName": "ble-unlock-cooldown-time", "paramValue": "5"},
                        {"paramName": "tof-unlock-distance-mm", "paramValue": "500"},
                        {
                            "paramName": "third-party-io-baud-rate",
                            "paramValue": "14400",
                        },
                        {"paramName": "badge-reader", "paramValue": "True"},
                        {"paramName": "mobile-unlock-enabled", "paramValue": "True"},
                        {"paramName": "door-api-unlock-enabled", "paramValue": "False"},
                        {"paramName": "nfc-enabled", "paramValue": "True"},
                        {"paramName": "lpr-unlock-enabled", "paramValue": "True"},
                        {"paramName": "lpr-unlock-cooldown-time", "paramValue": "0"},
                        {
                            "paramName": "ignore-outbound-reader-ac",
                            "paramValue": "False",
                        },
                        {"paramName": "lf-card-reading-enabled", "paramValue": "True"},
                        {"paramName": "polling-frequency-ms", "paramValue": "10000"},
                        {"paramName": "c3po-in1-type", "paramValue": "NONE"},
                        {"paramName": "c3po-in2-type", "paramValue": "NONE"},
                        {
                            "paramName": "replace-ios-with-security-relay",
                            "paramValue": "False",
                        },
                    ],
                    "deviceIos": [
                        {
                            "configs": {},
                            "ioDeviceTypeName": "ad31",
                            "ioSlotIndex": 0,
                            "ioSlotType": "rs485",
                        },
                        {
                            "configs": {},
                            "ioDeviceTypeName": "reader",
                            "ioSlotIndex": 0,
                            "ioSlotType": "wiegand",
                        },
                        {
                            "configs": {},
                            "ioDeviceTypeName": "lock",
                            "ioSlotIndex": 0,
                            "ioSlotType": "lock",
                        },
                        {
                            "configs": {"signalConfig": "NO"},
                            "ioDeviceTypeName": "dpi",
                            "ioSlotIndex": 0,
                            "ioSlotType": "dpi",
                        },
                        {
                            "configs": {"signalConfig": "NO"},
                            "ioDeviceTypeName": "rex",
                            "ioSlotIndex": 0,
                            "ioSlotType": "rex",
                        },
                        {
                            "configs": {"signalConfig": "NO"},
                            "ioDeviceTypeName": "rex2",
                            "ioSlotIndex": 0,
                            "ioSlotType": "rex2",
                        },
                    ],
                    "doorType": "standard",
                    "floorId": floor_id,
                    "name": door_name,
                }

                door_data = self._request(
                    "POST",
                    door_url,
                    json=door_payload,
                    error_context=(
                        f"Failed to configure door '{device_name} Door' "
                        f"(step 2: door creation)"
                    ),
                )

                # Guard against missing/empty 'doors' list (was an IndexError).
                doors = door_data.get("doors") or []
                if not doors:
                    raise ConnectionError(
                        f"Failed to configure door '{device_name} Door' "
                        f"(step 2: door creation): no doors returned in response."
                    )
                door_id = doors[0].get("doorId")
                if not door_id:
                    raise ConnectionError(
                        f"Failed to configure door '{device_name} Door' "
                        f"(step 2: door creation): no doorId in response."
                    )

                # Log against the door URL (not the setup URL — that was a bug).
                log_api_call(
                    "POST",
                    door_url.split("/__v/")[1],
                    f'{{"doorId": "{door_id}"}}',
                    self._status(door_data),
                    "{}",
                )
                return door_id

            case "connector":
                if "address" not in object_parameters:
                    raise ValueError(
                        "Missing 'address' in object_parameters for connector"
                    )
                raw_addr = object_parameters["address"]
                addr = raw_addr if isinstance(raw_addr, Address) else Address(*raw_addr)
                base_url = f"https://vprovision.command.verkada.com/__v/{self.org_short_name}/vfortress/update_box"
                data = self._request(
                    "POST",
                    base_url,
                    json={
                        "deviceId": device_id,
                        "locationLabel": addr.label,
                        "locationLat": addr.latitude,
                        "locationLon": addr.longitude,
                        "name": device_name,
                        "siteId": site_id,
                    },
                    error_context=f"Failed to configure connector '{device_name}'",
                )

                # None default is more honest for a string field than [].
                connector_device_id = data.get("deviceId")
                if not connector_device_id:
                    raise ConnectionError(
                        f"Failed to configure connector '{device_name}': "
                        f"no deviceId in response."
                    )

                log_api_call(
                    "POST",
                    base_url.split("/__v/")[1],
                    f'{{"deviceId": "{connector_device_id}"}}',
                    self._status(data),
                    "{}",
                )

            case "alarm_panel":
                # Step 1: Create alarm system
                url_create = (
                    f"https://vproconfig.command.verkada.com/__v/{self.org_short_name}"
                    "/alarm_system/create"
                )
                create_data = self._request(
                    "POST",
                    url_create,
                    json={"orgId": self.org_id, "siteId": site_id},
                    error_context=(
                        f"Failed to configure alarm_panel '{device_name}' "
                        f"(step 1: create alarm system)"
                    ),
                )

                system_id = (create_data.get("alarmSystem") or {}).get("id")
                if not system_id:
                    raise ConnectionError(
                        f"Failed to configure alarm_panel '{device_name}' "
                        f"(step 1: create alarm system): no system ID in response."
                    )

                log_api_call(
                    "POST",
                    f"{self.org_short_name}/alarm_system/create",
                    f'{{"siteId": "{site_id}"}}',
                    self._status(create_data),
                    f'{{"alarmSystemId": "{system_id}"}}',
                )

                # Step 2: Set up the panel device
                url_panel = (
                    f"https://vproconfig.command.verkada.com/__v/{self.org_short_name}"
                    "/unassigned_device/setup_colossus"
                )
                panel_data = self._request(
                    "POST",
                    url_panel,
                    json={
                        "alarmSystemId": system_id,
                        "deviceId": device_id,
                        "name": device_name,
                        "replaceExistingLeader": False,
                    },
                    error_context=(
                        f"Failed to configure alarm_panel '{device_name}' "
                        f"(step 2: panel setup)"
                    ),
                )

                log_api_call(
                    "POST",
                    f"{self.org_short_name}/unassigned_device/setup_colossus",
                    f'{{"deviceId": "{device_id}", "alarmSystemId": "{system_id}"}}',
                    self._status(panel_data),
                    "{}",
                )

                return system_id

            case "keypad":
                alarm_system_id = object_parameters.get("alarm_system_id")
                serial_number = object_parameters.get("serial_number")
                if alarm_system_id is None or serial_number is None:
                    raise ValueError(
                        "Missing 'alarm_system_id' or 'serial_number' in object_parameters for keypad"
                    )
                url_config_keypad = f"https://vproconfig.command.verkada.com/__v/{self.org_short_name}/unassigned_device/set_up_alarm_device"
                data = self._request(
                    "POST",
                    url_config_keypad,
                    json={
                        "alarmSystemId": alarm_system_id,
                        "deviceId": device_id,
                        "name": device_name,
                        "serialNumber": serial_number,
                    },
                    error_context=f"Failed to configure Alarm Keypad '{device_name}'",
                )

                log_api_call(
                    "POST",
                    url_config_keypad.split("/__v/")[1],
                    f'{{"deviceId": "{device_id}", "alarmSystemId": "{alarm_system_id}"}}',
                    self._status(data),
                    "{}",
                )

            case _:
                raise ValueError(
                    f"Unknown device category for configure_object: {category!r}"
                )

        return None

    def create_access_level(
        self, door_id: str, access_level_name: str, site_id: str, group_id: str
    ) -> None:
        """
        Creates a 24/7 access level (schedule) for the given door.

        Args:
            door_id: The door to grant access on.
            access_level_name: Display name for the access level.
            site_id: The site to scope the access level to.
            group_id: User group to grant access to. Pass an empty string to
                create the access level with no user groups attached (the AS
                template flow uses this).

        Raises:
            PermissionError: If not authenticated.
            ConnectionError: If the API call fails.
        """
        url = f"https://vcerberus.command.verkada.com/__v/{self.org_short_name}/access/v2/user/schedules"
        # 24/7 schedule: ALLOW for every weekday, all day. Time format is
        # HH:MM:SS.mmm — note the period before the milliseconds (server
        # rejects HH:MM:SS:mmm with "Incorrectly formatted data").
        START_TIME = "00:00:00.000"
        END_TIME = "23:59:59.999"
        events = [
            {
                "date": None,
                "doorPermissionState": "ALLOW",
                "endTime": END_TIME,
                "startTime": START_TIME,
                "weekday": day,
            }
            for day in range(1, 8)
        ]
        payload = {
            "defaultDoorLockState": "ACCESS_CONTROL",
            "defaultDoorPermissionState": "DENY",
            "deleted": False,
            "doors": [door_id],
            "endDateTime": None,
            "events": events,
            "name": access_level_name,
            "priority": "SCHEDULE",
            "sites": [site_id],
            "startDateTime": None,
            "type": "USER",
            "userGroups": [group_id] if group_id else [],
        }

        data = self._request(
            "POST",
            url,
            json=payload,
            error_context=f"Failed to create access level '{access_level_name}'",
        )

        log_api_call(
            "POST",
            f"{self.org_short_name}/access/v2/user/schedules",
            f'{{"name": "{access_level_name}"}}',
            self._status(data),
            "{}",
        )

    def get_object(self, category: str) -> list[dict[str, Any]]:
        """
        Generic fetch method for various Verkada device types via the internal API.

        Uses pattern matching to determine the correct endpoint, HTTP method,
        and normalization function for each device type.

        Args:
            category: Device type slug — one of: 'intercoms', 'access_controllers',
                      'sensors', 'mailroom_sites', 'desk_stations', 'alarm_sites',
                      'alarm_devices', 'unassigned_devices'.

        Returns:
            List of dicts with standardized keys: 'id', 'name', and optionally
            'serial_number', 'site_id', 'alarm_site_id', 'alarm_system_id'.

        Raises:
            PermissionError: If not authenticated.
            ValueError: If an unknown category is requested.
            ConnectionError: If the API call fails or returns non-JSON.
        """
        payload: dict[str, Any] | None = None

        match category:
            case "intercoms":
                object_type = "intercoms"
                request_type = "GET"
                subdomain = "api"
                path = f"vinter/v1/user/organization/{self.org_id}/device"

                def mapping_func(x: dict[str, Any]) -> dict[str, Any]:
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

                def mapping_func(x: dict[str, Any]) -> dict[str, Any]:
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

                def mapping_func(x: dict[str, Any]) -> dict[str, Any]:
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

                def mapping_func(x: dict[str, Any]) -> dict[str, Any]:
                    return {"id": x["siteId"], "name": x["siteName"]}

            case "desk_stations":
                object_type = "deskApps"
                request_type = "GET"
                subdomain = "api"
                path = f"vinter/v1/user/organization/{self.org_id}/device"

                def mapping_func(x: dict[str, Any]) -> dict[str, Any]:
                    return {
                        "id": x["deviceId"],
                        "name": x["name"],
                        "serial_number": x["serialNumber"],
                    }

            case "connectors":
                object_type = "items"
                request_type = "POST"
                subdomain = "vprovision"
                path = "vfortress/list_boxes"
                payload = {"organizationId": self.org_id}

                def mapping_func(x: dict[str, Any]) -> dict[str, Any]:
                    return {
                        "id": x["deviceId"],
                        "name": x["name"],
                        "serial_number": x.get("claimedSerialNumber"),
                    }

            case "alarm_sites":
                object_type = "responseSites"
                request_type = "POST"
                subdomain = "vagent"
                path = "response/site/list"
                payload = {"includeResponseConfigs": True}

                def mapping_func(x: dict[str, Any]) -> dict[str, Any]:
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
                payload = {"organizationId": self.org_id}

                def mapping_func(x: dict[str, Any]) -> dict[str, Any]:
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

                def mapping_func(x: dict[str, Any]) -> dict[str, Any]:
                    return {
                        "id": x["deviceId"],
                        "name": x["name"],
                        "serial_number": x["serialNumber"],
                    }

            case _:
                raise ValueError(f"Unknown device category: {category!r}")

        url = (
            f"https://{subdomain}.command.verkada.com/__v/{self.org_short_name}/{path}"
        )

        data = self._request(
            request_type,
            url,
            json=payload,
            error_context=f"Failed to fetch {category}",
        )

        items = data.get(object_type, [])
        results = [mapping_func(item) for item in items]

        log_api_call(
            request_type,
            f"{self.org_short_name}/{path}",
            f'{{"organizationId": "{self.org_id}"}}',
            self._status(data),
            f'{{"count": {len(results)}}}',
        )

        return results

    def delete_object(
        self, category: str, object_id: str | list[str] | tuple[str, ...]
    ) -> None:
        """
        Decommissions or deletes a specific object by ID via the internal API.

        Uses pattern matching to determine the correct endpoint and HTTP method
        for each device type.

        Args:
            category: The type of object to delete.
            object_id: The ID string for most categories. For 'alarm_sites',
                must be a 2-element sequence: [response_site_id, site_id].

        Raises:
            PermissionError: If not authenticated.
            ValueError: If an unknown category is requested, or if alarm_sites
                is given a non-2-element id.
            ConnectionError: If the API call fails.
        """
        payload: dict[str, Any] | None = None

        match category:
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

            case "connectors":
                request_type = "POST"
                subdomain = "vprovision"
                path = "vfortress/decommission"
                payload = {"deviceId": object_id, "organizationId": self.org_id}

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
                # alarm_sites requires a 2-element sequence:
                # [response_site_id, site_id]. A single string would silently
                # index into chars, so validate the shape explicitly.
                if isinstance(object_id, (str, bytes)) or not isinstance(
                    object_id, (list, tuple)
                ):
                    raise ValueError(
                        "alarm_sites requires a 2-element sequence "
                        "[response_site_id, site_id], got a single value."
                    )
                if len(object_id) != 2:
                    raise ValueError(
                        f"alarm_sites requires a 2-element sequence "
                        f"[response_site_id, site_id], got {len(object_id)} elements."
                    )
                response_site_id, alarm_site_internal_id = object_id
                request_type = "POST"
                subdomain = "vagent"
                path = "response/site/delete"
                payload = {
                    "responseSiteId": response_site_id,
                    "siteId": alarm_site_internal_id,
                }

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
                raise ValueError(f"Unknown device category: {category!r}")

        url = (
            f"https://{subdomain}.command.verkada.com/__v/{self.org_short_name}/{path}"
        )

        data = self._request(
            request_type,
            url,
            json=payload,
            error_context=f"Failed to delete {category} {object_id!r}",
        )

        log_api_call(
            request_type,
            f"{self.org_short_name}/{path}",
            f'{{"id": "{object_id}"}}',
            self._status(data),
            "{}",
        )
