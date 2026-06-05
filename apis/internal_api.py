import time
from typing import Any

import requests
from requests.exceptions import JSONDecodeError, RequestException

from apis.endpoints import (
    _DOOR_CREATE_CONFIGS,
    _DOOR_CREATE_IOS,
    _DOOR_EVENT,
    _LPR_DOOR_CREATE_CONFIGS,
    Address,
    AlarmAddress,
    GuestAddress,
    MFARequiredError,
    build_url,
    resolve,
)
from constants import (
    API_NAME,
    AS_INSTRUCTOR_KEYCODE,
    AS_INSTRUCTOR_KEYCODE_NAME,
    DEFAULT_TIMEOUT,
    DEV_SKIP_LOGIN,
)
from utils.logger import log_api_call


class APIError(ConnectionError):
    """
    API returned an error response. Carries the typed `id` code from the
    body so callers can branch on specific error kinds (e.g. invite_user
    catches code='cannot_invite_existing'). Subclasses ConnectionError so
    legacy `except ConnectionError` blocks still catch it.
    """

    def __init__(self, message: str = "", *, code: str = "", status_code: int = 0):
        super().__init__(message)
        self.code = code
        self.status_code = status_code


# Alarm device `type` strings (returned by alarm_system/get_devices) mapped
# to the v2 delete endpoint key for that device. Panels/keypads/expanders/
# wireless decommission; wired in/out use a different delete path.
_ALARM_DEVICE_DELETE_KEYS = {
    "COLOSSUS": "alarm.panel.delete",
    "SYLVIE": "alarm.keypad.delete",
    "KURIBO": "alarm.expander.delete",
    "WIRELESS_CONTACT_SENSOR": "alarm.wireless_contact_sensor.delete",
    "WIRELESS_PANIC_BUTTON": "alarm.wireless_panic_button.delete",
    "UNIVERSAL_TRANSMITTER": "alarm.wireless_universal_transmitter.delete",
    "WIRED_GENERIC_OUTPUT": "alarm.wired_output.delete",
    "WIRED_CONTACT_SENSOR": "alarm.wired_input.delete",
}

# Fixed overnight (23:30–06:30) arm schedule applied to every camera guard.
# startMinute 1110 = 18.5h*60; endMinute 390 = 6.5h*60. Each entry spans
# one night, rolling Sun→Mon … Sat→Sun.
_GUARD_SCHEDULES = [
    {
        "startDay": day,
        "startMinute": 1110,
        "startSecond": 0,
        "endDay": (day + 1) % 7,
        "endMinute": 390,
        "endSecond": 0,
    }
    for day in range(7)
]


class VerkadaInternalAPIClient:
    """
    Client for the Verkada internal (Command) API.

    API surface conventions:
      - One method per category per verb. No category dispatchers; each
        call site picks the exact method it wants.
      - create_*  → creates a logical entity (site, building, schedule)
      - configure_* → configures a previously commissioned device
      - delete_* → decommissions / deletes one entity by id
      - get_*    → lists one device/site category
      - enable_* / disable_* → toggle org or device feature flags

    Dispatch tables for callers that iterate over categories dynamically
    (e.g. decommission_view) live in constants.py as method-name maps.
    """

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

        # Saved during login() so verify_mfa() can replay the same payload
        self._pending_payload: dict | None = None

    # ------------------------------------------------------------------
    # Identity helpers
    # ------------------------------------------------------------------

    @property
    def user_id(self) -> str | None:
        return self.auth_data.get("adminUserId") if self.auth_data else None

    @property
    def org_id(self) -> str | None:
        return self.auth_data.get("organizationId") if self.auth_data else None

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

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

    def _parse_login_response(self, json_data: dict[str, Any]) -> dict[str, str]:
        """
        Extract session tokens from a successful login response and install
        them on the requests session as cookies.
        """
        try:
            csrf_token = str(json_data["csrfToken"])
            user_token = str(json_data["userToken"])
            organization_id = str(json_data["organizationId"])
            admin_user_id = str(json_data["userId"])

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

    def _login_url(self) -> str:
        """Pre-auth helper: build the login URL from the registry."""
        endpoint, formatted_path = resolve("login")
        return build_url(endpoint, self.org_short_name, formatted_path)

    def _set_global_site_admin(self, enabled: bool) -> None:
        key = (
            "permissions.global_site_admin.enable"
            if enabled
            else "permissions.global_site_admin.disable"
        )
        action = "enable" if enabled else "disable"
        self._request(
            key,
            json={
                "organizationId": self.org_id,
                "settings": {"globalSiteAdmin": enabled},
            },
            error_context=f"Failed to {action} Global Site Admin",
            log_request=(f'{{"globalSiteAdmin": {str(enabled).lower()}}}'),
        )

    def _set_user_permission(
        self,
        endpoint_key: str,
        permission: str,
        *,
        grant: bool,
        label: str,
    ) -> None:
        """
        Grant or revoke a single org-scoped permission on the current user.

        v2 splits the legacy multi-grant `access.roles.modify` endpoint
        into per-permission enable/disable keys (each just a thin wrapper
        around POST org/set_user_permissions with the grant/revoke arrays
        swapped); this helper carries the payload shape so callers only
        name the endpoint key and the permission string.
        """
        perms = [{"entityId": self.org_id, "permission": permission}]
        self._request(
            endpoint_key,
            json={
                "organizationId": self.org_id,
                "targetUserId": self.user_id,
                "returnPermissions": False,
                "grant": perms if grant else [],
                "revoke": [] if grant else perms,
            },
            error_context=f"Failed to {'grant' if grant else 'revoke'} {label}",
            log_request=(
                f'{{"targetUserId": "{self.user_id}", "permission": "{permission}"}}'
            ),
        )

    def _set_camera_features(
        self,
        camera_ids: list[str],
        feature_flags: dict[str, bool],
        feature_label: str,
    ) -> None:
        self._request(
            "camera.create.feature",
            json={"cameraIds": camera_ids, "params": feature_flags},
            error_context=f"Failed to enable {feature_label}",
            log_request=f'{{"cameraIds": {camera_ids}}}',
        )

    def _fetch_list(
        self,
        endpoint_key: str,
        *,
        response_key: str,
        mapping_func,
        path_params: dict | None = None,
        payload: dict | None = None,
    ) -> list[dict[str, Any]]:
        """Shared body for every get_* method."""
        data, status = self._request(
            endpoint_key,
            path_params=path_params,
            json=payload,
            error_context=f"Failed to fetch from {endpoint_key}",
            log_request=f'{{"organizationId": "{self.org_id}"}}',
            auto_log=False,
        )
        items = data.get(response_key, [])
        results = [mapping_func(item) for item in items]
        self._log(
            endpoint_key,
            status,
            path_params=path_params,
            log_request=f'{{"organizationId": "{self.org_id}"}}',
            log_response=f'{{"count": {len(results)}}}',
        )
        return results

    def _delete(
        self,
        endpoint_key: str,
        *,
        oid: str,
        json: dict | None = None,
        path_params: dict | None = None,
    ) -> None:
        """Shared body for every delete_* method."""
        self._request(
            endpoint_key,
            path_params=path_params,
            json=json,
            error_context=f"Failed to delete via {endpoint_key} (id={oid!r})",
            log_request=f'{{"id": "{oid}"}}',
        )

    def _request(
        self,
        endpoint_key: str,
        *,
        json: dict | None = None,
        path_params: dict | None = None,
        error_context: str,
        log_request: str = "",
        log_response: str = "",
        auto_log: bool = True,
    ) -> tuple[dict, int]:
        """
        Execute an authenticated request against a registered endpoint.

        URL building, auth header injection, JSON decode, empty-body
        tolerance, error-message extraction, and (by default) request
        logging all happen here. Callers only describe the call.

        Set auto_log=False when you need to log a field extracted from
        the response, and call _log() manually after extraction.

        Returns:
            (data, status_code) — `data` is the decoded body (top-level
            lists are wrapped as {"items": [...]}); `status_code` is the
            HTTP status. Both are exposed so callers can pass the status
            into _log() after extracting response fields.

        Raises:
            PermissionError: If not authenticated.
            APIError: On any non-2xx HTTP response; carries the typed `id`
                code from the response body when present.
            ConnectionError: On transport or decode failure.
        """
        if not self.auth_data:
            raise PermissionError("Not authenticated. Please call login() first.")

        endpoint, formatted_path = resolve(endpoint_key, path_params)
        url = build_url(endpoint, self.org_short_name, formatted_path)

        try:
            response = self.session.request(
                endpoint.method,
                url,
                json=json,
                headers=self._get_headers(),
                timeout=DEFAULT_TIMEOUT,
            )
        except RequestException as e:
            raise ConnectionError(f"{error_context}: {e}")

        # Tolerate empty bodies (some DELETEs and a few POSTs return nothing).
        if response.content:
            try:
                data = response.json()
            except JSONDecodeError:
                if not response.ok:
                    raise APIError(
                        f"{error_context}: {response.text or 'non-JSON response.'}",
                        status_code=response.status_code,
                    )
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
            code = data_dict.get("id", "") if isinstance(data_dict, dict) else ""
            raise APIError(
                f"{error_context}: {msg or 'unknown error'}",
                code=code,
                status_code=response.status_code,
            )

        if auto_log:
            log_api_call(
                endpoint.method,
                f"{self.org_short_name}/{formatted_path}",
                log_request,
                str(response.status_code),
                log_response,
            )

        return data_dict, response.status_code

    def _log(
        self,
        endpoint_key: str,
        status_code: int,
        *,
        log_request: str = "",
        log_response: str = "",
        path_params: dict | None = None,
    ) -> None:
        """
        Log a call using the same endpoint key + path_params used for the
        request. Used by methods that called _request(auto_log=False) and
        want to include extracted response fields in the log line.
        """
        endpoint, formatted_path = resolve(endpoint_key, path_params)
        log_api_call(
            endpoint.method,
            f"{self.org_short_name}/{formatted_path}",
            log_request,
            str(status_code),
            log_response,
        )

    # ------------------------------------------------------------------
    # Authentication
    # ------------------------------------------------------------------

    def _post_login(
        self,
        payload: dict,
        *,
        log_label: str,
        log_request: str,
        error_label: str,
    ) -> tuple[dict, int]:
        """
        Pre-auth POST to the login endpoint. Returns (decoded_body, status_code).

        Both login() and verify_mfa() use this — they run pre-auth so they
        can't go through _request (which enforces auth). The helper owns
        the POST + JSON-decode + decode-failure log; the caller branches
        on success / MFA / bad-credentials in the returned body.
        """
        try:
            response = self.session.post(
                self._login_url(),
                json=payload,
                timeout=DEFAULT_TIMEOUT,
            )
            data = response.json()
        except JSONDecodeError:
            log_api_call("POST", log_label, log_request, "200", "non-JSON response")
            raise ConnectionError(
                f"{error_label}: server returned a non-JSON response."
            )
        except RequestException as e:
            raise ConnectionError(f"{error_label}: {e}")
        return data, response.status_code

    def login(self) -> None:
        """
        Authenticate with the Verkada Provisioning API.

        Success (no MFA):  loggedIn=true → auth_data populated
        MFA required:      "2FA invalid" in message → MFARequiredError raised
        Bad credentials:   anything else → ConnectionError raised
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

        payload = {
            "email": self.email,
            "orgShortName": self.org_short_name,
            "termsAcked": False,
            "password": self.password,
            "loginMethod": "password",
            "shard": self.shard,
            "subdomain": True,
        }
        log_label = f"{self.org_short_name}/user/login"
        log_request = f'{{"email": "{self.email}"}}'

        data, status = self._post_login(
            payload,
            log_label=log_label,
            log_request=log_request,
            error_label="Login failed",
        )
        msg = data.get("message", "")

        if status == 200 and data.get("loggedIn"):
            self.auth_data = self._parse_login_response(data)
            return

        if "2FA invalid" in msg:
            self._pending_payload = payload
            sms_contact = data.get("data", {}).get("smsSent")
            log_api_call("POST", log_label, log_request, "200 (MFA)", msg)
            raise MFARequiredError("MFA Required", sms_contact)

        log_api_call("POST", log_label, log_request, str(status), msg)
        raise ConnectionError(f"Login failed: {msg or 'unknown error'}")

    def verify_mfa(self, otp_code: str) -> None:
        """
        Complete login by submitting the 2FA OTP code.

        Must be called after login() has raised MFARequiredError.
        """
        if not self._pending_payload:
            raise ValueError("No pending login. Call login() first.")

        payload = {**self._pending_payload, "otp": otp_code}
        log_label = f"{self.org_short_name}/user/login (MFA)"
        log_request = '{"otp": "***"}'

        data, status = self._post_login(
            payload,
            log_label=log_label,
            log_request=log_request,
            error_label="MFA verification failed",
        )
        msg = data.get("message", "")

        if status == 200 and data.get("loggedIn"):
            self.auth_data = self._parse_login_response(data)
            self._pending_payload = None
            return

        if "2FA invalid" in msg:
            log_api_call("POST", log_label, log_request, "200 (bad OTP)", msg)
            raise ValueError("Incorrect 2FA code. Please try again.")

        log_api_call("POST", log_label, log_request, str(status), msg)
        raise ConnectionError(f"MFA verification failed: {msg or 'unknown error'}")

    # ------------------------------------------------------------------
    # Devices
    # ------------------------------------------------------------------

    def add_device(self, device_name: str, serial_number: str) -> str:
        """
        Commissions a new device into the organization by serial number.

        Returns:
            The device ID string on success.
        """
        data, status = self._request(
            "org.add_device",
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
            log_request=f'{{"serialNumber": "{serial_number}", "name": "{device_name}"}}',
            auto_log=False,
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

        self._log(
            "org.add_device",
            status,
            log_request=f'{{"serialNumber": "{serial_number}", "name": "{device_name}"}}',
            log_response=f'{{"deviceId": "{device_id}"}}',
        )
        return device_id

    def get_unassigned_device(self) -> list[dict[str, Any]]:
        return self._fetch_list(
            "org.unassigned_devices.list",
            response_key="devices",
            path_params={"org_id": self.org_id},
            mapping_func=lambda x: {
                "id": x["deviceId"],
                "name": x["name"],
                "serial_number": x["serialNumber"],
            },
        )

    def is_org_empty(self) -> bool:
        """
        Pre-flight check for destructive flows: returns True iff the org
        holds no devices/sites/users (i.e. delete would succeed).
        """
        data, _ = self._request(
            "org.check_empty",
            json={"organizationId": self.org_id, "validateOnly": True},
            error_context="Failed to check if org is empty",
            log_request=f'{{"organizationId": "{self.org_id}"}}',
        )
        return bool(data.get("orgEmpty"))

    def get_device_count(self) -> dict[str, int]:
        """
        Returns {device_type: quantity} across every device category Verkada
        tracks. Useful for capacity dashboards / decommission accounting.
        """
        data, _ = self._request(
            "org.device_count",
            path_params={"org_id": self.org_id},
            error_context="Failed to fetch device counts",
            log_request=f'{{"organizationId": "{self.org_id}"}}',
        )
        return {d["deviceType"]: d["quantity"] for d in data.get("deviceCounts", [])}

    # ------------------------------------------------------------------
    # Users
    # ------------------------------------------------------------------

    def invite_user(
        self,
        email: str,
        first_name: str,
        last_name: str,
        role: str = "Org Admin",
    ) -> dict:
        """
        Invites a user to the organization.

        Maps the role string to orgAdmin: "Org Admin" → True, anything else → False.

        Returns a dict with user_id, email, and name on success. user_id and
        name are None if the response did not include user details.

        Raises ValueError if the user is already in the org.
        Raises ConnectionError / APIError for other API failures.
        """
        payload = {
            "organizationId": self.org_id,
            "email": email,
            "orgAdmin": role == "Org Admin",
            "commandUserAdmin": False,
            "firstName": first_name,
            "lastName": last_name,
            "inviteFf": True,
        }
        log_request = (
            f'{{"email": "{email}", "firstName": "{first_name}", '
            f'"lastName": "{last_name}"}}'
        )

        try:
            data, status = self._request(
                "user.create",
                json=payload,
                error_context=f"Invite failed for {email}",
                log_request=log_request,
                auto_log=False,
            )
        except APIError as e:
            if e.code == "cannot_invite_existing":
                raise ValueError(f"User already exists in this org: {email}")
            raise

        invitation_id = (data.get("orgInvitation") or [{}])[0].get(
            "orgInvitationId", ""
        )
        self._log(
            "user.create",
            status,
            log_request=log_request,
            log_response=f'{{"orgInvitationId": "{invitation_id}"}}',
        )

        users = data.get("users") or []
        if users:
            u = users[0]
            return {
                "user_id": u.get("userId"),
                "email": u.get("email"),
                "name": u.get("name"),
            }
        return {"user_id": None, "email": email, "name": None}

    def get_user(self) -> list[dict[str, Any]]:
        """
        Lists active + invited org users.

        Paging is fixed at pageSize=1000: orgs with more than 1000 users
        will silently truncate. The v2 endpoint supports cursor paging
        (searchAfter); wire it up if/when the cap becomes a real ceiling.
        """
        return self._fetch_list(
            "user.list",
            response_key="users",
            path_params={"org_id": self.org_id},
            payload={
                "paging": {"pageSize": 1000, "sortOrder": ["full_name:asc"]},
                "isVisitor": False,
                "status": ["active", "invited"],
                "organizationId": self.org_id,
                "userDirectoryIds": [],
                "includeRoleGrants": True,
                "includeGroups": True,
                "useEs": True,
            },
            mapping_func=lambda x: {
                "id": x["userId"],
                "email": x["email"],
                "first_name": x.get("firstName"),
                "last_name": x.get("lastName"),
                "is_org_admin": x.get("isOrganizationAdmin", False),
            },
        )

    def delete_user(self, user_id: str) -> None:
        self._delete(
            "user.delete",
            json={"organizationId": self.org_id, "userIds": [user_id]},
            oid=user_id,
        )

    # ------------------------------------------------------------------
    # API Keys
    # ------------------------------------------------------------------

    def create_external_api_key(self) -> str:
        """
        Generates a temporary External API Key (used to initialize the
        VerkadaExternalAPIClient). Key expires in 1 hour.

        Raises:
            ConnectionError: If the API key limit (10) is exceeded.
            APIError: On other API failures.
        """
        payload = {
            "api_key_name": API_NAME + str(int(time.time())),
            "expires_at": int(time.time() + 3600),
            "roles": [
                "PUBLIC_API_CAMERA_READ_WRITE",
                "PUBLIC_API_SENSORS_READ_WRITE",
                "PUBLIC_API_ACCESS_READ_WRITE",
                "PUBLIC_API_ALARMS_READ_WRITE",
                "PUBLIC_API_CORE_READ_WRITE",
                "PUBLIC_API_HELIX_READ_WRITE",
                "PUBLIC_API_WORKPLACE_READ_WRITE",
                "PUBLIC_API_INTERCOM_READ_WRITE",
                "PUBLIC_API_CAMERA_AUDIO",
            ],
        }
        log_request = f'{{"api_key_name": "{payload["api_key_name"]}"}}'

        try:
            data, status = self._request(
                "org.api_key.create",
                path_params={"org_id": self.org_id},
                json=payload,
                error_context="Failed to create external API key",
                log_request=log_request,
                auto_log=False,
            )
        except APIError as e:
            if e.status_code == 400 and "10 api keys limit" in str(e):
                raise ConnectionError(
                    "Failed to create external API key: exceeded 10 API keys limit."
                )
            raise

        api_key = data.get("apiKey", "")
        self._log(
            "org.api_key.create",
            status,
            path_params={"org_id": self.org_id},
            log_request=log_request,
            log_response=f'{{"apiKey": "{api_key}"}}',
        )
        return api_key

    def get_external_api_key(self) -> list[dict[str, Any]]:
        return self._fetch_list(
            "org.api_key.list",
            response_key="apiKeys",
            path_params={"org_id": self.org_id},
            mapping_func=lambda x: {
                "id": x["apiKeyId"],
                "name": x["apiKeyName"],
            },
        )

    def delete_external_api_key(self, api_key_id: str) -> None:
        self._delete(
            "org.api_key.delete",
            path_params={"org_id": self.org_id, "api_key_id": api_key_id},
            oid=api_key_id,
        )

    # ------------------------------------------------------------------
    # System-wide permissions
    # ------------------------------------------------------------------

    def enable_global_site_admin(self) -> None:
        """Enable globalSiteAdmin: org admins inherit access to all sites."""
        self._set_global_site_admin(True)

    def disable_global_site_admin(self) -> None:
        """Disable globalSiteAdmin: per-site grants required."""
        self._set_global_site_admin(False)

    def enable_access_admin(self) -> None:
        """
        Grant the current user the elevated access-control admin roles
        (ACCESS_CONTROL_SYSTEM_ADMIN + ACCESS_CONTROL_USER_ADMIN) required
        to delete certain access control hardware.

        Two API calls — atomicity note: if the second fails, the user is
        left with SYSTEM_ADMIN but not USER_ADMIN. There's no rollback;
        the caller surfaces the failure and retries.
        """
        self._set_user_permission(
            "permissions.access_system_admin.enable",
            "ACCESS_CONTROL_SYSTEM_ADMIN",
            grant=True,
            label="Access System Admin",
        )
        self._set_user_permission(
            "permissions.access_user_admin.enable",
            "ACCESS_CONTROL_USER_ADMIN",
            grant=True,
            label="Access User Admin",
        )

    # ------------------------------------------------------------------
    # Org Roles/Agreements
    # ------------------------------------------------------------------

    def enable_custom_roles(self) -> None:
        """Enables custom roles for the organization."""
        self._request(
            "org.custom_roles",
            path_params={"org_id": self.org_id},
            json={},
            error_context="Failed to enable custom roles",
        )

    def enable_org_features(self, with_analytics: bool) -> None:
        """
        Sign org agreement(s) and enable feature flags during commissioning.

        Two profiles, selected by the toggle:
          with_analytics=True  → sign LPR + CV_ANALYTICS, enable all 8 flags
          with_analytics=False → sign LPR only, enable the 4 LPR-related flags

        Sequential calls — no rollback. If sign_agreement succeeds but
        org.features fails, the agreement stays signed (idempotent) and
        the caller retries.
        """
        if with_analytics:
            agreements = ["LPR", "CV_ANALYTICS"]
            flags = {
                "ai-summarization": True,
                "face-detection": True,
                "license-plate-recognition": True,
                "natural-language-search": True,
                "people-history": True,
                "person-attributes": True,
                "poi-notifications": True,
                "vehicle-history": True,
            }
        else:
            agreements = ["LPR"]
            flags = {
                "ai-summarization": True,
                "license-plate-recognition": True,
                "natural-language-search": True,
                "vehicle-history": True,
            }

        for key in agreements:
            self._request(
                "org.sign_agreement",
                path_params={"org_id": self.org_id},
                json={"agreementKey": key, "userEmail": self.email},
                error_context=f"Failed to sign {key} agreement",
                log_request=f'{{"agreementKey": "{key}"}}',
            )

        self._request(
            "org.features",
            json={
                "organizationId": self.org_id,
                "params": flags,
                "annotations": {"timestamp": int(time.time()), "userId": self.user_id},
            },
            error_context="Failed to set org features",
            log_request=f'{{"params": "{len(flags)} flags"}}',
        )

    # ------------------------------------------------------------------
    # Sites
    # ------------------------------------------------------------------

    def create_site(self, site_name: str) -> str:
        """
        Creates a camera group (site) in the organization. Returns site_id.
        """
        data, status = self._request(
            "site.create",
            json={"organizationId": self.org_id, "name": site_name},
            error_context=f"Failed to create site '{site_name}'",
            log_request=f'{{"name": "{site_name}"}}',
            auto_log=False,
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

        self._log(
            "site.create",
            status,
            log_request=f'{{"name": "{site_name}"}}',
            log_response=f'{{"cameraGroupId": "{site_id}"}}',
        )
        return site_id

    def get_site(self) -> list[dict[str, Any]]:
        return self._fetch_list(
            "site.list",
            response_key="sites",
            payload={"orgId": self.org_id},
            mapping_func=lambda x: {"id": x["siteId"], "name": x["name"]},
        )

    def delete_site(self, site_id: str) -> None:
        self._delete(
            "site.delete",
            json={"cameraGroupId": site_id},
            oid=site_id,
        )

    # ------------------------------------------------------------------
    # Camera
    # ------------------------------------------------------------------

    def get_camera(self) -> list[dict[str, Any]]:
        """
        Lists all cameras in the org via the device search endpoint.

        Paging is fixed at size=1000: orgs with more than 1000 cameras
        will silently truncate. The endpoint supports cursor paging
        (searchAfter); wire it up if/when the cap becomes a real ceiling.
        """
        return self._fetch_list(
            "camera.list",
            response_key="devices",
            payload={
                "terms": {"deviceType": ["camera"]},
                "sortField": "device_type",
                "sortOrder": "asc",
                "size": 1000,
                "searchAfter": None,
                "deviceTypes": ["camera"],
            },
            mapping_func=lambda x: {
                "id": x["deviceId"],
                "name": x.get("deviceName"),
                "serial_number": x.get("serialNumber"),
                "site_id": x.get("siteId"),
            },
        )

    def configure_camera(
        self,
        camera_id: str,
        camera_name: str,
        site_id: str,
        address: Address,
    ) -> None:
        """
        Sets a camera's display name, site assignment, and location.
        Three calls in sequence — any failure aborts the rest.
        """
        addr = address if isinstance(address, Address) else Address(*address)
        log_req = f'{{"cameraId": "{camera_id}"}}'

        self._request(
            "camera.create.name",
            json={"cameraId": camera_id, "name": camera_name},
            error_context=f"Failed to configure name for camera '{camera_name}'",
            log_request=log_req,
        )
        self._request(
            "camera.create.site",
            json={"cameraIds": [camera_id], "destinationSiteId": site_id},
            error_context=f"Failed to assign camera '{camera_name}' to site",
            log_request=log_req,
        )
        self._request(
            "camera.create.location",
            json={
                "cameraId": camera_id,
                "angle": 0,
                "label": addr.label,
                "lat": addr.latitude,
                "lon": addr.longitude,
            },
            error_context=f"Failed to set location for camera '{camera_name}'",
            log_request=log_req,
        )

    def delete_camera(self, camera_id: str) -> None:
        self._delete("camera.delete", json={"cameraId": camera_id}, oid=camera_id)

    def get_connector(self) -> list[dict[str, Any]]:
        return self._fetch_list(
            "command_connector.list",
            response_key="items",
            payload={"organizationId": self.org_id},
            mapping_func=lambda x: {
                "id": x["deviceId"],
                "name": x["name"],
                "serial_number": x.get("claimedSerialNumber"),
            },
        )

    def configure_connector(
        self,
        device_id: str,
        connector_name: str,
        site_id: str,
        address: Address,
    ) -> None:
        """Configures a Command Connector (vfortress box)."""
        addr = address if isinstance(address, Address) else Address(*address)

        data, status = self._request(
            "command_connector.create",
            json={
                "deviceId": device_id,
                "locationLabel": addr.label,
                "locationLat": addr.latitude,
                "locationLon": addr.longitude,
                "name": connector_name,
                "siteId": site_id,
            },
            error_context=f"Failed to configure connector '{connector_name}'",
            log_request=f'{{"deviceId": "{device_id}"}}',
            auto_log=False,
        )
        if not data.get("deviceId"):
            raise ConnectionError(
                f"Failed to configure connector '{connector_name}': "
                "no deviceId in response."
            )
        self._log(
            "command_connector.create",
            status,
            log_request=f'{{"deviceId": "{device_id}"}}',
        )

    def delete_connector(self, device_id: str) -> None:
        self._delete(
            "command_connector.delete",
            json={"deviceId": device_id, "organizationId": self.org_id},
            oid=device_id,
        )

    def enable_camera_analytics(self, camera_ids: list[str]) -> None:
        """
        Enable analytics (people history, person attributes, face detection)
        on a list of cameras.
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
        Enable LPR on a list of cameras AND set their operating mode to 'lpr'.

        Two phases: one batch feature-flag call, then one config call per
        camera (the operating-mode endpoint accepts only one cameraId).

        Caller must pass only Bullet-model camera IDs; LPR cannot be
        enabled on other camera models.
        """
        self._set_camera_features(
            camera_ids,
            feature_flags={"license-plate-recognition": True},
            feature_label="camera LPR (step 1: feature flag)",
        )
        for camera_id in camera_ids:
            self._request(
                "camera.create.lpr_config",
                json={
                    "cameraId": camera_id,
                    "params": {"camera-config.operating-mode": "lpr"},
                },
                error_context="Failed to enable camera LPR (step 2: operating mode)",
                log_request=f'{{"cameraId": "{camera_id}"}}',
            )

    # ------------------------------------------------------------------
    # Access Control
    # ------------------------------------------------------------------

    def get_access_controller(self) -> list[dict[str, Any]]:
        return self._fetch_list(
            "access_controller.list",
            response_key="accessControllers",
            mapping_func=lambda x: {
                "id": x["accessControllerId"],
                "name": x["name"],
                "serial_number": x["serialNumber"],
            },
        )

    def configure_access_controller(
        self,
        device_id: str,
        controller_name: str,
        site_id: str,
        floor_id: str,
        timezone: str,
    ) -> str:
        """
        Sets up a newly commissioned access controller. Returns the
        accessControllerId used to bind doors via create_door().
        """
        data, status = self._request(
            "access_controller.create",
            json={
                "configs": {"acu-mode": "normal"},
                "deviceId": device_id,
                "enableLte": False,
                "floorId": floor_id,
                "name": controller_name,
                "siteId": site_id,
                "timezone": timezone,
            },
            error_context=f"Failed to configure controller '{controller_name}'",
            log_request=f'{{"deviceId": "{device_id}"}}',
            auto_log=False,
        )
        controller_id = data.get("accessControllerId")
        if not controller_id:
            raise ConnectionError(
                f"Failed to configure controller '{controller_name}': "
                "no accessControllerId returned."
            )
        self._log(
            "access_controller.create",
            status,
            log_request=f'{{"deviceId": "{device_id}"}}',
            log_response=f'{{"accessControllerId": "{controller_id}"}}',
        )
        return controller_id

    def delete_access_controller(self, device_id: str) -> None:
        self._delete(
            "access_controller.delete",
            json={"deviceId": device_id, "sharding": True},
            oid=device_id,
        )

    def create_access_level(
        self, door_id: str, access_level_name: str, site_id: str, group_id: str
    ) -> None:
        """
        Creates a 24/7 access level (schedule) for the given door.

        The weekly ALLOW-all-day event grid comes from the shared
        _DOOR_EVENT default.

        Args:
            group_id: User group to grant access to. Empty string → no groups attached.
        """
        self._request(
            "access_level.create",
            json={
                "defaultDoorLockState": "ACCESS_CONTROL",
                "defaultDoorPermissionState": "DENY",
                "deleted": False,
                "doors": [door_id],
                "endDateTime": None,
                "events": _DOOR_EVENT,
                "name": access_level_name,
                "priority": "SCHEDULE",
                "sites": [site_id],
                "startDateTime": None,
                "type": "USER",
                "userGroups": [group_id] if group_id else [],
            },
            error_context=f"Failed to create access level '{access_level_name}'",
            log_request=f'{{"name": "{access_level_name}"}}',
        )

    def get_access_level(self) -> list[dict[str, Any]]:
        return self._fetch_list(
            "access_level.list",
            response_key="schedules",
            path_params={"org_id": self.org_id},
            mapping_func=lambda x: {
                "id": x["scheduleId"],
                "name": x.get("name"),
                "doors": x.get("doors", []),
            },
        )

    def delete_access_level(self, schedule_id: str) -> None:
        self._delete(
            "access_level.delete",
            path_params={"schedule_id": schedule_id},
            oid=schedule_id,
        )

    def create_access_group(self, group_name: str) -> str:
        """Creates an access (user) group. Returns the new group_id."""
        data, status = self._request(
            "access_group.create",
            json={"organizationId": self.org_id, "groupName": group_name},
            error_context=f"Failed to create access group '{group_name}'",
            log_request=f'{{"groupName": "{group_name}"}}',
            auto_log=False,
        )
        group_id = data.get("groupId")
        if not group_id:
            raise ConnectionError(
                f"Failed to create access group '{group_name}': no groupId in response."
            )
        self._log(
            "access_group.create",
            status,
            log_request=f'{{"groupName": "{group_name}"}}',
            log_response=f'{{"groupId": "{group_id}"}}',
        )
        return group_id

    def get_access_group(self) -> list[dict[str, Any]]:
        """
        Lists access groups. The endpoint returns a `children` map keyed
        by group_id (not a list), so this can't use _fetch_list — flatten
        the map into the standard {id, name} shape here.
        """
        data, status = self._request(
            "access_group.list",
            json={"organizationId": self.org_id},
            error_context="Failed to fetch from access_group.list",
            log_request=f'{{"organizationId": "{self.org_id}"}}',
            auto_log=False,
        )
        children = data.get("children") or {}
        results = [
            {"id": group_id, "name": (info or {}).get("name")}
            for group_id, info in children.items()
        ]
        self._log(
            "access_group.list",
            status,
            log_request=f'{{"organizationId": "{self.org_id}"}}',
            log_response=f'{{"count": {len(results)}}}',
        )
        return results

    def delete_access_group(self, group_id: str) -> None:
        self._delete(
            "access_group.delete",
            json={"groupId": group_id, "organizationId": self.org_id},
            oid=group_id,
        )

    def add_user_to_access_group(self, user_id: str, group_id: str) -> None:
        """Adds a single user to a single access group (batch endpoint, 1-item lists)."""
        self._request(
            "access_group.add_user",
            json={
                "userIds": [user_id],
                "groupIds": [group_id],
                "organizationId": self.org_id,
            },
            error_context=(
                f"Failed to add user '{user_id}' to access group '{group_id}'"
            ),
            log_request=f'{{"userId": "{user_id}", "groupId": "{group_id}"}}',
        )

    def create_building(
        self, building_name: str, address: Address, floors: list
    ) -> str:
        """
        Creates a building with the given address and floor list. Returns
        the first floor_id.
        """
        addr = address if isinstance(address, Address) else Address(*address)

        data, _ = self._request(
            "building.create",
            json={
                "name": building_name,
                "organizationId": self.org_id,
                "address": addr.label,
                "latitude": addr.latitude,
                "longitude": addr.longitude,
                "floors": floors,
            },
            error_context=f"Failed to create building '{building_name}'",
            log_request=f'{{"name": "{building_name}"}}',
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
        return floor_id

    def get_building(self) -> list[dict[str, Any]]:
        return self._fetch_list(
            "building.list",
            response_key="items",
            path_params={"org_id": self.org_id},
            mapping_func=lambda x: {
                "id": x["buildingId"],
                "name": x.get("name"),
                "floors": x.get("floors", []),
            },
        )

    def delete_building(self, building_id: str) -> None:
        """Deletes a building. All of its floors must be deleted first."""
        self._delete(
            "building.delete",
            json={"buildingId": building_id},
            oid=building_id,
        )

    def get_floor(self) -> list[dict[str, Any]]:
        return self._fetch_list(
            "floor.list",
            response_key="items",
            path_params={"org_id": self.org_id},
            mapping_func=lambda x: {
                "id": x["floorId"],
                "name": x.get("name"),
                "building_id": x.get("buildingId"),
            },
        )

    def delete_floor(self, floor_id: str) -> None:
        self._delete(
            "floor.delete",
            json={"floorId": floor_id},
            oid=floor_id,
        )

    def create_door(
        self,
        access_controller_id: str,
        door_name: str,
        floor_id: str,
        *,
        lpr: bool = False,
    ) -> str:
        """
        Creates a door bound to the given access controller. Returns door_id.

        Typically called after configure_controller() (which returns the
        access_controller_id this method needs).

        Args:
            lpr: When True, the door is created with the LPR config set
                (lpr-unlock-enabled). v2 has no retroactive config-flip
                endpoint, so LPR doors must opt in at creation time; pair
                the camera afterward with pair_lpr_camera().
        """
        configs = _LPR_DOOR_CREATE_CONFIGS if lpr else _DOOR_CREATE_CONFIGS
        data, status = self._request(
            "door.create",
            json={
                "accessControllerId": access_controller_id,
                "configs": configs,
                "deviceIos": _DOOR_CREATE_IOS,
                "doorType": "standard",
                "floorId": floor_id,
                "name": door_name,
            },
            error_context=f"Failed to create door '{door_name}'",
            log_request=f'{{"accessControllerId": "{access_controller_id}", "name": "{door_name}"}}',
            auto_log=False,
        )

        doors = data.get("doors") or []
        if not doors:
            raise ConnectionError(
                f"Failed to create door '{door_name}': no doors returned in response."
            )
        door_id = doors[0].get("doorId")
        if not door_id:
            raise ConnectionError(
                f"Failed to create door '{door_name}': no doorId in response."
            )
        self._log(
            "door.create",
            status,
            log_request=f'{{"name": "{door_name}"}}',
            log_response=f'{{"doorId": "{door_id}"}}',
        )
        return door_id

    def get_door(self) -> list[dict[str, Any]]:
        return self._fetch_list(
            "door.list",
            response_key="doors",
            mapping_func=lambda x: {
                "id": x["doorId"],
                "name": x.get("name"),
                "access_controller_id": x.get("accessControllerId"),
                "floor_id": x.get("floorId"),
            },
        )

    def delete_door(self, door_id: str) -> None:
        self._delete(
            "door.delete",
            json={"doorId": door_id},
            oid=door_id,
        )

    def pair_lpr_camera(self, door_id: str, lpr_camera_id: str) -> None:
        """
        Registers an LPR camera as an IO device on a door so plate reads
        can unlock it.

        The door must have been created with lpr=True (its configs already
        carry lpr-unlock-enabled). This is a single call — v2 folds the
        old grant-config step into door creation.
        """
        self._request(
            "door.pair_lpr_camera",
            path_params={"door_id": door_id},
            json={
                "configs": {"lprCameraId": lpr_camera_id},
                "ioDeviceTypeName": "lpr-camera",
                "ioSlotType": "lpr-camera",
                "ioSlotIndex": 0,
            },
            error_context=f"Failed to pair LPR camera with door '{door_id}'",
            log_request=f'{{"lprCameraId": "{lpr_camera_id}"}}',
        )

    def create_visitor_access(
        self, site_id: str, visitor_access_name: str, visitor_access_description: str
    ) -> str:
        """
        Creates a visitor access (visit type) for a site. Returns the
        visitTypeId.

        Only the dynamic fields (site, name, description) are passed; the
        endpoint default fills the rest (roll-call on, all unlock methods
        off, 3-hour max duration).
        """
        data, status = self._request(
            "visitor_access.create",
            json={
                "cardEnabled": False,
                "codeEnabled": False,
                "qrCodeEnabled": False,
                "lpEnabled": False,
                "liveLinkEnabled": False,
                "bleEnabled": False,
                "remoteUnlockEnabled": False,
                "faceUnlockEnabled": False,
                "rollCallEnabled": True,
                "sites": [site_id],
                "doors": [],
                "updatedSchedule": False,
                "rollCallSiteIds": [site_id],
                "maximumDurationSeconds": 10800,
                "schedules": [],
                "directoryId": None,
                "name": visitor_access_name,
                "description": visitor_access_description,
            },
            error_context=(f"Failed to create visitor access '{visitor_access_name}'"),
            log_request=f'{{"name": "{visitor_access_name}"}}',
            auto_log=False,
        )
        visit_type_id = data.get("visitTypeId")
        if not visit_type_id:
            raise ConnectionError(
                f"Failed to create visitor access '{visitor_access_name}': "
                "no visitTypeId in response."
            )
        self._log(
            "visitor_access.create",
            status,
            log_request=f'{{"name": "{visitor_access_name}"}}',
            log_response=f'{{"visitTypeId": "{visit_type_id}"}}',
        )
        return visit_type_id

    def get_visitor_access(self) -> list[dict[str, Any]]:
        return self._fetch_list(
            "visitor_access.list",
            response_key="visitTypes",
            mapping_func=lambda x: {
                "id": x["visitTypeId"],
                "name": x.get("name"),
            },
        )

    def delete_visitor_access(self, visitor_access_id: str) -> None:
        self._delete(
            "visitor_access.delete",
            path_params={"visitor_access_id": visitor_access_id},
            oid=visitor_access_id,
        )

    # ------------------------------------------------------------------
    # Intercoms
    # ------------------------------------------------------------------

    def get_intercom(self) -> list[dict[str, Any]]:
        return self._fetch_list(
            "intercom.list",
            response_key="intercoms",
            path_params={"org_id": self.org_id},
            mapping_func=lambda x: {
                "id": x["deviceId"],
                "name": x["name"],
                "serial_number": x["serialNumber"],
            },
        )

    def delete_intercom(self, device_id: str) -> None:
        self._delete(
            "intercom.delete",
            path_params={"org_id": self.org_id, "object_id": device_id},
            json={"sharding": True},
            oid=device_id,
        )

    def get_desk_station(self) -> list[dict[str, Any]]:
        return self._fetch_list(
            "desk_station.list",
            response_key="deskApps",
            path_params={"org_id": self.org_id},
            mapping_func=lambda x: {
                "id": x["deviceId"],
                "name": x["name"],
                "serial_number": x["serialNumber"],
            },
        )

    def delete_desk_station(self, device_id: str) -> None:
        self._delete(
            "desk_station.delete",
            path_params={"org_id": self.org_id, "object_id": device_id},
            json={"sharding": True},
            oid=device_id,
        )

    # ------------------------------------------------------------------
    # Sensors
    # ------------------------------------------------------------------

    def get_sensor(self) -> list[dict[str, Any]]:
        return self._fetch_list(
            "sensor.list",
            response_key="sensorDevice",
            payload={"organizationId": self.org_id},
            mapping_func=lambda x: {
                "id": x["deviceId"],
                "name": x["name"],
                "serial_number": x["claimedSerialNumber"],
            },
        )

    def delete_sensor(self, device_id: str) -> None:
        self._delete(
            "sensor.delete",
            json={"deviceId": device_id, "sharding": True},
            oid=device_id,
        )

    # ------------------------------------------------------------------
    # Alarms
    # ------------------------------------------------------------------

    # ── Alarm Site ───────────────────────────────────────────────────

    def create_alarm_site(
        self,
        business_name: str,
        alarm_address: AlarmAddress,
        site_id: str,
    ) -> str:
        """
        Creates an alarm response site and enables its software trial.
        Returns the response_config_id from the auto-created response config
        (used for set_alarm_self_monitored and partition response assignment).
        """
        addr = (
            alarm_address
            if isinstance(alarm_address, AlarmAddress)
            else AlarmAddress(*alarm_address)
        )

        # Step 1: create the response site
        data, _ = self._request(
            "alarm.site.create",
            json={
                "organizationId": self.org_id,
                "siteId": site_id,
                "businessName": business_name,
                "permitNumber": "",
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
                "adminContactUserId": self.user_id,
            },
            error_context=f"Failed to configure alarm site for '{business_name}'",
            log_request=f'{{"siteId": "{site_id}"}}',
        )
        response_configs = data.get("responseConfigs") or []
        response_config_id = response_configs[0].get("id") if response_configs else ""

        # Step 2: enable the software trial
        self._request(
            "alarm.site.activate_trial",
            json={"siteId": site_id},
            error_context=f"Failed to enable alarm trial for '{business_name}'",
            log_request=f'{{"siteId": "{site_id}"}}',
        )
        return response_config_id

    def get_alarm_site(self) -> list[dict[str, Any]]:
        """
        Lists alarm (response) sites across the org.

        v2 has no org-wide alarm-site endpoint — alarm.site.list resolves
        one site by siteId — so enumerate the org's sites (site.list) and
        probe each, keeping those that resolve to a response site. Sites
        without an alarm site are skipped silently.

        response_config_id is surfaced in the mapping for callers that
        need it (e.g. set_alarm_self_monitored / partition assignment).
        """
        site_ids = self._fetch_list(
            "site.list",
            response_key="sites",
            payload={"orgId": self.org_id},
            mapping_func=lambda x: x.get("siteId"),
        )

        results: list[dict[str, Any]] = []
        for site_id in site_ids:
            if not site_id:
                continue
            try:
                data, _ = self._request(
                    "alarm.site.list",
                    json={
                        "includeMonthlyAlarmCounts": True,
                        "includePsapInfo": True,
                        "siteId": site_id,
                    },
                    error_context=f"Failed to fetch alarm site for '{site_id}'",
                    log_request=f'{{"siteId": "{site_id}"}}',
                )
            except APIError:
                # Site has no alarm site — skip.
                continue
            response_site = data.get("responseSite") or {}
            if not response_site.get("id"):
                continue
            response_configs = data.get("responseConfigs") or []
            response_config_id = (
                response_configs[0].get("id") if response_configs else None
            )
            results.append(
                {
                    "id": response_site.get("id"),
                    "site_id": response_site.get("siteId"),
                    "alarm_site_id": response_site.get("id"),
                    "name": response_site.get("businessName"),
                    "response_config_id": response_config_id,
                }
            )
        return results

    def delete_alarm_site(self, alarm_site_id: str, site_id: str) -> None:
        """
        Removes an alarm response site. Requires BOTH ids — Command
        identifies alarm sites by (responseSiteId, siteId).
        """
        self._delete(
            "alarm.site.delete",
            json={"siteId": site_id, "responseSiteId": alarm_site_id},
            oid=alarm_site_id,
        )

    def set_alarm_self_monitored(self, site_id: str, response_config_id: str) -> None:
        """Sets an alarm response config to the self-monitored response level."""
        self._request(
            "alarm.site.set_self_monitored",
            json={
                "siteId": site_id,
                "responseConfigId": response_config_id,
                "updateType": "CONFIG_UPDATE_TYPE_UPDATE_RESPONSE_LEVEL",
                "updateResponseLevelInput": {
                    "responseLevel": "RESPONSE_LEVEL_SELF_MONITORED"
                },
            },
            error_context=(f"Failed to set alarm site '{site_id}' to self-monitored"),
            log_request=f'{{"responseConfigId": "{response_config_id}"}}',
        )

    # ── Alarm System ─────────────────────────────────────────────────

    def create_alarm_system(self, site_id: str) -> str:
        """
        Creates an empty alarm system on a site. Returns alarm_system_id.

        Used as a precursor to configure_alarm_panel / configure_keypad,
        which need a system to attach devices to.
        """
        data, status = self._request(
            "alarm.system.create",
            json={"orgId": self.org_id, "siteId": site_id},
            error_context=f"Failed to create alarm system on site '{site_id}'",
            log_request=f'{{"siteId": "{site_id}"}}',
            auto_log=False,
        )
        system_id = (data.get("alarmSystem") or {}).get("id")
        if not system_id:
            raise ConnectionError(
                f"Failed to create alarm system on site '{site_id}': "
                "no system ID in response."
            )
        self._log(
            "alarm.system.create",
            status,
            log_request=f'{{"siteId": "{site_id}"}}',
            log_response=f'{{"alarmSystemId": "{system_id}"}}',
        )
        return system_id

    def get_alarm_system(self) -> list[dict[str, Any]]:
        return self._fetch_list(
            "alarm.system.list",
            response_key="alarmSystems",
            payload={"orgId": self.org_id},
            mapping_func=lambda x: {
                "id": x["id"],
                "site_id": x.get("siteId"),
                "leader_device_id": x.get("leaderDeviceId"),
            },
        )

    def set_alarm_keycode(self, alarm_system_id: str) -> str:
        """
        Creates a general alarm keycode on a site. Returns keycode_id.

        Used as a precursor to configure_alarm_panel / configure_keypad,
        which need a system to attach devices to.
        """
        data, status = self._request(
            "alarm.system.create_general_keycode",
            json={
                "alarmSystemId": alarm_system_id,
                "name": AS_INSTRUCTOR_KEYCODE_NAME,
                "code": AS_INSTRUCTOR_KEYCODE,
                "partitionIds": [],
                "firePermissionScope": "FIRE_PERMISSION_SCOPE_OPERATION",
            },
            error_context=f"Failed to create general keycode on site '{alarm_system_id}'",
            log_request=f'{{"siteId": "{alarm_system_id}"}}',
            auto_log=False,
        )
        keycode_id = (data.get("keycode") or {}).get("id")
        if not keycode_id:
            raise ConnectionError(
                f"Failed to create general keycode on site '{alarm_system_id}': "
                "no keycode ID in response."
            )
        self._log(
            "alarm.system.create_general_keycode",
            status,
            log_request=f'{{"alarm_system_id": "{alarm_system_id}"}}',
            log_response=f'{{"keycode_id": "{keycode_id}"}}',
        )
        return keycode_id

    def delete_alarm_system(self, alarm_system_id: str) -> None:
        self._delete(
            "alarm.system.delete",
            json={"alarmSystemId": alarm_system_id},
            oid=alarm_system_id,
        )

    # ── Alarm Partition ──────────────────────────────────────────────

    def create_alarm_partition(self, alarm_system_id: str, name: str) -> list[str]:
        """Creates a partition on an alarm system.

        Returns:
            list[str]: A list containing [partition_id, alarm_response_id].
        """
        data, status = self._request(
            "alarm.partition.create",
            json={"alarmSystemId": alarm_system_id, "name": name},
            error_context=f"Failed to create alarm partition '{name}'",
            log_request=f'{{"alarmSystemId": "{alarm_system_id}", "name": "{name}"}}',
            auto_log=False,
        )
        partition = data.get("partition") or {}
        partition_id = partition.get("id")
        alarm_response_id = partition.get("responseConfigId")
        if not partition_id:
            raise ConnectionError(
                f"Failed to create alarm partition '{name}': no partition id."
            )
        if not alarm_response_id:
            raise ConnectionError(
                f"Failed to create alarm partition '{name}': no alarm response id."
            )
        self._log(
            "alarm.partition.create",
            status,
            log_request=f'{{"name": "{name}"}}',
            log_response=f'{{"partitionId": "{partition_id}", "alarm_response_id": "{alarm_response_id}"}}',
        )
        return [partition_id, alarm_response_id]

    def assign_alarm_partition_response(
        self, partition_id: str, response_config_id: str
    ) -> None:
        """Binds a partition to an alarm response config."""
        self._request(
            "alarm.partition.assign_response",
            json={
                "partitionId": partition_id,
                "responseConfigId": response_config_id,
            },
            error_context=(
                f"Failed to assign response config to partition '{partition_id}'"
            ),
            log_request=(
                f'{{"partitionId": "{partition_id}", '
                f'"responseConfigId": "{response_config_id}"}}'
            ),
        )

    def get_alarm_partition(self, alarm_system_id: str) -> list[dict[str, Any]]:
        return self._fetch_list(
            "alarm.partition.list",
            response_key="partitions",
            payload={"alarmSystemId": alarm_system_id},
            mapping_func=lambda x: {
                "id": x["id"],
                "name": x.get("name"),
                "response_config_id": x.get("responseConfigId"),
            },
        )

    def delete_alarm_partition(self, partition_id: str) -> None:
        self._delete(
            "alarm.partition.delete",
            json={"partitionId": partition_id},
            oid=partition_id,
        )

    # ── Alarm Guard (camera-based) ───────────────────────────────────

    def create_alarm_guard(
        self,
        site_id: str,
        name: str,
        camera_ids: list[str],
        response_config_id: str,
        timezone: str,
    ) -> str:
        """
        Creates a camera guard on an alarm site. Returns guard_id.

        Guards arm a set of cameras on the fixed overnight _GUARD_SCHEDULES
        window. cameraType defaults to C_M42_SECURE for every camera (the
        documented default); pass only secure-capable cameras.
        """
        data, status = self._request(
            "alarm.guard.create",
            json={
                "siteId": site_id,
                "organizationId": self.org_id,
                "name": name,
                "cameraIds": camera_ids,
                "cameras": [
                    {"cameraId": cid, "cameraType": "C_M42_SECURE"}
                    for cid in camera_ids
                ],
                "schedules": _GUARD_SCHEDULES,
                "responseConfigId": response_config_id,
                "timezoneIana": timezone,
            },
            error_context=f"Failed to create alarm guard '{name}'",
            log_request=f'{{"siteId": "{site_id}", "name": "{name}"}}',
            auto_log=False,
        )
        guard_id = (data.get("guard") or {}).get("id")
        if not guard_id:
            raise ConnectionError(
                f"Failed to create alarm guard '{name}': no guard id in response."
            )
        self._log(
            "alarm.guard.create",
            status,
            log_request=f'{{"name": "{name}"}}',
            log_response=f'{{"guardId": "{guard_id}"}}',
        )
        return guard_id

    def get_alarm_guard(self, site_id: str) -> list[dict[str, Any]]:
        return self._fetch_list(
            "alarm.guard.list",
            response_key="guards",
            payload={"organizationId": self.org_id, "siteId": site_id},
            mapping_func=lambda x: {
                "id": x["id"],
                "name": x.get("name"),
                "camera_ids": x.get("cameraIds", []),
            },
        )

    def delete_alarm_guard(self, guard_id: str) -> None:
        self._delete(
            "alarm.guard.delete",
            json={"guardId": guard_id},
            oid=guard_id,
        )

    # ── Alarm Devices: shared listing ────────────────────────────────

    def _list_alarm_devices(
        self,
        alarm_system_id: str,
        endpoint_key: str,
        *,
        device_type: str | None = None,
    ) -> list[dict[str, Any]]:
        """
        Shared body for the per-type alarm device get_* methods.

        Every alarm device .list key hits the same alarm_system/get_devices
        endpoint and returns ALL devices in the system; filtering by `type`
        client-side is what distinguishes panels from keypads from sensors.
        device_type=None returns every device (used by get_alarm_device).
        """
        data, status = self._request(
            endpoint_key,
            json={"alarmSystemId": alarm_system_id},
            error_context=f"Failed to fetch from {endpoint_key}",
            log_request=f'{{"alarmSystemId": "{alarm_system_id}"}}',
            auto_log=False,
        )
        results = [
            {
                "id": d["id"],
                "name": d.get("name"),
                "serial_number": (d.get("verkadaDeviceConfig") or {}).get(
                    "serialNumber"
                ),
                "type": d.get("type"),
            }
            for d in (data.get("devices") or [])
            if device_type is None or d.get("type") == device_type
        ]
        self._log(
            endpoint_key,
            status,
            log_request=f'{{"alarmSystemId": "{alarm_system_id}"}}',
            log_response=f'{{"count": {len(results)}}}',
        )
        return results

    # ── Alarm Panel ──────────────────────────────────────────────────

    def configure_alarm_panel(
        self,
        device_id: str,
        panel_name: str,
        alarm_system_id: str,
    ) -> None:
        """
        Attaches a commissioned alarm panel to an existing alarm system.
        Use create_alarm_system() first to get the alarm_system_id.
        """
        self._request(
            "alarm.panel.create",
            json={
                "alarmSystemId": alarm_system_id,
                "deviceId": device_id,
                "name": panel_name,
                "replaceExistingLeader": False,
            },
            error_context=f"Failed to configure alarm panel '{panel_name}'",
            log_request=(
                f'{{"deviceId": "{device_id}", "alarmSystemId": "{alarm_system_id}"}}'
            ),
        )

    def get_alarm_panel(self, alarm_system_id: str) -> list[dict[str, Any]]:
        return self._list_alarm_devices(
            alarm_system_id, "alarm.panel.list", device_type="COLOSSUS"
        )

    def delete_alarm_panel(self, device_id: str) -> None:
        self._delete("alarm.panel.delete", json={"deviceId": device_id}, oid=device_id)

    # ── Alarm Keypad ─────────────────────────────────────────────────

    def configure_keypad(
        self,
        device_id: str,
        keypad_name: str,
        alarm_system_id: str,
        serial_number: str,
    ) -> None:
        """Attaches an alarm keypad to an existing alarm system."""
        self._request(
            "alarm.keypad.create",
            json={
                "alarmSystemId": alarm_system_id,
                "deviceId": device_id,
                "name": keypad_name,
                "serialNumber": serial_number,
            },
            error_context=f"Failed to configure alarm keypad '{keypad_name}'",
            log_request=(
                f'{{"deviceId": "{device_id}", "alarmSystemId": "{alarm_system_id}"}}'
            ),
        )

    def get_alarm_keypad(self, alarm_system_id: str) -> list[dict[str, Any]]:
        return self._list_alarm_devices(
            alarm_system_id, "alarm.keypad.list", device_type="SYLVIE"
        )

    def delete_alarm_keypad(self, device_id: str) -> None:
        self._delete("alarm.keypad.delete", json={"deviceId": device_id}, oid=device_id)

    # ── Alarm Expander ───────────────────────────────────────────────

    def configure_alarm_expander(
        self,
        device_id: str,
        expander_name: str,
        alarm_system_id: str,
        serial_number: str,
    ) -> None:
        """Attaches an alarm output expander to an existing alarm system."""
        self._request(
            "alarm.expander.create",
            json={
                "alarmSystemId": alarm_system_id,
                "deviceId": device_id,
                "name": expander_name,
                "serialNumber": serial_number,
            },
            error_context=f"Failed to configure alarm expander '{expander_name}'",
            log_request=(
                f'{{"deviceId": "{device_id}", "alarmSystemId": "{alarm_system_id}"}}'
            ),
        )

    def get_alarm_expander(self, alarm_system_id: str) -> list[dict[str, Any]]:
        return self._list_alarm_devices(
            alarm_system_id, "alarm.expander.list", device_type="KURIBO"
        )

    def delete_alarm_expander(self, device_id: str) -> None:
        self._delete(
            "alarm.expander.delete", json={"deviceId": device_id}, oid=device_id
        )

    # ── Alarm Wireless Devices ───────────────────────────────────────

    def configure_wireless_contact_sensor(
        self,
        device_id: str,
        name: str,
        alarm_system_id: str,
        partition_id: str,
        serial_number: str,
    ) -> None:
        """Attaches a wireless contact (door) sensor to a partition."""
        self._request(
            "alarm.wireless_contact_sensor.create",
            json={
                "alarmSystemId": alarm_system_id,
                "devices": [
                    {
                        "deviceId": device_id,
                        "alarmSystemId": alarm_system_id,
                        "serialNumber": serial_number,
                        "name": name,
                        "partitionId": partition_id,
                        "contactSensorType": "DOOR",
                    }
                ],
            },
            error_context=f"Failed to configure wireless contact sensor '{name}'",
            log_request=f'{{"deviceId": "{device_id}", "name": "{name}"}}',
        )

    def get_wireless_contact_sensor(self, alarm_system_id: str) -> list[dict[str, Any]]:
        return self._list_alarm_devices(
            alarm_system_id,
            "alarm.wireless_contact_sensor.list",
            device_type="WIRELESS_CONTACT_SENSOR",
        )

    def delete_wireless_contact_sensor(self, device_id: str) -> None:
        self._delete(
            "alarm.wireless_contact_sensor.delete",
            json={"deviceId": device_id},
            oid=device_id,
        )

    def configure_wireless_panic_button(
        self,
        device_id: str,
        name: str,
        alarm_system_id: str,
        partition_id: str,
        serial_number: str,
    ) -> None:
        """Attaches a wireless panic button to a partition."""
        self._request(
            "alarm.wireless_panic_button.create",
            json={
                "alarmSystemId": alarm_system_id,
                "devices": [
                    {
                        "deviceId": device_id,
                        "alarmSystemId": alarm_system_id,
                        "serialNumber": serial_number,
                        "name": name,
                        "partitionId": partition_id,
                        "gestureType": "SINGLE_PRESS",
                    }
                ],
            },
            error_context=f"Failed to configure wireless panic button '{name}'",
            log_request=f'{{"deviceId": "{device_id}", "name": "{name}"}}',
        )

    def get_wireless_panic_button(self, alarm_system_id: str) -> list[dict[str, Any]]:
        return self._list_alarm_devices(
            alarm_system_id,
            "alarm.wireless_panic_button.list",
            device_type="WIRELESS_PANIC_BUTTON",
        )

    def delete_wireless_panic_button(self, device_id: str) -> None:
        self._delete(
            "alarm.wireless_panic_button.delete",
            json={"deviceId": device_id},
            oid=device_id,
        )

    def configure_wireless_universal_transmitter(
        self,
        device_id: str,
        name: str,
        alarm_system_id: str,
        partition_id: str,
        serial_number: str,
    ) -> None:
        """Attaches a wireless universal transmitter to a partition."""
        self._request(
            "alarm.wireless_universal_transmitter.create",
            json={
                "alarmSystemId": alarm_system_id,
                "devices": [
                    {
                        "deviceId": device_id,
                        "alarmSystemId": alarm_system_id,
                        "serialNumber": serial_number,
                        "name": name,
                        "partitionId": partition_id,
                    }
                ],
            },
            error_context=(
                f"Failed to configure wireless universal transmitter '{name}'"
            ),
            log_request=f'{{"deviceId": "{device_id}", "name": "{name}"}}',
        )

    def get_wireless_universal_transmitter(
        self, alarm_system_id: str
    ) -> list[dict[str, Any]]:
        return self._list_alarm_devices(
            alarm_system_id,
            "alarm.wireless_universal_transmitter.list",
            device_type="UNIVERSAL_TRANSMITTER",
        )

    def delete_wireless_universal_transmitter(self, device_id: str) -> None:
        self._delete(
            "alarm.wireless_universal_transmitter.delete",
            json={"deviceId": device_id},
            oid=device_id,
        )

    # ── Alarm Wired Devices ──────────────────────────────────────────

    def create_wired_output(
        self, name: str, alarm_system_id: str, panel_id: str, pin_num: int
    ) -> str:
        """Creates a wired generic output on a panel pin. Returns device_id."""
        data, status = self._request(
            "alarm.wired_output.create",
            json={
                "device": {"name": name, "type": "WIRED_GENERIC_OUTPUT"},
                "alarmSystemId": alarm_system_id,
                "hubId": panel_id,
                "pinNum": pin_num,
            },
            error_context=f"Failed to create wired output '{name}'",
            log_request=f'{{"name": "{name}", "pinNum": {pin_num}}}',
            auto_log=False,
        )
        device_id = (data.get("device") or {}).get("id")
        if not device_id:
            raise ConnectionError(
                f"Failed to create wired output '{name}': no device id in response."
            )
        self._log(
            "alarm.wired_output.create",
            status,
            log_request=f'{{"name": "{name}"}}',
            log_response=f'{{"deviceId": "{device_id}"}}',
        )
        return device_id

    def get_wired_output(self, alarm_system_id: str) -> list[dict[str, Any]]:
        return self._list_alarm_devices(
            alarm_system_id,
            "alarm.wired_output.list",
            device_type="WIRED_GENERIC_OUTPUT",
        )

    def delete_wired_output(self, device_id: str) -> None:
        self._delete(
            "alarm.wired_output.delete", json={"deviceId": device_id}, oid=device_id
        )

    def create_wired_input(
        self,
        name: str,
        alarm_system_id: str,
        panel_id: str,
        partition_id: str,
        pin_num: int,
    ) -> str:
        """Creates a wired contact-sensor input on a panel pin. Returns device_id."""
        data, status = self._request(
            "alarm.wired_input.create",
            json={
                "device": {
                    "name": name,
                    "type": "WIRED_CONTACT_SENSOR",
                    "sensorConfig": {
                        "wiredContactSensorConfig": {
                            "type": "DOOR",
                            "doorHeldOpenDelay": 0,
                        }
                    },
                },
                "alarmSystemId": alarm_system_id,
                "partitionId": partition_id,
                "hubId": panel_id,
                "pinNum": pin_num,
                "normalState": "CLOSED",
            },
            error_context=f"Failed to create wired input '{name}'",
            log_request=f'{{"name": "{name}", "pinNum": {pin_num}}}',
            auto_log=False,
        )
        device_id = (data.get("device") or {}).get("id")
        if not device_id:
            raise ConnectionError(
                f"Failed to create wired input '{name}': no device id in response."
            )
        self._log(
            "alarm.wired_input.create",
            status,
            log_request=f'{{"name": "{name}"}}',
            log_response=f'{{"deviceId": "{device_id}"}}',
        )
        return device_id

    def get_wired_input(self, alarm_system_id: str) -> list[dict[str, Any]]:
        return self._list_alarm_devices(
            alarm_system_id,
            "alarm.wired_input.list",
            device_type="WIRED_CONTACT_SENSOR",
        )

    def delete_wired_input(self, device_id: str) -> None:
        self._delete(
            "alarm.wired_input.delete", json={"deviceId": device_id}, oid=device_id
        )

    # ── Alarm Devices: unified accessors (UI compatibility) ──────────

    def get_alarm_device(self) -> list[dict[str, Any]]:
        """
        Lists every alarm device across all of the org's alarm systems.

        v2 has no org-wide device endpoint — alarm_system/get_devices is
        per-system — so list the systems (alarm.system.list) and aggregate
        their devices. Each item carries its `type`, which delete_alarm_device
        needs to pick the right delete endpoint.
        """
        results: list[dict[str, Any]] = []
        for system in self.get_alarm_system():
            results.extend(self._list_alarm_devices(system["id"], "alarm.panel.list"))
        return results

    # ── Org-wide alarm accessors (no system/site arg) ────────────────
    # The per-type getters above all require an alarm_system_id (or
    # site_id for guards/partitions). The decommission scan has neither,
    # so these zero-arg wrappers aggregate across every system/site —
    # mirroring get_alarm_device. They are what constants._INTERNAL_GETTERS
    # points the alarm categories at.

    def _aggregate_over_systems(self, per_system_getter) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        for system in self.get_alarm_system():
            results.extend(per_system_getter(system["id"]))
        return results

    def get_alarm_panel_all(self) -> list[dict[str, Any]]:
        return self._aggregate_over_systems(self.get_alarm_panel)

    def get_alarm_keypad_all(self) -> list[dict[str, Any]]:
        return self._aggregate_over_systems(self.get_alarm_keypad)

    def get_alarm_expander_all(self) -> list[dict[str, Any]]:
        return self._aggregate_over_systems(self.get_alarm_expander)

    def get_wireless_contact_sensor_all(self) -> list[dict[str, Any]]:
        return self._aggregate_over_systems(self.get_wireless_contact_sensor)

    def get_wireless_panic_button_all(self) -> list[dict[str, Any]]:
        return self._aggregate_over_systems(self.get_wireless_panic_button)

    def get_wireless_universal_transmitter_all(self) -> list[dict[str, Any]]:
        return self._aggregate_over_systems(self.get_wireless_universal_transmitter)

    def get_wired_input_all(self) -> list[dict[str, Any]]:
        return self._aggregate_over_systems(self.get_wired_input)

    def get_wired_output_all(self) -> list[dict[str, Any]]:
        return self._aggregate_over_systems(self.get_wired_output)

    def get_alarm_partition_all(self) -> list[dict[str, Any]]:
        return self._aggregate_over_systems(self.get_alarm_partition)

    def get_alarm_guard_all(self) -> list[dict[str, Any]]:
        """Guards are scoped per response site, not per alarm system."""
        results: list[dict[str, Any]] = []
        for site in self.get_alarm_site():
            site_id = site.get("site_id")
            if site_id:
                results.extend(self.get_alarm_guard(site_id))
        return results

    def delete_alarm_device(self, device_id: str, device_type: str) -> None:
        """
        Deletes an alarm device, choosing the delete endpoint from its
        type (panels/keypads/expanders/wireless decommission; wired in/out
        use a different delete path). device_type comes from the `type`
        field surfaced by get_alarm_device.
        """
        key = _ALARM_DEVICE_DELETE_KEYS.get(device_type)
        if not key:
            raise ValueError(
                f"Unknown alarm device type {device_type!r} for device {device_id!r}"
            )
        self._delete(key, json={"deviceId": device_id}, oid=device_id)

    # ------------------------------------------------------------------
    # Workplace
    # ------------------------------------------------------------------

    def create_guest_site(self, guest_address: GuestAddress, site_id: str) -> str:
        """
        Creates a guest (visitor management) site and enables its trial.
        """
        addr = (
            guest_address
            if isinstance(guest_address, GuestAddress)
            else GuestAddress(*guest_address)
        )

        # Step 1: create the guest site
        data, _ = self._request(
            "guest.create",
            path_params={"org_id": self.org_id},
            json={
                "siteId": site_id,
                "fullAddress": addr.full_address,
                "latitude": addr.latitude,
                "longitude": addr.longitude,
                "countryCode": addr.country_code,
            },
            error_context=f"Failed to configure guest site '{site_id}'",
            log_request=f'{{"siteId": "{site_id}"}}',
        )
        guest_site_id = data.get("siteId") or ""

        # Step 2: enable the guest trial
        self._request(
            "guest.activate_trial",
            path_params={"org_id": self.org_id, "site_id": site_id},
            json={"productType": "GUEST"},
            error_context=f"Failed to enable guest trial for '{site_id}'",
            log_request=f'{{"siteId": "{site_id}"}}',
        )
        return guest_site_id

    def delete_guest_site(self, site_id: str) -> None:
        self._delete(
            "guest.delete",
            path_params={"org_id": self.org_id, "site_id": site_id},
            oid=site_id,
        )

    def create_mailroom_site(self, site_id: str, address: Address) -> str:
        """
        Activates the org mailroom trial, then creates a mailroom (package)
        site. Returns the packageLocationId.

        The trial is org-level (one-time) and re-runs harmlessly on each
        call; site creation is per-site.
        """
        addr = address if isinstance(address, Address) else Address(*address)

        # Step 1: activate the org-level mailroom trial
        self._request(
            "mailroom.activate_trial",
            path_params={"org_id": self.org_id},
            json={},
            error_context="Failed to activate mailroom trial",
            log_request=f'{{"organizationId": "{self.org_id}"}}',
        )

        # Step 2: create the mailroom site
        data, status = self._request(
            "mailroom.create",
            path_params={"org_id": self.org_id},
            json={
                "siteId": site_id,
                "latitude": addr.latitude,
                "longitude": addr.longitude,
                "fullAddress": addr.label,
            },
            error_context=f"Failed to create mailroom site on '{site_id}'",
            log_request=f'{{"siteId": "{site_id}"}}',
            auto_log=False,
        )
        location_id = data.get("packageLocationId")
        if not location_id:
            raise ConnectionError(
                f"Failed to create mailroom site on '{site_id}': "
                "no packageLocationId in response."
            )
        self._log(
            "mailroom.create",
            status,
            path_params={"org_id": self.org_id},
            log_request=f'{{"siteId": "{site_id}"}}',
            log_response=f'{{"packageLocationId": "{location_id}"}}',
        )
        return location_id

    def get_mailroom_site(self) -> list[dict[str, Any]]:
        return self._fetch_list(
            "mailroom.list",
            response_key="package_sites",
            path_params={"org_id": self.org_id},
            mapping_func=lambda x: {"id": x["siteId"], "name": x["siteName"]},
        )

    def delete_mailroom_site(self, site_id: str) -> None:
        self._delete(
            "mailroom.delete",
            path_params={"org_id": self.org_id, "site_id": site_id},
            oid=site_id,
        )
