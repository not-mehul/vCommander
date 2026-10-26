import json
import re
import time
from typing import Any, NamedTuple

import requests
from requests.exceptions import JSONDecodeError, RequestException

from apis.endpoints import (
    _ACCESS_STATION_PRO_DOOR_CREATE_CONFIGS,
    _DOOR_CREATE_CONFIGS,
    _DOOR_CREATE_IOS,
    _DOOR_EVENT,
    _LPR_DOOR_CREATE_CONFIGS,
    _MFA_DOOR_EVENT,
    DEFAULT_SHARD,
    Address,
    AlarmAddress,
    GuestAddress,
    MFARequiredError,
    OrgShard,
    build_url,
    resolve,
)
from apis.http import build_session
from constants import (
    API_NAME,
    AS_INSTRUCTOR_KEYCODE,
    AS_INSTRUCTOR_KEYCODE_NAME,
    DEFAULT_TIMEOUT,
    DEV_SKIP_LOGIN,
    INTERNAL_PAGE_SIZE,
    SEARCH_DURATION,
)
from utils.logger import log_api_call


class OrgNotFoundError(ValueError):
    """org/validate_short_name doesn't know the org short name."""


# A hostname (or label) as returned in shard host metadata. Anything else is
# rejected rather than spliced into request URLs.
_HOSTNAME = re.compile(r"^[a-z0-9]([a-z0-9-]*[a-z0-9])?(\.[a-z0-9]([a-z0-9-]*[a-z0-9])?)*$")


def validate_org_short_name(
    org_short_name: str, session: requests.Session | None = None
) -> OrgShard:
    """Look up which shard hosts an org (pre-auth, shard-independent).

    POSTs org/validate_short_name on the global vglobal service. The
    response names the shard and its host metadata, from which every
    internal and public-API host for the org is built.

    Raises:
        OrgNotFoundError: the short name isn't a known org (4xx, or a 2xx
            without shard details).
        ConnectionError: transport failure, a 5xx, or malformed host data.
    """
    endpoint, path = resolve("org.validate_short_name")
    url = build_url(endpoint, org_short_name, path)
    log_label = f"{org_short_name}/{path}"
    session = session or build_session()
    try:
        response = session.post(
            url, json={"orgShortName": org_short_name}, timeout=DEFAULT_TIMEOUT
        )
    except RequestException as e:
        raise ConnectionError(f"Couldn't look up org '{org_short_name}': {e}") from e

    try:
        data = response.json() if response.content else {}
    except JSONDecodeError:
        data = {}
    shard = data.get("shard") if isinstance(data, dict) else None
    shard_info = shard if isinstance(shard, dict) else {}
    log_api_call(
        "POST",
        log_label,
        f'{{"orgShortName": "{org_short_name}"}}',
        str(response.status_code),
        json.dumps(
            {
                "shard": shard_info.get("name"),
                "region": shard_info.get("readable_name"),
                "host_metadata": shard_info.get("host_metadata"),
            }
        ),
    )
    if response.status_code >= 500:
        raise ConnectionError(
            f"Couldn't look up org '{org_short_name}' (HTTP {response.status_code})."
        )
    if not response.ok or not isinstance(shard, dict):
        raise OrgNotFoundError(f"No Verkada org named '{org_short_name}' was found.")

    hosts = shard.get("host_metadata") or {}
    result = OrgShard(
        name=str(shard.get("name") or ""),
        domain=str(hosts.get("domain") or ""),
        api_gateway_endpoint=str(hosts.get("api_gateway_endpoint") or "api"),
        public_api_endpoint=str(hosts.get("public_api_endpoint") or "apiadmin"),
        readable_name=str(shard.get("readable_name") or ""),
        org_name=str(data.get("name") or ""),
    )
    # public_api_endpoint isn't used to build any host, so it isn't checked.
    for label in (result.domain, result.api_gateway_endpoint):
        if not _HOSTNAME.match(label):
            raise ConnectionError(
                f"Org lookup for '{org_short_name}' returned an unusable host "
                f"({label!r})."
            )
    if not result.name:
        raise ConnectionError(
            f"Org lookup for '{org_short_name}' returned no shard name."
        )
    return result


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


class ExternalApiKey(NamedTuple):
    """A freshly minted public-API key plus the id needed to delete it."""

    key: str
    key_id: str | None


# Wired-input device `type` strings. All of these are created on a panel
# pin, listed by alarm.wired_input.list, and decommissioned via
# alarm.wired_input.delete. Only WIRED_CONTACT_SENSOR carries an extra
# sensorConfig; the rest send just name + type.
_WIRED_INPUT_TYPES = (
    "WIRED_CONTACT_SENSOR",
    "WIRED_GLASS_BREAK_SENSOR",
    "WIRED_MOTION_SENSOR",
    "WIRED_GENERIC_SENSOR",
    "WIRED_PANIC_BUTTON",
    "WIRED_WATER_LEAK_SENSOR",
)

# Alarm device `type` strings (returned by alarm_system/get_devices) mapped
# to the v2 delete endpoint key for that device. Panels/keypads/expanders/
# wireless decommission; wired in/out use a different delete path. Every
# wired-input subtype shares the one alarm.wired_input.delete endpoint.
_ALARM_DEVICE_DELETE_KEYS = {
    "COLOSSUS": "alarm.panel.delete",
    "SYLVIE": "alarm.keypad.delete",
    "KURIBO": "alarm.expander.delete",
    "WIRELESS_CONTACT_SENSOR": "alarm.wireless_contact_sensor.delete",
    "WIRELESS_PANIC_BUTTON": "alarm.wireless_panic_button.delete",
    "UNIVERSAL_TRANSMITTER": "alarm.wireless_universal_transmitter.delete",
    "WIRED_GENERIC_OUTPUT": "alarm.wired_output.delete",
    **{t: "alarm.wired_input.delete" for t in _WIRED_INPUT_TYPES},
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
        self,
        email: str,
        password: str,
        org_short_name: str,
        shard: OrgShard | None = None,
    ):
        self.email = email
        self.password = password
        self.org_short_name = org_short_name
        # Where the org is hosted. Resolved from org/validate_short_name by
        # login() unless given; every request URL is built from it.
        self.shard = shard

        # Persistent session keeps cookies alive across requests; the shared
        # factory adds retry on transient failures + a default timeout.
        self.session = build_session()

        # Populated by _parse_login_response() after successful auth
        self.auth_data: dict[str, str] | None = None

        # Saved during login() so verify_mfa() can replay the same payload
        self._pending_payload: dict | None = None

        # Populated when login() raises MFARequiredError so the 2FA screen
        # can prompt for the right factor (SMS vs authenticator/QR) and
        # offer a resend. None/False until an MFA challenge is seen.
        self.mfa_sms_enabled: bool = False
        self.mfa_sms_contact: str | None = None

    # ------------------------------------------------------------------
    # Identity helpers
    # ------------------------------------------------------------------

    @property
    def host_shard(self) -> OrgShard:
        """The resolved shard, or the default US shard before resolution."""
        return self.shard or DEFAULT_SHARD

    @property
    def public_api_region(self) -> str:
        """Public-API host label for this org's region ("api", "api.eu", …)."""
        return self.host_shard.public_api_region

    def resolve_shard(self) -> OrgShard:
        """Look up (once) which shard hosts this org."""
        if self.shard is None:
            self.shard = validate_org_short_name(self.org_short_name, self.session)
        return self.shard

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
            raise ValueError(
                f"Unexpected login response format, missing key: {e}"
            ) from e

    def _login_url(self) -> str:
        """Pre-auth helper: build the login URL from the registry."""
        endpoint, formatted_path = resolve("login")
        return build_url(endpoint, self.org_short_name, formatted_path, self.host_shard)

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

    def _set_door_config(
        self,
        endpoint_key: str,
        door_id: str,
        param_name: str,
        feature_label: str,
    ) -> None:
        """
        Grant a single boolean door config param (POST door/config/set).

        Backs the face-unlock and MFA toggles: those endpoint keys are the
        same call with a different paramName, so callers name the key and
        the param and this carries the payload shape.
        """
        self._request(
            endpoint_key,
            json={
                "doorId": door_id,
                "action": "grant",
                "paramName": param_name,
                "paramValue": True,
            },
            error_context=f"Failed to enable {feature_label} on door '{door_id}'",
            log_request=f'{{"doorId": "{door_id}", "paramName": "{param_name}"}}',
        )

    def _create_door(
        self,
        endpoint_key: str,
        *,
        access_controller_id: str,
        door_name: str,
        floor_id: str,
        configs: list[dict[str, Any]],
        door_type: str,
    ) -> str:
        """
        Shared body for every door-creating method. Returns the new door_id.

        The door endpoints differ only in config profile and doorType (a
        standard door hangs off an access controller; a Access Station Pro
        door is the station acting as its own controller).
        """
        log_req = (
            f'{{"accessControllerId": "{access_controller_id}", "name": "{door_name}"}}'
        )
        data, status = self._request(
            endpoint_key,
            json={
                "accessControllerId": access_controller_id,
                "configs": configs,
                "deviceIos": _DOOR_CREATE_IOS,
                "doorType": door_type,
                "floorId": floor_id,
                "name": door_name,
            },
            error_context=f"Failed to create door '{door_name}'",
            log_request=log_req,
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
            endpoint_key,
            status,
            log_request=f'{{"name": "{door_name}"}}',
            log_response=f'{{"doorId": "{door_id}"}}',
        )
        return door_id

    def _fetch_list(
        self,
        endpoint_key: str,
        *,
        response_key: str,
        mapping_func,
        path_params: dict | None = None,
        payload: dict | None = None,
        filter_func=None,
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
        if filter_func is not None:
            items = [item for item in items if filter_func(item)]
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
        url = build_url(endpoint, self.org_short_name, formatted_path, self.host_shard)

        try:
            response = self.session.request(
                endpoint.method,
                url,
                json=json,
                headers=self._get_headers(),
                timeout=DEFAULT_TIMEOUT,
            )
        except RequestException as e:
            raise ConnectionError(f"{error_context}: {e}") from e

        # Tolerate empty bodies (some DELETEs and a few POSTs return nothing).
        if response.content:
            try:
                data = response.json()
            except JSONDecodeError:
                if not response.ok:
                    raise APIError(
                        f"{error_context}: {response.text or 'non-JSON response.'}",
                        status_code=response.status_code,
                    ) from None
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
            ) from None
        except RequestException as e:
            raise ConnectionError(f"{error_label}: {e}") from e
        return data, response.status_code

    def _send_mfa_sms(self) -> str | None:
        """
        Dispatch an SMS 2FA code and return the masked destination digits.

        Posts to vauth's auth/twofactor/sms/new with the login credentials.
        Runs pre-auth (no session tokens yet), so like login()/verify_mfa()
        it can't go through _request. Returns the masked digits (e.g.
        "7647") on success, or None if the response omitted them.

        Raises ConnectionError on transport or decode failure so callers can
        decide whether a send failure should block the 2FA challenge.
        """
        endpoint, formatted_path = resolve("auth.twofactor.sms.new")
        url = build_url(endpoint, self.org_short_name, formatted_path, self.host_shard)
        payload = {
            "email": self.email,
            "password": self.password,
            "orgShortName": self.org_short_name,
        }
        log_label = f"{self.org_short_name}/{formatted_path}"
        log_request = f'{{"email": "{self.email}"}}'

        try:
            response = self.session.post(url, json=payload, timeout=DEFAULT_TIMEOUT)
            data = response.json()
        except JSONDecodeError:
            log_api_call("POST", log_label, log_request, "200", "non-JSON response")
            raise ConnectionError(
                "Failed to send SMS code: server returned a non-JSON response."
            ) from None
        except RequestException as e:
            raise ConnectionError(f"Failed to send SMS code: {e}") from e

        sms_sent = data.get("smsSent") if isinstance(data, dict) else None
        log_api_call(
            "POST",
            log_label,
            log_request,
            str(response.status_code),
            f'{{"smsSent": "{sms_sent}"}}',
        )
        return sms_sent

    def resend_mfa_sms(self) -> str | None:
        """
        Re-send the SMS 2FA code (used by the 2FA screen's resend action).

        Only valid mid-login, after login() has raised MFARequiredError for
        an SMS-enabled org. Returns and caches the masked destination digits.
        """
        if not self._pending_payload:
            raise ValueError("No pending login. Call login() first.")
        contact = self._send_mfa_sms()
        self.mfa_sms_contact = contact or self.mfa_sms_contact
        return self.mfa_sms_contact

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

        # Route the login (and everything after it) to the org's shard.
        shard = self.resolve_shard()
        payload = {
            "email": self.email,
            "orgShortName": self.org_short_name,
            "termsAcked": False,
            "password": self.password,
            "loginMethod": "password",
            "shard": shard.name,
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
            mfa_data = data.get("data") or {}
            sms_enabled = bool(mfa_data.get("smsEnabled"))
            qr_enabled = bool(mfa_data.get("qrEnabled"))
            sms_contact = mfa_data.get("smsSent")

            # The login response no longer dispatches the SMS itself nor
            # carries the destination digits. When SMS is a configured
            # factor we must hit auth/twofactor/sms/new to send the code
            # (and learn the masked number). QR/authenticator orgs need no
            # send — the user already has a rolling code. A send failure is
            # non-fatal: an org may also offer QR, and the 2FA screen can
            # retry via resend, so we still surface the challenge.
            if sms_enabled:
                try:
                    sms_contact = self._send_mfa_sms() or sms_contact
                except ConnectionError as e:
                    log_api_call(
                        "POST", log_label, log_request, "sms_send_failed", str(e)
                    )

            self.mfa_sms_enabled = sms_enabled
            self.mfa_sms_contact = sms_contact

            log_api_call("POST", log_label, log_request, f"{status} (MFA)", msg)
            raise MFARequiredError(
                "MFA Required",
                sms_contact,
                sms_enabled=sms_enabled,
                qr_enabled=qr_enabled,
            )

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
                raise ValueError(f"User already exists in this org: {email}") from e
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

    def create_external_api_key(self) -> ExternalApiKey:
        """
        Generates a temporary External API Key (used to initialize the
        VerkadaExternalAPIClient). Key expires in 1 hour, but callers should
        delete it with delete_external_api_key(key_id) once their run ends:
        an org holds at most 10 keys, so leftovers block the next run.

        Returns:
            ExternalApiKey(key, key_id). key_id is taken from the create
            response, falling back to a lookup by the (unique) key name; it
            is None only if neither source has it.

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
                ) from e
            raise

        api_key = data.get("apiKey", "")
        key_id = data.get("apiKeyId")
        self._log(
            "org.api_key.create",
            status,
            path_params={"org_id": self.org_id},
            log_request=log_request,
            log_response=f'{{"apiKey": "{api_key}", "apiKeyId": "{key_id}"}}',
        )
        if not key_id:
            # Best effort: the key already exists, so a failed lookup must not
            # fail the create (the caller would then never delete the key).
            key_name = payload["api_key_name"]
            try:
                key_id = next(
                    (k["id"] for k in self.get_external_api_key() if k["name"] == key_name),
                    None,
                )
            except (ConnectionError, PermissionError, KeyError):
                key_id = None
        return ExternalApiKey(api_key, key_id)

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

    def enable_org_face_unlock(self) -> None:
        """
        Allow face unlock across the organization.

        Org-level prerequisite for the per-door toggle — a door's
        face-unlock-enabled config (enable_door_face_unlock) only takes
        effect once the org flag is set.
        """
        self._request(
            "org.allow_face_unlock",
            json={
                "organizationId": self.org_id,
                "paramName": "face-unlock-enabled",
                "paramValue": True,
            },
            error_context="Failed to allow face unlock for the organization",
            log_request='{"paramName": "face-unlock-enabled"}',
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

    def create_or_reuse_site(self, site_name: str) -> str:
        """Create a site, or return the id of an existing one with that name.

        Command never allows two sites with the same name under one parent
        ("A sub-site with the name 'HQ' already exists under the same parent
        site."). Most templates name their site "HQ", so commissioning a
        second template into the same org would otherwise fail here and leave
        its devices outside any site (where, with Global Site Admin off, later
        camera calls are refused with "error authorizing user access").
        """
        try:
            return self.create_site(site_name)
        except ConnectionError as ex:
            if "already exists" not in str(ex).lower():
                raise
            for site in self.get_site():
                if site["name"] == site_name:
                    return site["id"]
            raise

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

    def rename_site(self, site_id: str, new_name: str) -> None:
        """Renames a site (camera group).

        Used as the decommission fallback when site deletion fails —
        renaming frees the original name for future commissioning runs.
        """
        self._request(
            "site.rename",
            json={"cameraGroupId": site_id, "name": new_name},
            error_context=f"Failed to rename site '{site_id}' to '{new_name}'",
            log_request=f'{{"cameraGroupId": "{site_id}", "name": "{new_name}"}}',
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

    def disable_camera_install_mode(self, camera_ids: list[str]) -> None:
        """
        Disable Install mode on a list of cameras.

        Caller must pass only PTZ-model camera IDs; Install Mode cannot be
        disabled on other camera models.
        """
        self._request(
            "camera.create.ptz_install_disable",
            json={
                "cameraIds": camera_ids,
                "params": {
                    "peripheral-motor-ctrl.disable-pan-tilt": False
                },
                "consumable": False
            },
        error_context="Failed to disable install mode on PTZ",
        log_request=f'{{"cameraId": "{camera_ids}"}}')

    # ------------------------------------------------------------------
    # Access Control
    # ------------------------------------------------------------------

    # Access Station Pros are surfaced by the same access_controllers
    # endpoint as regular controllers, tagged with vconductorModelId
    # "MOODY". The two getters partition that shared list so a device is
    # never handled as both an access controller and an access station.
    _ACCESS_STATION_PRO_MODEL = "MOODY"

    def get_access_controller(self) -> list[dict[str, Any]]:
        return self._fetch_list(
            "access_controller.list",
            response_key="accessControllers",
            filter_func=lambda x: (
                x.get("vconductorModelId") != self._ACCESS_STATION_PRO_MODEL
            ),
            mapping_func=lambda x: {
                "id": x["accessControllerId"],
                "name": x["name"],
                "serial_number": x["serialNumber"],
            },
        )

    def get_access_station_pro(self) -> list[dict[str, Any]]:
        """Lists Access Station Pro devices (vconductorModelId == MOODY)."""
        return self._fetch_list(
            "access_station_pro.list",
            response_key="accessControllers",
            filter_func=lambda x: (
                x.get("vconductorModelId") == self._ACCESS_STATION_PRO_MODEL
            ),
            mapping_func=lambda x: {
                "id": x["accessControllerId"],
                "name": x.get("name"),
                "serial_number": x.get("serialNumber"),
            },
        )

    def configure_access_station_pro(
        self,
        device_id: str,
        station_name: str,
        site_id: str,
        address: Address,
    ) -> str:
        """
        Sets up a newly commissioned Access Station Pro. Returns the
        accessControllerId used to bind a door via
        create_access_station_pro_door().

        The station doubles as its own access controller, so the setup
        response carries both a deviceId and an accessControllerId — doors
        bind to the latter.
        """
        addr = address if isinstance(address, Address) else Address(*address)
        log_req = f'{{"deviceId": "{device_id}"}}'
        data, status = self._request(
            "access_station_pro.create",
            json={
                "deviceId": device_id,
                "name": station_name,
                "siteId": site_id,
                "location": {
                    "label": addr.label,
                    "lat": addr.latitude,
                    "lon": addr.longitude,
                },
            },
            error_context=f"Failed to configure Access Station Pro '{station_name}'",
            log_request=log_req,
            auto_log=False,
        )
        controller_id = data.get("accessControllerId")
        if not controller_id:
            raise ConnectionError(
                f"Failed to configure Access Station Pro '{station_name}': "
                "no accessControllerId returned."
            )
        self._log(
            "access_station_pro.create",
            status,
            log_request=log_req,
            log_response=f'{{"accessControllerId": "{controller_id}"}}',
        )
        return controller_id

    def delete_access_station_pro(self, device_id: str) -> None:
        self._delete(
            "access_station_pro.delete",
            json={"deviceId": device_id, "sharding": True},
            oid=device_id,
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
        """
        Lists access levels. Door schedules (type DOOR) and supervisor
        schedules (other types) come back from the SAME endpoint
        (organizations/{org_id}/schedules) but cannot be deleted through
        access_level.delete — only type USER is accepted. Include
        untyped items so legacy access levels still surface.
        """
        return self._fetch_list(
            "access_level.list",
            response_key="schedules",
            path_params={"org_id": self.org_id},
            filter_func=lambda x: x.get("type") in (None, "USER"),
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

    def create_mfa_schedule(self, door_id: str, schedule_name: str) -> None:
        """
        Creates a 24/7 door schedule that holds the door in two-factor
        mode (doorLockState ACCESS_CONTROL_2FA).

        The weekly event grid comes from the shared _MFA_DOOR_EVENT
        default. Pair with the per-door MFA toggles: this schedule sets
        *when* two-factor applies, while enable_door_mfa_* sets *which*
        credential combination satisfies it.

        Shares the upsert-style PUT that delete_schedule uses — schedules
        are keyed by scheduleId, so an object sent without one is created
        rather than replacing the org's existing schedules.
        """
        self._request(
            "schedule.create.mfa",
            path_params={"org_id": self.org_id},
            json={
                "sitesEnabled": True,
                "schedules": [
                    {
                        "doors": [door_id],
                        "events": _MFA_DOOR_EVENT,
                        "name": schedule_name,
                        "type": "DOOR",
                        "priority": "SCHEDULE",
                        "defaultDoorLockState": "ACCESS_CONTROL",
                    }
                ],
            },
            error_context=f"Failed to create MFA schedule '{schedule_name}'",
            log_request=f'{{"name": "{schedule_name}", "doorId": "{door_id}"}}',
        )

    def get_schedule(self) -> list[dict[str, Any]]:
        """
        Lists door schedules (type DOOR) from the shared
        organizations/{org_id}/schedules listing (access levels, type
        USER, come from get_access_level via the same endpoint).

        schedule.delete is an upsert-style PUT that echoes the entire
        schedule object back with deleted=True, so each result carries
        the full raw object(s) needed to delete it in `delete_objects`:
        the DOOR schedule plus its paired SUPERVISOR schedule (when
        supervisorScheduleId is set) — the two must be deleted together
        in one call or the server rejects it. Supervisor schedules are
        never surfaced on their own; they belong to a door schedule.
        """
        data, status = self._request(
            "schedule.list",
            path_params={"org_id": self.org_id},
            error_context="Failed to fetch from schedule.list",
            log_request=f'{{"organizationId": "{self.org_id}"}}',
            auto_log=False,
        )
        raw = data.get("schedules", [])
        by_id = {s.get("scheduleId"): s for s in raw}

        results: list[dict[str, Any]] = []
        for sched in raw:
            if sched.get("type") != "DOOR":
                continue
            delete_objects = [sched]
            sup_id = sched.get("supervisorScheduleId")
            if sup_id and sup_id in by_id:
                delete_objects.append(by_id[sup_id])
            results.append(
                {
                    "id": sched.get("scheduleId"),
                    "name": sched.get("name"),
                    # Full raw object(s) echoed back on delete; consumed
                    # by delete_schedule. Not shown in the UI.
                    "delete_objects": delete_objects,
                }
            )
        self._log(
            "schedule.list",
            status,
            # path_params are required: schedule.list's path has an
            # {org_id} placeholder that _log -> resolve must substitute.
            path_params={"org_id": self.org_id},
            log_request=f'{{"organizationId": "{self.org_id}"}}',
            log_response=f'{{"count": {len(results)}}}',
        )
        return results

    def delete_schedule(self, delete_objects: list[dict[str, Any]]) -> None:
        """
        Deletes door schedule(s) via the upsert-style PUT. The endpoint
        requires the FULL schedule object echoed back verbatim with
        deleted=True (events, type, ids, timestamps, …) — a minimal body
        is rejected with "Missing data for required field". A door
        schedule that has a paired supervisor schedule must include BOTH
        objects in the same call. `delete_objects` comes straight from
        get_schedule's `delete_objects`.
        """
        if not delete_objects:
            raise ValueError("delete_schedule requires at least one schedule object")
        payload = [{**obj, "deleted": True} for obj in delete_objects]
        self._delete(
            "schedule.delete",
            path_params={"org_id": self.org_id},
            json={"sitesEnabled": True, "schedules": payload},
            oid=delete_objects[0].get("scheduleId", ""),
        )

    def get_scenario(self) -> list[dict[str, Any]]:
        """Lists access scenarios (lockdowns: EVACUATE/SHELTER/etc.)."""
        return self._fetch_list(
            "scenario.list",
            response_key="lockdowns",
            path_params={"org_id": self.org_id},
            mapping_func=lambda x: {
                "id": x["lockdownId"],
                "name": x.get("name"),
                "type": x.get("scenarioType"),
            },
        )

    def delete_scenario(self, scenario_id: str) -> None:
        self._delete(
            "scenario.delete",
            path_params={"scenario_id": scenario_id},
            oid=scenario_id,
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

    # ------------------------------------------------------------------
    # Security entity groups, access users, footage archives,
    # investigation incidents, and alert rules
    # ------------------------------------------------------------------

    def create_group(self, group_name: str) -> str:
        """
        Creates a security entity group (a Command group). Returns the new
        group_id.

        Distinct from create_access_group: access groups gate door access,
        Command groups gate Command permissions.
        """
        log_req = f'{{"name": "{group_name}"}}'
        data, status = self._request(
            "group.create",
            json={"organizationId": self.org_id, "name": group_name},
            error_context=f"Failed to create group '{group_name}'",
            log_request=log_req,
            auto_log=False,
        )
        # The new group comes back under securityEntityGroup — the list
        # schema this endpoint shares with group.list, collapsed to the one
        # created group. Tolerate a bare object in case it isn't wrapped.
        entity = data.get("securityEntityGroup") or {}
        if isinstance(entity, list):
            entity = entity[0] if entity else {}
        group_id = entity.get("entityGroupId") or data.get("entityGroupId")
        if not group_id:
            raise ConnectionError(
                f"Failed to create group '{group_name}': no entityGroupId in response."
            )
        self._log(
            "group.create",
            status,
            log_request=log_req,
            log_response=f'{{"entityGroupId": "{group_id}"}}',
        )
        return group_id

    def add_users_to_group(self, user_ids: list[str], group_id: str) -> None:
        """Adds one or more users to a security entity group."""
        self._request(
            "group.add_members",
            json={
                "securityEntityGroupId": group_id,
                "securityEntityIds": user_ids,
            },
            error_context=f"Failed to add users to group '{group_id}'",
            log_request=f'{{"groupId": "{group_id}", "userIds": {user_ids}}}',
        )

    def get_group(self) -> list[dict[str, Any]]:
        """List security entity groups the user can delete.

        Verkada-managed groups are system defaults, so only groups with
        `verkadaManaged` falsy are surfaced (the rest are ignored).
        """
        return self._fetch_list(
            "group.list",
            response_key="securityEntityGroup",
            payload={
                "organizationId": self.org_id,
                "includeMembers": True,
                "includeMemberCount": False,
            },
            filter_func=lambda g: not g.get("verkadaManaged", False),
            mapping_func=lambda g: {
                "id": g["entityGroupId"],
                "name": g.get("name"),
            },
        )

    def delete_group(self, group_id: str) -> None:
        """Delete a single security entity group (endpoint accepts a list)."""
        self._delete(
            "group.delete",
            json={"securityEntityGroupIds": [group_id]},
            oid=group_id,
        )

    def get_visitor(self) -> list[dict[str, Any]]:
        """List visitors — access users flagged is_visitor — with granted
        access. One page of INTERNAL_PAGE_SIZE (decommission re-lists until
        empty, see PAGED_CATEGORIES). Deleted after Visits and before
        Command Users.
        """
        return self._fetch_list(
            "visitor.list",
            response_key="users",
            payload={
                "organizationId": self.org_id,
                "must_queries": [
                    {"bool": {"must": [{"term": {"is_visitor": True}}]}}
                ],
                "status": ["access_granted"],
                "status_filter_v2": True,
                "paging": {
                    "pageSize": INTERNAL_PAGE_SIZE,
                    "sortOrder": ["first_name:asc", "email:asc"],
                },
            },
            mapping_func=lambda u: {"id": u["userId"], "name": u.get("name")},
        )

    def delete_visitor(self, visitor_id: str) -> None:
        """Delete a single visitor (endpoint accepts a list of userIds)."""
        self._delete(
            "visitor.delete",
            json={"organizationId": self.org_id, "userIds": [visitor_id]},
            oid=visitor_id,
        )

    def get_visit(self) -> list[dict[str, Any]]:
        """List active visits (one page of INTERNAL_PAGE_SIZE).

        Visits reference visitors, so they are deleted first — before
        Visitors and Command Users.
        """
        return self._fetch_list(
            "visit.list",
            response_key="visits",
            path_params={"page_size": INTERNAL_PAGE_SIZE},
            mapping_func=lambda v: {"id": v["visitId"], "name": v.get("name")},
        )

    def delete_visit(self, visit_id: str) -> None:
        """Delete a single visit."""
        self._delete(
            "visit.delete",
            path_params={"visit_id": visit_id},
            oid=visit_id,
        )

    def get_archive(self) -> list[dict[str, Any]]:
        """List footage archives within the SEARCH_DURATION-day look-back.

        The archive.list endpoint filters by footage time. footageTimeMin is
        the start of the window (SEARCH_DURATION days ago) and footageTimeMax
        is the end (now), both epoch seconds. One page of INTERNAL_PAGE_SIZE.
        """
        now = int(time.time())
        window_start = now - SEARCH_DURATION * 86400
        return self._fetch_list(
            "archive.list",
            response_key="instant",
            payload={
                "organizationId": self.org_id,
                "pageSize": INTERNAL_PAGE_SIZE,
                "instantLastKey": None,
                "legacyLastKey": None,
                "first": True,
                "sortAscending": False,
                "sortBy": "creation_time",
                "filters": {
                    "footageTimeMin": window_start,
                    "footageTimeMax": now,
                },
            },
            mapping_func=lambda a: {"id": a["archiveId"], "name": a.get("archiveId")},
        )

    def delete_archive(self, archive_id: str) -> None:
        """Delete a single footage archive (endpoint accepts a list)."""
        self._delete(
            "archive.delete",
            json={"archiveIds": [archive_id]},
            oid=archive_id,
        )

    def get_incident(self) -> list[dict[str, Any]]:
        """List investigation incidents (one page of INTERNAL_PAGE_SIZE)."""
        return self._fetch_list(
            "incident.list",
            response_key="incidents",
            payload={"organizationId": self.org_id, "limit": INTERNAL_PAGE_SIZE},
            mapping_func=lambda x: {
                "id": x["incidentId"],
                "name": x.get("name") or x["incidentId"],
            },
        )

    def delete_incident(self, incident_id: str) -> None:
        """Delete a single investigation incident."""
        self._delete(
            "incident.delete",
            json={"incidentId": incident_id},
            oid=incident_id,
        )

    def get_alert(self) -> list[dict[str, Any]]:
        """List alert rules configured in the org.

        The alert_rules/get endpoint returns a top-level JSON list, which
        _request wraps under the "items" key.
        """
        return self._fetch_list(
            "alert.list",
            response_key="items",
            payload={
                "organizationId": self.org_id,
                "showSharedAlerts": True,
                "filters": {},
            },
            mapping_func=lambda x: {
                "id": x["alertRuleId"],
                "name": x.get("name") or x["alertRuleId"],
            },
        )

    def delete_alert(self, alert_rule_id: str) -> None:
        """Delete a single alert rule.

        `alert_rules/delete` performs the deletion but reports the removed rule
        back as a non-2xx "alert rule not found" instead of an empty success.
        Since "not found" means the rule is gone — the desired end state — we
        treat it as an idempotent success rather than surfacing a spurious
        failure. Any other API error still propagates.
        """
        try:
            self._delete(
                "alert.delete",
                json={"organizationId": self.org_id, "filterId": alert_rule_id},
                oid=alert_rule_id,
            )
        except APIError as e:
            if "not found" not in str(e).lower():
                raise

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

    def create_or_reuse_building(
        self, building_name: str, address: Address, floors: list
    ) -> str:
        """Return a floor id in the org's building of that name, creating the
        building only when there is none.

        Unlike sites, Command accepts duplicate building names, so a second
        template run used to add another "HQ" building. The floor named
        floors[0] is preferred, else the building's first floor.
        """
        building_ids = [b["id"] for b in self.get_building() if b["name"] == building_name]
        if building_ids:
            existing = [f for f in self.get_floor() if f["building_id"] in building_ids]
            wanted = floors[0] if floors else None
            match = next((f for f in existing if f["name"] == wanted), None)
            if match or existing:
                return (match or existing[0])["id"]
        return self.create_building(building_name, address, floors)

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
        return self._create_door(
            "door.create",
            access_controller_id=access_controller_id,
            door_name=door_name,
            floor_id=floor_id,
            configs=_LPR_DOOR_CREATE_CONFIGS if lpr else _DOOR_CREATE_CONFIGS,
            door_type="standard",
        )

    def create_access_station_pro_door(
        self,
        access_controller_id: str,
        door_name: str,
        floor_id: str,
    ) -> str:
        """
        Creates the door served by an Access Station Pro. Returns door_id.

        Called after configure_access_station_pro(), which returns the
        access_controller_id this method needs. The station is its own
        controller, so the door is created with doorType "moody_as_acu"
        and the Access Station Pro config profile (which already carries
        face-unlock-enabled).
        """
        return self._create_door(
            "access_station_pro.door.create",
            access_controller_id=access_controller_id,
            door_name=door_name,
            floor_id=floor_id,
            configs=_ACCESS_STATION_PRO_DOOR_CREATE_CONFIGS,
            door_type="moody_as_acu",
        )

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

    def enable_door_face_unlock(self, door_id: str) -> None:
        """
        Enable face unlock on a door.

        Requires the org flag (enable_org_face_unlock) to already be set.
        Doors created by create_access_station_pro_door() ship with this
        config, so it is only needed for doors created another way.
        """
        self._set_door_config(
            "door.enable_face_unlock",
            door_id,
            "face-unlock-enabled",
            "face unlock",
        )

    # Each MFA mode is its own door config param — the combination named
    # by the method is what the reader will accept as two factors. They
    # are independent flags, so more than one can be enabled on a door.

    def enable_door_mfa_card_code(self, door_id: str) -> None:
        """Require card + PIN code at the door."""
        self._set_door_config(
            "door.mfa.card-code",
            door_id,
            "mfa-card-code-enabled",
            "card + code MFA",
        )

    def enable_door_mfa_face_card(self, door_id: str) -> None:
        """Require face + card at the door."""
        self._set_door_config(
            "door.mfa.face-card",
            door_id,
            "mfa-face-card-enabled",
            "face + card MFA",
        )

    def enable_door_mfa_face_code(self, door_id: str) -> None:
        """Require face + PIN code at the door."""
        self._set_door_config(
            "door.mfa.face-code",
            door_id,
            "mfa-face-code-enabled",
            "face + code MFA",
        )

    def get_visitor_access_template(self) -> list[dict[str, Any]]:
        """List visitor access templates (visit types) in the org."""
        return self._fetch_list(
            "visitor_access_type.list",
            response_key="visitTypes",
            mapping_func=lambda x: {
                "id": x["visitTypeId"],
                "name": x.get("name"),
            },
        )

    def delete_visitor_access_template(self, visitor_access_type_id: str) -> None:
        """Delete a single visitor access template (visit type)."""
        self._delete(
            "visitor_access_type.delete",
            path_params={"visitor_access_type_id": visitor_access_type_id},
            oid=visitor_access_type_id,
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
        identifies alarm sites by (alarmSiteId, siteId) and the body's
        `responseSiteId` field takes the alarm site id (the responseSite.id
        from alarm.site.list), NOT the response config id.
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
        device_type: str | tuple[str, ...] | None = None,
    ) -> list[dict[str, Any]]:
        """
        Shared body for the per-type alarm device get_* methods.

        Every alarm device .list key hits the same alarm_system/get_devices
        endpoint and returns ALL devices in the system; filtering by `type`
        client-side is what distinguishes panels from keypads from sensors.
        device_type may be a single type, a tuple of types (e.g. the wired
        input family), or None to return every device (get_alarm_device).
        """
        if device_type is None:
            wanted: set[str] | None = None
        elif isinstance(device_type, str):
            wanted = {device_type}
        else:
            wanted = set(device_type)

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
            if wanted is None or d.get("type") in wanted
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
        *,
        device_type: str = "WIRED_CONTACT_SENSOR",
        normal_state: str = "CLOSED",
    ) -> str:
        """Creates a wired input on a panel pin. Returns device_id.

        device_type is one of _WIRED_INPUT_TYPES. Only WIRED_CONTACT_SENSOR
        carries the extra wiredContactSensorConfig; glass-break/motion/
        generic/panic/water-leak send just name + type.
        """
        if device_type not in _WIRED_INPUT_TYPES:
            raise ValueError(
                f"Unknown wired input type {device_type!r}; "
                f"expected one of {_WIRED_INPUT_TYPES}"
            )
        device: dict[str, Any] = {"name": name, "type": device_type}
        if device_type == "WIRED_CONTACT_SENSOR":
            device["sensorConfig"] = {
                "wiredContactSensorConfig": {"type": "DOOR", "doorHeldOpenDelay": 0}
            }
        data, status = self._request(
            "alarm.wired_input.create",
            json={
                "device": device,
                "alarmSystemId": alarm_system_id,
                "partitionId": partition_id,
                "hubId": panel_id,
                "pinNum": pin_num,
                "normalState": normal_state,
            },
            error_context=f"Failed to create wired input '{name}'",
            log_request=f'{{"name": "{name}", "type": "{device_type}", "pinNum": {pin_num}}}',
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
        """Lists every wired-input subtype (contact/glass-break/motion/
        generic/panic/water-leak) on the system."""
        return self._list_alarm_devices(
            alarm_system_id,
            "alarm.wired_input.list",
            device_type=_WIRED_INPUT_TYPES,
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
