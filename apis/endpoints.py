from typing import NamedTuple


class Endpoint(NamedTuple):
    method: str  # 'GET', 'POST', 'DELETE'
    subdomain: str  # e.g. 'vprovision', 'vcerberus', 'api'
    path: str  # str.format template; {org_id}, {device_id}, ...
    payload: dict  # example request body (placeholder values)
    response: dict | list | None  # example response body (placeholder values)
    # Fixed domain for shard-independent endpoints (e.g. GLOBAL_DOMAIN).
    # None = served from the org's shard domain.
    domain: str | None = None


class OrgShard(NamedTuple):
    """Where an org is hosted, as reported by org/validate_short_name.

    Every internal service lives at `<service>.<domain>` (e.g.
    vprovision.prod-us-ohio.verkada.com). Gateway endpoints use the
    `api_gateway_endpoint` label instead of a service name.

    `public_api_endpoint` is NOT the public API's host: Command's own shard
    table sets it to "apiadmin" on every shard, the service that manages
    API keys. The public API host is per shard (see `public_api_region`).
    """

    name: str  # shard id sent at login: "prod1", "prod-us-ohio", ...
    domain: str  # e.g. "command.verkada.com", "prod-us-ohio.verkada.com"
    api_gateway_endpoint: str = "api"
    public_api_endpoint: str = "apiadmin"  # informational only, see above
    readable_name: str = ""  # region: "US", "EU", "AU"
    org_name: str = ""  # display name, e.g. "SSS Alpha"

    @property
    def public_api_region(self) -> str:
        """Public-API host label (https://<label>.verkada.com) for the shard.

        Looked up by shard name first: prod1 and prod-us-ohio both read "US"
        but have separate public APIs, and an API key only works on its own
        shard's host (api.verkada.com answers an Ohio key with 409
        "Authentication error"). An unknown shard falls back to its region.
        """
        label = PUBLIC_API_SHARDS.get(self.name)
        if label is None:
            label = PUBLIC_API_REGIONS.get(self.readable_name.strip().upper(), "api")
        return label


# Public API host label per shard and, as a fallback, per region
# (readable_name). From Verkada's API docs (Service Regions): api.verkada.com
# (US default), api.oh.verkada.com (additional US region), api.eu.verkada.com,
# api.au.verkada.com.
PUBLIC_API_SHARDS = {
    "prod1": "api",
    "prod-us-ohio": "api.oh",
    "prod2": "api.eu",
    "prod-ap-syd": "api.au",
}
PUBLIC_API_REGIONS = {"US": "api", "EU": "api.eu", "AU": "api.au"}


# The original US shard. Used before an org's shard is known (and by the dev
# login bypass); matches the hosts vCommander used before shards were
# resolved per org.
DEFAULT_SHARD = OrgShard(name="prod1", domain="command.verkada.com", readable_name="US")

# Domain of the shard-independent services (vglobal).
GLOBAL_DOMAIN = "global-prod.verkada.com"


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

    sms_contact holds the last digits of the SMS-receiving number, if known.
    sms_enabled / qr_enabled report which second factors the org has
    configured so the 2FA screen can prompt for the right one (and so
    login() knows whether to dispatch an SMS via auth/twofactor/sms/new).
    """

    def __init__(
        self,
        message: str = "MFA Required",
        sms_contact: str | None = None,
        *,
        sms_enabled: bool = False,
        qr_enabled: bool = False,
    ):
        super().__init__(message)
        self.sms_contact = sms_contact
        self.sms_enabled = sms_enabled
        self.qr_enabled = qr_enabled


# Subdomain marker for API-gateway endpoints. Most internal endpoints live on
# a named service host (vprovision, vcerberus, …); the ones registered with
# API_GATEWAY_SUBDOMAIN use the shard's `api_gateway_endpoint` label instead
# (build_url swaps it in).
API_GATEWAY_SUBDOMAIN = "api"

_LPR_DOOR_CREATE_CONFIGS = [
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
    {"paramName": "third-party-io-baud-rate", "paramValue": "14400"},
    {"paramName": "badge-reader", "paramValue": "True"},
    {"paramName": "mobile-unlock-enabled", "paramValue": "True"},
    {"paramName": "door-api-unlock-enabled", "paramValue": "False"},
    {"paramName": "nfc-enabled", "paramValue": "True"},
    {"paramName": "lpr-unlock-enabled", "paramValue": "True"},
    {"paramName": "lpr-unlock-cooldown-time", "paramValue": "0"},
    {"paramName": "ignore-outbound-reader-ac", "paramValue": "False"},
    {"paramName": "lf-card-reading-enabled", "paramValue": "True"},
    {"paramName": "c3po-in1-type", "paramValue": "NONE"},
    {"paramName": "c3po-in2-type", "paramValue": "NONE"},
    {"paramName": "replace-ios-with-security-relay", "paramValue": "False"},
]

_ACCESS_STATION_PRO_DOOR_CREATE_CONFIGS = [
    {"paramName": "default-unlock-time", "paramValue": "10"},
    {"paramName": "assa-extended-unlock-time", "paramValue": "20"},
    {"paramName": "has-door-sensor", "paramValue": "False"},
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
    {"paramName": "third-party-io-baud-rate", "paramValue": "14400"},
    {"paramName": "badge-reader", "paramValue": "True"},
    {"paramName": "mobile-unlock-enabled", "paramValue": "True"},
    {"paramName": "door-api-unlock-enabled", "paramValue": "False"},
    {"paramName": "nfc-enabled", "paramValue": "True"},
    {"paramName": "lpr-unlock-enabled", "paramValue": "False"},
    {"paramName": "lpr-unlock-cooldown-time", "paramValue": "0"},
    {"paramName": "ignore-outbound-reader-ac", "paramValue": "False"},
    {"paramName": "lf-card-reading-enabled", "paramValue": "True"},
    {"paramName": "c3po-in1-type", "paramValue": "NONE"},
    {"paramName": "c3po-in2-type", "paramValue": "NONE"},
    {"paramName": "replace-ios-with-security-relay", "paramValue": False},
    {"paramName": "face-unlock-enabled", "paramValue": "True"},
]

# Two-factor modes a door accepts once a 2FA schedule applies. The Command
# web app sends them with door/create (its defaults: face + card and face +
# code on, card + code off) instead of setting them afterwards.
_DOOR_MFA_CREATE_CONFIGS = [
    {"paramName": "mfa-card-code-enabled", "paramValue": "True"},
    {"paramName": "mfa-face-card-enabled", "paramValue": "True"},
    {"paramName": "mfa-face-code-enabled", "paramValue": "True"},
]

_DOOR_CREATE_CONFIGS = [
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
    {"paramName": "third-party-io-baud-rate", "paramValue": "14400"},
    {"paramName": "badge-reader", "paramValue": "True"},
    {"paramName": "mobile-unlock-enabled", "paramValue": "True"},
    {"paramName": "door-api-unlock-enabled", "paramValue": "False"},
    {"paramName": "nfc-enabled", "paramValue": "True"},
    {"paramName": "lpr-unlock-enabled", "paramValue": "False"},
    {"paramName": "lpr-unlock-cooldown-time", "paramValue": "0"},
    {"paramName": "ignore-outbound-reader-ac", "paramValue": "False"},
    {"paramName": "lf-card-reading-enabled", "paramValue": "True"},
    {"paramName": "c3po-in1-type", "paramValue": "NONE"},
    {"paramName": "c3po-in2-type", "paramValue": "NONE"},
    {"paramName": "replace-ios-with-security-relay", "paramValue": "False"},
]

_DOOR_CREATE_IOS = [
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
    {"configs": {}, "ioDeviceTypeName": "lock", "ioSlotIndex": 0, "ioSlotType": "lock"},
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
]

_DOOR_EVENT = [
    {
        "doorPermissionState": "ALLOW",
        "weekday": 7,
        "date": None,
        "startTime": "00:00:00.000",
        "endTime": "23:59:59.999",
    },
    {
        "doorPermissionState": "ALLOW",
        "weekday": 1,
        "date": None,
        "startTime": "00:00:00.000",
        "endTime": "23:59:59.999",
    },
    {
        "doorPermissionState": "ALLOW",
        "weekday": 2,
        "date": None,
        "startTime": "00:00:00.000",
        "endTime": "23:59:59.999",
    },
    {
        "doorPermissionState": "ALLOW",
        "weekday": 3,
        "date": None,
        "startTime": "00:00:00.000",
        "endTime": "23:59:59.999",
    },
    {
        "doorPermissionState": "ALLOW",
        "weekday": 4,
        "date": None,
        "startTime": "00:00:00.000",
        "endTime": "23:59:59.999",
    },
    {
        "doorPermissionState": "ALLOW",
        "weekday": 5,
        "date": None,
        "startTime": "00:00:00.000",
        "endTime": "23:59:59.999",
    },
    {
        "doorPermissionState": "ALLOW",
        "weekday": 6,
        "date": None,
        "startTime": "00:00:00.000",
        "endTime": "23:59:59.999",
    },
]

_MFA_DOOR_EVENT = [
    {
        "doorLockState": "ACCESS_CONTROL_2FA",
        "weekday": 1,
        "date": None,
        "startTime": "00:00:00.000",
        "endTime": "23:59:59.999",
        "twoPersonRuleEnabled": False
    },
    {
        "doorLockState": "ACCESS_CONTROL_2FA",
        "weekday": 2,
        "date": None,
        "startTime": "00:00:00.000",
        "endTime": "23:59:59.999",
        "twoPersonRuleEnabled": False
    },
    {
        "doorLockState": "ACCESS_CONTROL_2FA",
        "weekday": 3,
        "date": None,
        "startTime": "00:00:00.000",
        "endTime": "23:59:59.999",
        "twoPersonRuleEnabled": False
    },
    {
        "doorLockState": "ACCESS_CONTROL_2FA",
        "weekday": 4,
        "date": None,
        "startTime": "00:00:00.000",
        "endTime": "23:59:59.999",
        "twoPersonRuleEnabled": False
    },
    {
        "doorLockState": "ACCESS_CONTROL_2FA",
        "weekday": 5,
        "date": None,
        "startTime": "00:00:00.000",
        "endTime": "23:59:59.999",
        "twoPersonRuleEnabled": False
    },
    {
        "doorLockState": "ACCESS_CONTROL_2FA",
        "weekday": 6,
        "date": None,
        "startTime": "00:00:00.000",
        "endTime": "23:59:59.999",
        "twoPersonRuleEnabled": False
    },
    {
        "doorLockState": "ACCESS_CONTROL_2FA",
        "weekday": 7,
        "date": None,
        "startTime": "00:00:00.000",
        "endTime": "23:59:59.999",
        "twoPersonRuleEnabled": False
    },
]


def resolve(endpoint_key: str, path_params: dict | None = None) -> tuple[Endpoint, str]:
    """
    Look up an endpoint and apply path_params to its template.

    Returns:
        (endpoint, formatted_path) — `formatted_path` is the path with
        placeholders substituted, suitable for both URL building and
        log lines (so the log line matches the actual request path).

    Raises:
        KeyError: if endpoint_key isn't registered (likely a typo).
        KeyError: from `str.format` if a placeholder is missing from
            path_params; the message names the missing field.
    """
    endpoint = ENDPOINTS[endpoint_key]
    formatted = endpoint.path.format(**(path_params or {}))
    return endpoint, formatted


def build_url(
    endpoint: Endpoint,
    org_short_name: str,
    formatted_path: str,
    shard: OrgShard = DEFAULT_SHARD,
) -> str:
    """Compose the full request URL from an endpoint and a pre-formatted path.

    The host is `<service>.<shard domain>`: gateway endpoints
    (API_GATEWAY_SUBDOMAIN) take the shard's gateway label, and endpoints
    with a fixed `domain` (global services) ignore the shard.
    """
    subdomain = endpoint.subdomain
    if subdomain == API_GATEWAY_SUBDOMAIN:
        subdomain = shard.api_gateway_endpoint
    domain = endpoint.domain or shard.domain
    return f"https://{subdomain}.{domain}/__v/{org_short_name}/{formatted_path}"


ENDPOINTS: dict[str, Endpoint] = {
    # ── Org discovery (pre-auth, shard-independent) ──────────────────
    # Resolves which shard hosts an org and which API hosts it uses, so
    # login can be routed without asking the user for a shard or region.
    "org.validate_short_name": Endpoint(
        method="POST",
        subdomain="vglobal",
        path="org/validate_short_name",
        payload={"orgShortName": "<org_short_name>"},
        response={
            "name": "<org_display_name>",
            "shard": {
                "name": "prod-us-ohio",
                "readable_name": "US",
                "host_metadata": {
                    "domain": "prod-us-ohio.verkada.com",
                    "guest_domain": "prod-us-ohio.my.verkada.com",
                    "local_camera_domain": "prod-us-ohio.verkada-lan.com",
                    "public_api_endpoint": "api",
                    "api_gateway_endpoint": "api",
                    "saml_endpoint": "https://saml.prod-us-ohio.verkada.com",
                    "scim_endpoint": "https://scim.prod-us-ohio.verkada.com",
                },
                "enum_value": 13,
            },
        },
        domain=GLOBAL_DOMAIN,
    ),
    # ── Auth ─────────────────────────────────────────────────────────
    "login": Endpoint(
        method="POST",
        subdomain="vprovision",
        path="user/login",
        payload={
            "email": "<email>",
            "orgShortName": "<org_short_name>",
            "termsAcked": False,
            "password": "<password>",
            "loginMethod": "password",
            "shard": "prod1",
            "subdomain": True,
        },
        response={
            "loggedIn": True,
            "csrfToken": "<csrf>",
            "userToken": "<user_token>",
            "organizationId": "<org_id>",
            "userId": "<user_id>",
        },
    ),
    # Dispatches an SMS 2FA code mid-login. Lives on the vauth subdomain
    # (not vprovision) and runs pre-auth. The login response that demands
    # MFA no longer sends the text itself nor carries the destination
    # digits — this endpoint does both. QR/authenticator orgs skip it.
    "auth.twofactor.sms.new": Endpoint(
        method="POST",
        subdomain="vauth",
        path="auth/twofactor/sms/new",
        payload={
            "email": "<email>",
            "password": "<password>",
            "orgShortName": "<org_short_name>",
        },
        response={"smsSent": "<masked_phone_digits>"},
    ),
    # ── Permissions ──────────────────────────────────────────────────
    "permissions.global_site_admin.enable": Endpoint(
        method="POST",
        subdomain="vprovision",
        path="org/settings/update",
        payload={
            "organizationId": "<org_id>",
            "settings": {"globalSiteAdmin": True},
        },
        response={},
    ),
    "permissions.global_site_admin.disable": Endpoint(
        method="POST",
        subdomain="vprovision",
        path="org/settings/update",
        payload={
            "organizationId": "<org_id>",
            "settings": {"globalSiteAdmin": False},
        },
        response={},
    ),
    # Read-only use of set_user_permissions: nothing granted or revoked, and
    # returnPermissions on, so the response lists the user's roles
    # (roleGrant[].roleKey) and permissions.
    "permissions.user_roles.get": Endpoint(
        method="POST",
        subdomain="vprovision",
        path="org/set_user_permissions",
        payload={
            "organizationId": "<org_id>",
            "targetUserId": "<user_id>",
            "returnPermissions": True,
            "grant": [],
            "revoke": [],
        },
        response={
            "roleGrant": [
                {
                    "roleKey": "ACCESS_CONTROL_SYSTEM_ADMIN",
                    "targetEntityType": "organization",
                    "entityId": "<org_id>",
                },
            ],
            "role": [{"key": "ACCESS_CONTROL_SYSTEM_ADMIN", "roleId": "<role_id>"}],
            "permissions": [{"permission": "ADMIN", "entityId": "<entity_id>"}],
        },
    ),
    # Grant and/or revoke any org-level roles on a user in one call; the
    # Command web app batches every role changed in a Manage dialog (Org
    # Admin is ORG_MANAGER). The per-role keys below are single-role uses.
    "permissions.user_roles.set": Endpoint(
        method="POST",
        subdomain="vprovision",
        path="org/set_user_permissions",
        payload={
            "organizationId": "<org_id>",
            "targetUserId": "<user_id>",
            "returnPermissions": False,
            "grant": [
                {"entityId": "<org_id>", "permission": "ACCESS_CONTROL_SYSTEM_ADMIN"},
                {"entityId": "<org_id>", "permission": "ACCESS_CONTROL_USER_ADMIN"},
            ],
            "revoke": [],
        },
        response={},
    ),
    "permissions.access_system_admin.enable": Endpoint(
        method="POST",
        subdomain="vprovision",
        path="org/set_user_permissions",
        payload={
            "organizationId": "<org_id>",
            "returnPermissions": False,
            "revoke": [],
            "grant": [
                {
                    "entityId": "<org_id>",
                    "permission": "ACCESS_CONTROL_SYSTEM_ADMIN",
                },
            ],
            "targetUserId": "<user_id>",
        },
        response={},
    ),
    "permissions.access_system_admin.disable": Endpoint(
        method="POST",
        subdomain="vprovision",
        path="org/set_user_permissions",
        payload={
            "grant": [],
            "organizationId": "<org_id>",
            "returnPermissions": False,
            "revoke": [
                {"entityId": "<org_id>", "permission": "ACCESS_CONTROL_SYSTEM_ADMIN"},
            ],
            "targetUserId": "<user_id>",
        },
        response={},
    ),
    "permissions.access_user_admin.enable": Endpoint(
        method="POST",
        subdomain="vprovision",
        path="org/set_user_permissions",
        payload={
            "organizationId": "<org_id>",
            "returnPermissions": False,
            "revoke": [],
            "grant": [
                {
                    "entityId": "<org_id>",
                    "permission": "ACCESS_CONTROL_USER_ADMIN",
                },
            ],
            "targetUserId": "<user_id>",
        },
        response={},
    ),
    "permissions.access_user_admin.disable": Endpoint(
        method="POST",
        subdomain="vprovision",
        path="org/set_user_permissions",
        payload={
            "grant": [],
            "organizationId": "<org_id>",
            "returnPermissions": False,
            "revoke": [
                {"entityId": "<org_id>", "permission": "ACCESS_CONTROL_USER_ADMIN"},
            ],
            "targetUserId": "<user_id>",
        },
        response={},
    ),
    # ── Org ──────────────────────────────────────────────────────────
    "org.check_empty": Endpoint(
        method="POST",
        subdomain="vprovision",
        path="org/delete",
        payload={"organizationId": "<org_id>", "validateOnly": True},
        response={"orgEmpty": True},
    ),
    "org.device_information.list": Endpoint(
        method="POST",
        subdomain="vlicensing",
        path="device/batch/information",
        payload={"serialNumbers": "<serial_number>", "organizationId": "<org_id>"},
        response={
            "devices": [
                {
                    "deviceId": None,
                    "deviceModelId": "",
                    "deviceType": "camera",
                    "modelNumber": "2100",
                    "organizationId": None,
                    "registered": False,
                    "serialNumber": "NMCC-QXN6-Q7E4",
                }
            ],
            "invalidSerialNumbers": [],
            "restrictedSerialNumbers": [],
            "unclaimableSerialNumbers": [],
        },
    ),
    "org.device_count": Endpoint(
        method="GET",
        subdomain="vlicensing",
        path="org/{org_id}/get_device_counts",
        payload={},
        response={
            "deviceCounts": [
                {"deviceType": "Camera", "quantity": 0},
                {"deviceType": "Sensor", "quantity": 0},
                {"deviceType": "Gateway", "quantity": 0},
                {"deviceType": "Cellular", "quantity": 0},
                {"deviceType": "Desk App", "quantity": 0},
                {"deviceType": "Intercom", "quantity": 0},
                {"deviceType": "Workplace", "quantity": 0},
                {"deviceType": "Mobile NFC", "quantity": 0},
                {"deviceType": "Sensor Basic", "quantity": 0},
                {"deviceType": "WiFi Gateway", "quantity": 0},
                {"deviceType": "Alarm Speaker", "quantity": 0},
                {"deviceType": "Cloud Storage", "quantity": 0},
                {"deviceType": "Access Control", "quantity": 0},
                {"deviceType": "Access Station", "quantity": 0},
                {"deviceType": "Alarm Location", "quantity": 0},
                {"deviceType": "Mobile Trailer", "quantity": 0},
                {"deviceType": "Cellular Backup", "quantity": 0},
                {"deviceType": "Viewing Station", "quantity": 0},
                {"deviceType": "Alarm Sites Basic", "quantity": 0},
                {"deviceType": "Non Verkada Channel", "quantity": 0},
                {"deviceType": "Access IO Controller", "quantity": 0},
                {"deviceType": "Alarm Location Basic", "quantity": 0},
                {"deviceType": "Two-Camera Multisensor", "quantity": 0},
                {"deviceType": "CH52 Multisensor Camera", "quantity": 0},
                {"deviceType": "Alarm Location Monitoring", "quantity": 0},
                {"deviceType": "Cellular Gateway Data Plan", "quantity": 0},
                {"deviceType": "Advanced Video Alarms Sites", "quantity": 0},
            ]
        },
    ),
    "org.add_device": Endpoint(
        method="POST",
        subdomain="vconductor",
        path="vconductor/command/device/batch/commission",
        payload={
            "organizationId": "<org_id>",
            "devices": [
                {
                    "deferUpdate": True,
                    "name": "<name>",
                    "serialNumber": "<serial>",
                    "updateSchedule": None,
                }
            ],
        },
        response={
            "successfulDevices": [{"deviceId": "<device_id>"}],
            "failedSerials": [],
        },
    ),
    "org.unassigned_devices.list": Endpoint(
        method="GET",
        subdomain="vconductor",
        path="org/{org_id}/unassigned_devices",
        payload={},
        response={
            "devices": [
                {"deviceId": "<id>", "name": "<name>", "serialNumber": "<serial>"},
            ]
        },
    ),
    "org.custom_roles": Endpoint(
        method="POST",
        subdomain="vauth",
        path="org/{org_id}/custom_roles/enable",
        payload={},
        response={},
    ),
    "org.sign_agreement": Endpoint(
        method="POST",
        subdomain="vcorgi",
        path="{org_id}/sign_agreement",
        payload={"agreementKey": "<CV_ANALYTICS | LPR>", "userEmail": "<email>"},
        response={
            "orgAgreements": [
                {
                    "agreementKey": "CV_ANALYTICS | LPR",
                    "organizationId": "<org_id>",
                    "userEmail": "<email>",
                    "userId": "<user_id>",
                }
            ]
        },
    ),
    "org.features": Endpoint(
        method="POST",
        subdomain="vdeviceconfig",
        path="user/org/feature/set",
        payload={
            "organizationId": "<org_id>",
            "params": {"<feature_flag>": True},
            # Feature Flags:
            # - aiSummarization
            # - faceDetection
            # - licensePlateRecognition
            # - naturalLanguageSearch
            # - peopleHistory
            # - personAttributes
            # - personOfInterestNotifications
            # - vehicleHistory
            "annotations": {
                "timestamp": 0,
                "userId": "<user_id>",
            },
        },
        response={},
    ),
    "org.allow_face_unlock": Endpoint(
        method="POST",
        subdomain=API_GATEWAY_SUBDOMAIN,
        path="organization/config/set",
        payload={
            "organizationId": "<org_id>",
            "paramName": "face-unlock-enabled",
            "paramValue": True,
        },
        response={},
    ),
    "org.api_key.create": Endpoint(
        method="POST",
        subdomain="apiadmin",
        path="admin/orgs/{org_id}/v2/granular_apikeys",
        payload={
            "api_key_name": "<key_name>",
            "expires_at": 0,
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
        },
        response={
            "apiKey": "<api_key>",
            "apiKeyId": "<api_key_id>",
            "apiKeyName": "<api_key_name>",
        },
    ),
    "org.api_key.list": Endpoint(
        method="GET",
        subdomain="apiadmin",
        path="admin/orgs/{org_id}/v2/apikeys",
        payload={},
        response={
            "apiKeys": [
                {
                    "apiKeyId": "<api_key_id>",
                    "apiKeyName": "<api_key_name>",
                }
            ]
        },
    ),
    "org.api_key.delete": Endpoint(
        method="DELETE",
        subdomain="apiadmin",
        path="admin/orgs/{org_id}/v2/apikeys/{api_key_id}",
        payload={},
        response={
            "apiKeyId": "<api_key_id>",
            "apiKeyName": "<api_key_name>",
        },
    ),
    "alert.list": Endpoint(
        subdomain="vlive",
        method="POST",
        path="alert_rules/get",
        payload={"organizationId": "<org_id>", "showSharedAlerts": True, "filters": {}},
        response=[
            {
                "alertRuleId": "<alert_rule_id>",
                "organizationId": "<org_id>",
                "name": "<alert_name>",
                "ownerId": "<owner_id>",
            },
        ],
    ),
    "alert.delete": Endpoint(
        subdomain="vlive",
        method="POST",
        path="alert_rules/delete",
        payload={"organizationId": "<org_id>", "filterId": "<alert_rule_id>"},
        response=None,
    ),
    # ── Site ─────────────────────────────────────────────────────────
    # ── Site ─────────────────────────────────────────────────────────
    "site.create": Endpoint(
        method="POST",
        subdomain="vprovision",
        path="org/camera_group/create",
        payload={"organizationId": "<org_id>", "name": "<site_name>"},
        response={"cameraGroups": [{"cameraGroupId": "<site_id>"}]},
    ),
    "site.list": Endpoint(
        method="POST",
        subdomain="vprovision",
        path="org/site/list",
        payload={"orgId": "<org_id>"},
        response={
            "sites": [
                {"siteId": "<id>", "name": "<name>"},
            ]
        },
    ),
    "site.rename": Endpoint(
        method="POST",
        subdomain="vprovision",
        path="org/camera_group/modify",
        payload={"cameraGroupId": "<site_id>", "name": "<site_name>"},
        response={
            "cameraGroups": [
                {
                    "name": "<site_name>",
                    "organizationId": "<org_id>",
                }
            ],
        },
    ),
    "site.delete": Endpoint(
        method="POST",
        subdomain="vprovision",
        path="org/camera_group/delete",
        payload={"cameraGroupId": "<id>"},
        response={},
    ),
    # ── Users ────────────────────────────────────────────────────────
    "user.create": Endpoint(
        method="POST",
        subdomain="vprovision",
        path="org/invite",
        payload={
            "organizationId": "<org_id>",
            "email": "<email>",
            "orgAdmin": True,
            "commandUserAdmin": False,
            "firstName": "<FirstName>",
            "lastName": "<LastName>",
            "inviteFf": True,
        },
        response={
            "orgInvitation": [{"orgInvitationId": "<inv_id>"}],
            "users": [
                {"userId": "<user_id>", "email": "<email>", "name": "<full_name>"}
            ],
        },
    ),
    "user.list": Endpoint(
        method="POST",
        subdomain="vprovision",
        path="organization/{org_id}/users/search",
        payload={
            "paging": {"pageSize": 1000, "sortOrder": ["full_name:asc"]},
            "isVisitor": False,
            "status": ["active", "invited"],
            "organizationId": "<org_id>",
            "userDirectoryIds": [],
            "includeRoleGrants": True,
            "includeGroups": True,
            "useEs": True,
        },
        response={
            "users": [
                {
                    "email": "<email>",
                    "firstName": "<FirstName>",
                    "lastName": "<LastName>",
                    "isOrganizationAdmin": True,
                    "userId": "<user_id>",
                },
            ],
        },
    ),
    "user.delete": Endpoint(
        method="POST",
        subdomain=API_GATEWAY_SUBDOMAIN,
        path="users/delete",
        payload={
            "organizationId": "<org_id>",
            "userIds": ["<user_id>"],
        },
        response={},
    ),
    # What the Command web app calls for User Management → user → Delete
    # User (recorded 2026-10-27). Takes several userIds in one call.
    "user.delete.batch": Endpoint(
        method="POST",
        subdomain="vcorgi",
        path="org/{org_id}/users/delete",
        payload={"userIds": ["<user_id>"]},
        # Asynchronous: users/search shows the user for a few seconds more.
        response={"operationId": "<operation_id>"},
    ),
    "user.hard_delete": Endpoint(
        method="POST",
        subdomain="vprovision",
        path="core/v1/org/{org_id}/user:hardDelete",
        payload={
            "organizationId": "<org_id>",
            "callingUserId": "<user_id>",
            "userIds": [
                "<deleted_user_id>",
            ],
            "deleteAllSoftDeleted": False,
        },
        response={
            "userInfo": {
                "<deleted_user_id>": {
                    "email": "<deleted_user_email>",
                    "name": "<deleted_user_name>",
                },
            }
        },
    ),
    "user.add_license_plate": Endpoint(
        method="POST",
        subdomain=API_GATEWAY_SUBDOMAIN,
        path="access/v2/user/license_plate",
        payload={
            "userId": "<user_id>",
            "licensePlateNumber": "<license_plate_number>",
            "organizationId": "<org_id>",
        },
        response={
            "licensePlateNumber": "<license_plate_number>",
            "organizationId": "<org_id>",
            "userId": "<user_id>",
        },
    ),
    # Who holds a license plate (the web app checks this before adding one).
    # 404 "No such license plate registered" when nobody does.
    "user.license_plate.get": Endpoint(
        method="GET",
        subdomain=API_GATEWAY_SUBDOMAIN,
        path="access/v2/user/license_plate/{license_plate}",
        payload={},
        response={
            "licensePlateNumber": "<license_plate_number>",
            "userId": "<user_id>",
            "organizationId": "<org_id>",
            "active": True,
        },
    ),
    # Remove a plate from its user (Access → user → Profile → Remove License
    # Plate in the web app).
    "user.license_plate.delete": Endpoint(
        method="POST",
        subdomain=API_GATEWAY_SUBDOMAIN,
        path="access/v2/user/license_plate/delete",
        payload={"licensePlateNumber": "<license_plate_number>"},
        response={},
    ),
    "group.create": Endpoint(
        method="POST",
        subdomain="vauth",
        path="security_entity_group/create",
        payload={
            "organizationId": "<org_id>",
            "name": "<group_name>"
        },
        response={
            "securityEntityGroup": [
                {
                    "entityGroupId": "<group_id>",
                    "name": "<group_name>",
                    "organizationId": "<org_id>",
                }
            ]
        }
    ),
    "group.add_members": Endpoint(
        method="POST",
        subdomain="vauth",
        path="security_entity_group/members/add",
        payload={
            "securityEntityGroupId": "<group_id>",
            "securityEntityIds": [
                "<user_id>",
                "<user_id>"
            ]
        },
        response=None
    ),
    "group.list": Endpoint(
        method="POST",
        subdomain="vauth",
        path="security_entity_group/list",
        payload={
            "organizationId": "<org_id>",
            "includeMembers": True,
            "includeMemberCount": False,
        },
        response={
            "securityEntityGroup": [
                {
                    "entityGroupId": "<group_id>",
                    "name": "13 Admins",
                    "verkadaManaged": False,
                },
            ],
        },
    ),
    "group.delete": Endpoint(
        method="POST",
        subdomain="vauth",
        path="security_entity_group/delete",
        payload={
            "securityEntityGroupIds": [
                "<group_id>",
            ]
        },
        response={},
    ),
    # ── Cameras ──────────────────────────────────────────────────────
    "camera.create.name": Endpoint(
        method="POST",
        subdomain="vprovision",
        path="camera/name/set",
        payload={"cameraId": "<camera_id>", "name": "<name>"},
        response={
            "cameras": [
                {
                    "cameraId": "<camera_id>",
                    "name": "<camera_name>",
                    "organizationId": "<org_id>",
                    "serialNumber": "<serial_number>",
                }
            ],
        },
    ),
    "camera.create.site": Endpoint(
        method="POST",
        subdomain="vprovision",
        path="camera/site/batch/set",
        payload={
            "cameraIds": ["<camera_id>"],
            "destinationSiteId": "<site_id>",
        },
        response={},
    ),
    "camera.create.location": Endpoint(
        method="POST",
        subdomain="vprovision",
        path="camera/location/set",
        payload={
            "cameraId": "<camera_id>",
            "angle": 0,
            "label": "<address>",
            "lat": 0.0,
            "lon": 0.0,
        },
        response={
            "cameras": [
                {
                    "cameraId": "<camera_id>",
                    "name": "<camera_name>",
                    "organizationId": "<org_id>",
                    "serialNumber": "<serial_number>",
                }
            ],
        },
    ),
    "camera.create.feature": Endpoint(
        method="POST",
        subdomain="vdeviceconfig",
        path="user/camera/feature/set",
        payload={
            "cameraIds": ["<camera_id>"],
            "params": {"<feature_flag>": True},
        },
        response={},
    ),
    "camera.create.lpr_config": Endpoint(
        method="POST",
        subdomain="vprovision",
        path="user/camera/config/set",
        payload={
            "cameraId": "<camera_id>",
            "params": {"camera-config.operating-mode": "lpr"},
        },
        response={},
    ),
    "camera.create.ptz_install_disable": Endpoint(
        method="POST",
        subdomain="vdeviceconfig",
        path="user/camera/config/set",
        payload={
            "cameraIds": [
                "<camera_id>"
            ],
            "params": {
                "peripheral-motor-ctrl.disable-pan-tilt": False
            },
            "consumable": False
        },
        response={"<camera_id>":{}}
    ),
    "camera.list": Endpoint(
        method="POST",
        subdomain="vconductor",
        path="command/device/search",
        payload={
            "terms": {"deviceType": ["camera"]},
            "sortField": "device_type",
            "sortOrder": "asc",
            "size": 50,
            "searchAfter": None,
            "deviceTypes": ["camera"],
        },
        response={
            "devices": [
                {
                    "deviceId": "<camera_id>",
                    "deviceName": "<camera_name>",
                    "deviceType": "camera",
                    "macAddress": "<mac_address>",
                    "serialNumber": "<serial_number>",
                    "siteId": "<site_id>",
                },
            ],
            "total": 1,
        },
    ),
    "camera.delete": Endpoint(
        method="POST",
        subdomain="vprovision",
        path="camera/decommission",
        payload={"cameraId": "<camera_id>"},
        response={},
    ),
    "archive.list": Endpoint(
        method="POST",
        subdomain="vsubmit",
        path="library/v2/archive/list/org",
        payload={
            "organizationId": "<org_id>",
            "pageSize": 99,
            "instantLastKey": None,
            "legacyLastKey": None,
            "first": True,
            "sortAscending": False,
            "sortBy": "creation_time",
            "filters": {
                "footageTimeMin": "<epoch time - SEARCH_DURATION days ago>",
                "footageTimeMax": "<epoch time - now>",
            },
        },
        response={
            "instant": [
                {
                    "archiveId": "<archive_id>",
                },
            ],
        },
    ),
    "archive.delete": Endpoint(
        # Must be DELETE — the same path served as POST returns
        # "Insufficient permissions" for the org/user session.
        method="DELETE",
        subdomain="vsubmit",
        path="library/v2/archive/delete",
        payload={"archiveIds": ["<archive_id>"]},
        response={"<archive_id>": "success"},
    ),
    "incident.list": Endpoint(
        method="POST",
        subdomain="vinvestigate",
        path="v2/incident/list",
        payload={"organizationId": "<org_id>", "limit": 99},
        response={
            "incidents": [
                {
                    "incidentId": "<incident_id>",
                    "name": "<incident_name>",
                }
            ],
        },
    ),
    "incident.delete": Endpoint(
        method="POST",
        subdomain="vinvestigate",
        path="v2/incident/delete",
        payload={"incidentId": "<incident_id>"},
        response={"success": True},
    ),
    "command_connector.create": Endpoint(
        method="POST",
        subdomain="vprovision",
        path="vfortress/update_box",
        payload={
            "deviceId": "<command_connector_id>",
            "locationLabel": "<label>",
            "locationLat": 0.0,
            "locationLon": 0.0,
            "name": "<command_connector_name>",
            "siteId": "<site_id>",
        },
        response={
            "deviceId": "<command_connector_id>",
            "organizationId": "<org_id>",
            "name": "<command_connector_name>",
            "siteId": "<site_id>",
            "claimedSerialNumber": "<serial_number>",
        },
    ),
    "command_connector.list": Endpoint(
        method="POST",
        subdomain="vprovision",
        path="vfortress/list_boxes",
        payload={"organizationId": "<org_id>"},
        response=[
            {
                "deviceId": "<command_connector_id>",
                "organizationId": "<org_id>",
                "name": "<command_connector_name>",
                "siteId": "<site_id>",
                "claimedSerialNumber": "<serial_number>",
            },
        ],
    ),
    "command_connector.delete": Endpoint(
        method="POST",
        subdomain="vprovision",
        path="vfortress/decommission",
        payload={"deviceId": "<command_connector_id>", "organizationId": "<org_id>"},
        response={
            "deviceId": "<command_connector_id>",
            "organizationId": "<org_id>",
            "name": "<command_connector_name>",
            "siteId": "<site_id>",
            "claimedSerialNumber": "<serial_number>",
        },
    ),
    # ── Intercoms ────────────────────────────────────────────────────
    "intercom.list": Endpoint(
        method="GET",
        subdomain=API_GATEWAY_SUBDOMAIN,
        path="vinter/v1/user/organization/{org_id}/device",
        payload={},
        response={
            "intercoms": [
                {
                    "deviceId": "<intercom_id>",
                    "name": "<intercom_name>",
                    "serialNumber": "<serial_number>",
                },
            ]
        },
    ),
    "intercom.delete": Endpoint(
        method="DELETE",
        subdomain=API_GATEWAY_SUBDOMAIN,
        path="vinter/v1/user/async/organization/{org_id}/device/{object_id}",
        payload={"sharding": True},
        response={},
    ),
    "desk_station.list": Endpoint(
        method="GET",
        subdomain=API_GATEWAY_SUBDOMAIN,
        path="vinter/v1/user/organization/{org_id}/device",
        payload={},
        response={
            "deskApps": [
                {
                    "deviceId": "<deskstation_id>",
                    "name": "<deskstation_name>",
                    "serialNumber": "<serial_number>",
                },
            ]
        },
    ),
    "desk_station.delete": Endpoint(
        method="DELETE",
        subdomain=API_GATEWAY_SUBDOMAIN,
        path="vinter/v1/user/async/organization/{org_id}/device/{object_id}",
        payload={"sharding": True},
        response={},
    ),
    # ── Sensors ──────────────────────────────────────────────────────
    "sensor.list": Endpoint(
        method="POST",
        subdomain="vsensor",
        path="devices/list",
        payload={"organizationId": "<org_id>"},
        response={
            "sensorDevice": [
                {
                    "deviceId": "<sensor_id>",
                    "name": "<sensor_name>",
                    "claimedSerialNumber": "<serial_number>",
                },
            ]
        },
    ),
    "sensor.delete": Endpoint(
        method="POST",
        subdomain="vsensor",
        path="devices/decommission",
        payload={"deviceId": "<sensor_id>", "sharding": True},
        response={},
    ),
    # ── Access Controller ────────────────────────────────────────────
    "access_controller.create": Endpoint(
        method="POST",
        subdomain="vcerberus",
        path="access/v2/user/access_device/setup",
        payload={
            "deviceId": "<access_controller_id>",
            "name": "<access_controller_name>",
            "floorId": "<floor_id>",
            "timezone": "<timezone>",
            "siteId": "<site_id>",
            "configs": {"acu-mode": "normal"},
            "enableLte": False,
        },
        response={
            "accessControllerId": "<access_controller_id>",
            "floorId": "<floor_id>",
            "name": "<access_controller_name>",
            "organizationId": "<org_id>",
            "vconductorSerialNumber": "<serial_number>",
        },
    ),
    "access_controller.list": Endpoint(
        method="GET",
        subdomain=API_GATEWAY_SUBDOMAIN,
        path="access/v3/user/access_controllers",
        payload={},
        response={
            "accessControllers": [
                {
                    "accessControllerId": "<access_controller_id>",
                    "floorId": "<floor_id>",
                    "name": "<access_controller_name>",
                    "organizationId": "<org_id>",
                    "serialNumber": "<serial_number>",
                }
            ]
        },
    ),
    "access_controller.delete": Endpoint(
        method="POST",
        subdomain="vcerberus",
        path="access_device/decommission",
        payload={"deviceId": "<access_controller_id>", "sharding": True},
        response={},
    ),
    "access_station_pro.create": Endpoint(
        method="POST",
        subdomain="vcerberus",
        path="access/v2/user/access_device/setup",
        payload={
            "deviceId": "<access_station_pro_id>",
            "name": "<access_station_pro_name>",
            "siteId": "<site_id>",
            "location": {"label": "<address>", "lat": 0, "lon": 0},
        },
        response={
            "accessControllerId": "<access_controller_id>",
            "deviceId": "<access_station_pro_id>",
            "name": "<access_station_pro_name>",
            "organizationId": "<org_id>",
            "serialNumber": "<serial_number>",
            "timezone": "<timezone>",
            "vconductorModelId": "MOODY",
        },
    ),
    "access_station_pro.door.create": Endpoint(
        method="POST",
        subdomain=API_GATEWAY_SUBDOMAIN,
        path="door/create",
        payload={
            "name": "<door_name>",
            "floorId": "<floor_id>",
            "accessControllerId": "<access_controller_id>",
            "deviceIos": _DOOR_CREATE_IOS,
            "configs": _ACCESS_STATION_PRO_DOOR_CREATE_CONFIGS,
            "doorType": "moody_as_acu",
        },
        response={
            "doors": [
                {
                    "accessControllerId": "<access_station_pro_id>",
                    "doorId": "<door_id>",
                    "floorId": "<floor_id>",
                    "name": "<door_name>",
                    "nearbyCameras": [
                        {
                            "cameraId": "<access_station_pro_id>",
                        }
                    ],
                }
            ]
        },
    ),
    "access_station_pro.list": Endpoint(
        method="GET",
        subdomain=API_GATEWAY_SUBDOMAIN,
        path="access/v3/user/access_controllers",
        payload={},
        response={
            "accessControllers": [
                {
                    "accessControllerId": "<access_station_pro_id>",
                    "name": "<access_station_pro_name>",
                    "organizationId": "<org_id>",
                    "serialNumber": "<serial_number>",
                    "vconductorModelId": "MOODY",
                },
            ]
        },
    ),
    "access_station_pro.delete": Endpoint(
        method="POST",
        subdomain="vcerberus",
        path="access_device/decommission",
        payload={"deviceId": "<access_station_pro_id>", "sharding": True},
        response={},
    ),
    "door.create": Endpoint(
        method="POST",
        subdomain=API_GATEWAY_SUBDOMAIN,
        path="door/create",
        payload={
            "name": "<door_name>",
            "floorId": "<floor_id>",
            "accessControllerId": "<access_controller_id>",
            "deviceIos": _DOOR_CREATE_IOS,
            "configs": _DOOR_CREATE_CONFIGS,
            "doorType": "standard",
        },
        response={
            "doors": [
                {
                    "accessControllerId": "<access_controller_id>",
                    "doorId": "<door_id>",
                    "floorId": "<floor_id>",
                    "name": "<door_name>",
                }
            ]
        },
    ),
    "door.list": Endpoint(
        method="GET",
        subdomain=API_GATEWAY_SUBDOMAIN,
        path="access/v3/user/doors",
        payload={},
        response={
            "doors": [
                {
                    "accessControllerId": "<access_controller_id>",
                    "doorId": "<door_id>",
                    "floorId": "<floor_id>",
                    "name": "<door_name>",
                }
            ]
        },
    ),
    "door.delete": Endpoint(
        method="POST",
        subdomain=API_GATEWAY_SUBDOMAIN,
        path="door/delete",
        payload={
            "doorId": "<door_id>",
        },
        response={},
    ),
    "door.pair_lpr_camera": Endpoint(
        method="POST",
        subdomain=API_GATEWAY_SUBDOMAIN,
        path="door/{door_id}/device_io",
        payload={
            "configs": {"lprCameraId": "<camera_id>"},
            "ioDeviceTypeName": "lpr-camera",
            "ioSlotType": "lpr-camera",
            "ioSlotIndex": 0,
        },
        response={
            "accessControllerId": "<access_controller_id>",
            "configs": {"lprCameraId": "<camera_id>"},
            "deviceId": "<door_id>",
        },
    ),
    "door.enable_face_unlock": Endpoint(
        method="POST",
        subdomain=API_GATEWAY_SUBDOMAIN,
        path="door/config/set",
        payload={
            "doorId": "<door_id>",
            "action": "grant",
            "paramName": "face-unlock-enabled",
            "paramValue": True,
        },
        response={
        "doorConfigParams" : [
            {
                "doorId": "<door_id>",
                "paramName": "face-unlock-enabled",
                "paramValue": True
            }
        ]
        },
    ),
    "door.mfa.card-code": Endpoint(
        method="POST",
        subdomain=API_GATEWAY_SUBDOMAIN,
        path="door/config/set",
        payload={
            "doorId": "<door_id>",
            "action": "grant",
            "paramName": "mfa-card-code-enabled",
            "paramValue": True,
        },
        response = {
            "doorConfigParams": [
                {
                    "doorId": "<door_id>",
                    "paramName": "mfa-card-code-enabled",
                    "paramValue": True
                }
            ]
        }
    ),
    "door.mfa.face-card": Endpoint(
        method="POST",
        subdomain=API_GATEWAY_SUBDOMAIN,
        path="door/config/set",
        payload={
            "doorId": "<door_id>",
            "action": "grant",
            "paramName": "mfa-face-card-enabled",
            "paramValue": True,
        },
        response = {
            "doorConfigParams": [
                {
                    "doorId": "<door_id>",
                    "paramName": "mfa-face-card-enabled",
                    "paramValue": True
                }
            ]
        }
    ),
    "door.mfa.face-code": Endpoint(
        method="POST",
        subdomain=API_GATEWAY_SUBDOMAIN,
        path="door/config/set",
        payload={
            "doorId": "<door_id>",
            "action": "grant",
            "paramName": "mfa-face-code-enabled",
            "paramValue": True,
        },
        response = {
            "doorConfigParams": [
                {
                    "doorId": "<door_id>",
                    "paramName": "mfa-face-code-enabled",
                    "paramValue": True
                }
            ]
        }
    ),
    "building.create": Endpoint(
        method="POST",
        subdomain="vprovision",
        path="building/create",
        payload={
            "name": "<building_name>",
            "organizationId": "<org_id>",
            "address": "<address>",
            "latitude": 0.0,
            "longitude": 0.0,
            "floors": [
                "<floor_name>",
            ],
        },
        response={
            "buildings": [
                {
                    "address": "<address>",
                    "buildingId": "<building_id>",
                    "floors": ["<floor_id>"],
                    "name": "<building_name>",
                    "organizationId": "<org_id>",
                },
            ],
            "floors": [
                {
                    "buildingId": "<building_id>",
                    "floorId": "<floor_id>",
                    "name": "<floor_name>",
                    "shortName": "1",
                    "sortOrder": 0,
                },
            ],
        },
    ),
    "building.list": Endpoint(
        method="GET",
        subdomain="vprovision",
        path="buildings?organizationId={org_id}",
        payload={},
        response=[
            {
                "address": "<address>",
                "buildingId": "<building_id>",
                "cacheId": "<building_id>",
                "floors": ["<floor_id>"],
                "latitude": 0.0,
                "longitude": 0.0,
                "name": "<building_name>",
                "organizationId": "<org_id>",
            },
        ],
    ),
    "building.delete": Endpoint(
        method="POST",
        subdomain="vprovision",
        path="building/delete",
        payload={"buildingId": "<building_id>"},
        response={
            "buildings": [
                {
                    "address": "<address>",
                    "buildingId": "<building_id>",
                    "floors": [],
                    "name": "<building_name>",
                    "organizationId": "<org_id>",
                }
            ],
        },
    ),
    "floor.list": Endpoint(
        method="GET",
        subdomain="vprovision",
        path="floors?organizationId={org_id}",
        payload={},
        response=[
            {
                "buildingId": "<building_id>",
                "cacheId": "<floor_1_id>",
                "floorId": "<floor_1_id>",
                "name": "G",
                "shortName": "1",
                "sortOrder": 0,
            },
        ],
    ),
    "floor.delete": Endpoint(
        method="POST",
        subdomain="vprovision",
        path="floor/delete",
        payload={"floorId": "<floor_id>"},
        response={
            "buildings": [
                {
                    "address": "<address>",
                    "buildingId": "<building_id>",
                    "floors": [],
                    "name": "<building_name>",
                    "organizationId": "<org_id>",
                }
            ],
        },
    ),
    "floorplan.delete": Endpoint(
        method="POST",
        subdomain="vprovision",
        path="floor_plan/delete",
        payload={"floorPlanId": "<floor_plan_id>"},
        response={},
    ),
    "visitor.list": Endpoint(
        method="POST",
        subdomain="vcerberus",
        path="access/v2/user/users/search",
        payload={
            "organizationId": "<org_id>",
            "must_queries": [{"bool": {"must": [{"term": {"is_visitor": True}}]}}],
            "status": [
                "access_granted",
            ],
            "status_filter_v2": True,
            "paging": {"pageSize": 99, "sortOrder": ["first_name:asc", "email:asc"]},
        },
        response={
            "users": [
                {
                    "email": "<visitor_email>",
                    "name": "<visitor_name>",
                    "organizationId": "<org_id>",
                    "userId": "<visitor_id>",
                },
            ],
        },
    ),
    "visitor.delete": Endpoint(
        method="POST",
        subdomain=API_GATEWAY_SUBDOMAIN,
        path="users/delete",
        payload={
            "organizationId": "<org_id>",
            "userIds": [
                "<user_id>",
            ],
        },
        response={},
    ),
    "access_card.list": Endpoint(
        method="POST",
        subdomain=API_GATEWAY_SUBDOMAIN,
        path="user/access_card/get",
        payload={
            "organizationId": "<org_id>",
            "userId": "<user_id>"
        },
        response={
            "accessCards": [
                {
                    "activationState": "active",
                    "active": True,
                    "autoExpiredTimestamp": None,
                    "cacheId": "<access_card_cache_id>",
                    "cardId": "<access_card_id>",
                    "cardParams": {
                        "cardNumber": 12345,
                        "facilityCode": 123
                    },
                    "cardType": "<card_type>",
                    "expirationPeriodBegin": 1786554036,
                    "lastUsed": "2026-08-12T18:53:43.530118",
                    "lastUsedEvent": "<last_event_id>",
                    "modified": 1786554036,
                    "organizationId": "<org_id>",
                    "scimManaged": False,
                    "systemManaged": None,
                    "systemManagedId": None,
                    "userId": "<user_id>"
                }
            ]
        }
    ),
    "access_card.delete": Endpoint(
        method="POST",
        subdomain=API_GATEWAY_SUBDOMAIN,
        path="user/access_card/delete",
        payload={
            "activationState": "active",
            "active": True,
            "autoExpiredTimestamp": None,
            "cacheId": "<access_card_cache_id>",
            "cardId": "<access_card_id>",
            "cardParams": {
                "cardNumber": 12345,
                "facilityCode": 123
            },
            "cardType": "<card_type>",
            "expirationPeriodBegin": 1786554036,
            "lastUsed": "2026-08-12T18:53:43.530118",
            "lastUsedEvent": "<last_event_id>",
            "modified": 1786554036,
            "organizationId": "<org_id>",
            "scimManaged": False,
            "systemManaged": None,
            "systemManagedId": None,
            "userId": "<user_id>"
        },
        response={}
    ),
    "access_group.create": Endpoint(
        method="POST",
        subdomain=API_GATEWAY_SUBDOMAIN,
        path="user_groups/add_group",
        payload={"organizationId": "<org_id>", "groupName": "<access_group_name>"},
        response={"groupId": "<access_group_id>"},
    ),
    "access_group.list": Endpoint(
        method="POST",
        subdomain=API_GATEWAY_SUBDOMAIN,
        path="user_groups/get",
        payload={"organizationId": "<org_id>"},
        response={
            "children": {
                "<access_group_id>": {
                    "name": "<access_group_name>",
                }
            },
        },
    ),
    "access_group.delete": Endpoint(
        method="POST",
        subdomain=API_GATEWAY_SUBDOMAIN,
        path="user_groups/remove_group",
        payload={"groupId": "<access_group_id>", "organizationId": "<org_id>"},
        response={},
    ),
    "access_group.add_user": Endpoint(
        method="POST",
        subdomain=API_GATEWAY_SUBDOMAIN,
        path="user_groups/bulk_add_users",
        payload={
            "userIds": ["<user_id>"],
            "groupIds": ["<group_id>"],
            "organizationId": "<org_id>",
        },
        response=None,
    ),
    "access_level.create": Endpoint(
        method="POST",
        subdomain="vcerberus",
        path="access/v2/user/schedules",
        payload={
            "priority": "SCHEDULE",
            "startDateTime": None,
            "endDateTime": None,
            "deleted": False,
            "doors": ["<door_id>"],
            "userGroups": ["<access_group_id>"],
            "events": _DOOR_EVENT,
            "name": "<access_level_name>",
            "sites": ["<site_id>"],
            "type": "USER",
            "defaultDoorLockState": "ACCESS_CONTROL",
            "defaultDoorPermissionState": "DENY",
        },
        response={
            "schedules": [
                {
                    "doors": ["<door_id>"],
                    "name": "<access_level_name>",
                    "organizationId": "<org_id>",
                    "scheduleId": "<schedule_id>",
                }
            ],
        },
    ),
    "access_level.list": Endpoint(
        method="GET",
        subdomain=API_GATEWAY_SUBDOMAIN,
        path="organizations/{org_id}/schedules",
        payload={},
        response={
            "schedules": [
                {
                    "doors": ["<door_id>"],
                    "name": "<access_level_name>",
                    "organizationId": "<org_id>",
                    "scheduleId": "<schedule_id>",
                }
            ],
        },
    ),
    "access_level.delete": Endpoint(
        method="DELETE",
        subdomain="vcerberus",
        path="access/v2/user/schedules/{schedule_id}",
        payload={},
        response={},
    ),
    "visitor_access_type.list": Endpoint(
        method="GET",
        subdomain=API_GATEWAY_SUBDOMAIN,
        path="access/v3/user/visit_types",
        payload={},
        response={
            "visitTypes": [
                {
                    "name": "<visitor_access_type_name>",
                    "organizationId": "<org_id>",
                    "visitTypeId": "<visitor_access_type_id>",
                }
            ]
        },
    ),
    "visitor_access_type.delete": Endpoint(
        method="DELETE",
        subdomain=API_GATEWAY_SUBDOMAIN,
        path="access/v2/user/visit_types/{visitor_access_type_id}",
        payload={},
        response={
            "deleted": True,
            "name": "<visitor_access_type_name>",
            "organizationId": "<org_id>",
            "visitTypeId": "<visitor_access_type_id>",
        },
    ),
    "visit.list": Endpoint(
        method="GET",
        subdomain="vcerberus",
        path="access/v3/user/visits?page_size={page_size}",
        payload={},
        response={
            "visits": [
                {
                    "visitId": "<visit_id>",
                    "visitorId": "<visitor_id>",
                    "organizationId": "<org_id>",
                    "name": "visit_name",
                },
            ],
        },
    ),
    "visit.delete": Endpoint(
        method="DELETE",
        subdomain=API_GATEWAY_SUBDOMAIN,
        path="access/v2/user/visits/{visit_id}",
        payload={},
        response={
            "deleted": True,
            "name": "<visit_name>",
            "organizationId": "<org_id>",
            "visitId": "<visit_id>",
            "visitorId": "<visitor_id>",
        },
    ),
    "scenario.create": Endpoint(
        method="POST",
        subdomain="vcerberus",
        path="access/v2/user/lockdowns",
        payload={
            "name": "<scenario_name>",
            "sites": ["<site_id>"],
            "doorConfigurations": [],
            "userGroupsWithDoorAccess": [],
            "userGroupsWithEnableAccess": ["<access_group_id>"],
            "userGroupsWithDisableAccess": ["<access_group_id>"],
            "message": "<scenario_message>",
            # Scenario Types: "EVACUATE" || "SHELTER" || "LOCKDOWN" || "SECURE" || "HOLD">
            "scenarioType": "<scenario_type>",
        },
        response={
            "lockdowns": [
                {
                    "lockdownId": "<scenario_id>",
                    "message": "",
                    "name": "<scenario_name>",
                    "organizationId": "<org_id>",
                    "scenarioType": "<scenario_type>",
                }
            ]
        },
    ),
    "scenario.list": Endpoint(
        method="GET",
        subdomain=API_GATEWAY_SUBDOMAIN,
        path="organizations/{org_id}/lockdowns",
        payload={},
        response={
            "lockdowns": [
                {
                    "lockdownId": "<scenario_id>",
                    "message": "<scenario_message>",
                    "name": "<scenario_name>",
                    "organizationId": "<org_id>",
                    "scenarioType": "LOCKDOWN",
                },
            ]
        },
    ),
    "scenario.delete": Endpoint(
        method="DELETE",
        subdomain="vcerberus",
        # NOTE: curly braces — resolve() substitutes {placeholders} via
        # str.format; angle brackets would be sent literally.
        path="access/v2/user/lockdowns/{scenario_id}",
        payload={},
        response={},
    ),
    "schedule.create.mfa": Endpoint(
        method="PUT",
        subdomain=API_GATEWAY_SUBDOMAIN,
        path="organizations/{org_id}/schedules",
        payload={
            "sitesEnabled": True,
            "schedules": [
                {
                    "doors": ["<door_id>"],
                    "events": _MFA_DOOR_EVENT,
                    "name": "<schedule_name>",
                    "type": "DOOR",
                    "priority": "SCHEDULE",
                    "defaultDoorLockState": "ACCESS_CONTROL",
                }
            ],
        },
        response={},
    ),
    "schedule.list": Endpoint(
        method="GET",
        subdomain=API_GATEWAY_SUBDOMAIN,
        path="organizations/{org_id}/schedules",
        # Shared with access_level.list. `type` distinguishes the rows:
        #   DOOR       → door schedule (this category)
        #   SUPERVISOR → supervisor half of a door schedule; linked via
        #                the door schedule's supervisorScheduleId and its
        #                own doorScheduleId back-pointer
        #   USER       → access level (see access_level.list)
        payload={},
        response={
            "schedules": [
                {
                    "name": "<schedule_name>",
                    "organizationId": "<org_id>",
                    "priority": "SCHEDULE",
                    "scheduleId": "<schedule_id>",
                    "type": "DOOR",
                    "supervisorScheduleId": "<supervisor_schedule_id>",
                    "events": ["<full event objects>"],
                },
            ]
        },
    ),
    "schedule.delete": Endpoint(
        method="PUT",
        subdomain="vcerberus",
        path="organizations/{org_id}/schedules",
        # Upsert-style PUT: each schedule object from schedule.list must
        # be echoed back VERBATIM (full events array, type, ids, …) with
        # deleted=True — a trimmed body is rejected with "Missing data
        # for required field". A door schedule that has a paired
        # supervisor schedule must send BOTH objects in the schedules
        # array. See VerkadaInternalAPIClient.delete_schedule.
        payload={
            "sitesEnabled": True,
            "schedules": ["<full schedule object>", "...deleted: True"],
        },
        response={},
    ),
    # ── Workplace ────────────────────────────────────────────────────
    "guest.create": Endpoint(
        method="POST",
        subdomain="vdoorman",
        path="site/org/{org_id}",
        payload={
            "siteId": "<site_id>",
            "fullAddress": "<full_address>",
            "latitude": 0.0,
            "longitude": 0.0,
            "countryCode": "<country_code>",
        },
        response={"siteId": "<guest_site_id>"},
    ),
    "guest.activate_trial": Endpoint(
        method="POST",
        subdomain="vdoorman",
        path="guest/trial/org/{org_id}/site/{site_id}",
        payload={"productType": "GUEST"},
        response={
            "softwareTrial": {
                "organizationId": "<org_id>",
                "productPlanType": "GUEST",
                "siteId": "<site_id>",
            }
        },
    ),
    "guest.list": Endpoint(
        # Guest sites, as the Guest app lists them (internal; replaces the
        # public API's guest/v1/sites for Decommission).
        method="GET",
        subdomain="vdoorman",
        path="site/org/{org_id}",
        payload={},
        response={"sites": [{"siteId": "<site_id>", "siteName": "<site_name>"}]},
    ),
    "guest.delete": Endpoint(
        method="DELETE",
        subdomain="vdoorman",
        path="site/org/{org_id}?siteId={site_id}",
        payload={},
        response={"siteId": "<site_id>"},
    ),
    "guest_type.create": Endpoint(
        method="POST",
        subdomain="vdoorman",
        path="visitor_type/v2/standard/org/{org_id}/site/{site_id}",
        payload={
            "visitorType": {
                "checkInOutConfig": "CHECK_IN_AND_OUT",
                "guestSelfSignOut": "ANYWHERE",
                "printBadge": True,
                "reviewVisitInformation": True,
                "invitesEnabled": True,
                "enableFastpass": True,
                "enableFaceMatch": False,
                "hasVisitorTypeAccessEnabled": False,
                "badgeConfig": {
                    "printName": True,
                    "printHost": True,
                    "printPhoto": True,
                    "enableBotd": True,
                    "badgeOrientationPortrait": {
                        "defaultSelectedValue": False,
                        "rules": [],
                    },
                    "badgeBorderTreatment": {
                        "defaultSelectedValue": "NONE",
                        "rules": [],
                    },
                    "badgeBorderColor": {
                        "defaultSelectedValue": "#000000",
                        "rules": [],
                    },
                },
                "badgeConfigV2": {
                    "designedFor": "monochrome",
                    "featureMode": "basic",
                    "badgeStyles": {
                        "orientation": "landscape",
                        "border": {
                            "style": "NONE",
                            "color": "#000000",
                            "colorValue": {"hex": "#000000"},
                        },
                        "background": {
                            "color": "",
                            "colorValue": {
                                "hex": "",
                                "colorSchemeKey": "backgroundColor",
                            },
                        },
                    },
                    "components": [
                        {
                            "id": "guestPhoto-a7ba8af2-4094-43df-999b-16ba3d9ccc99",
                            "type": "guestPhoto",
                            "landscape": {
                                "x": 17,
                                "y": 0,
                                "width": 15,
                                "height": 15,
                                "imageShape": "circle",
                                "zIndex": 0,
                            },
                            "portrait": {
                                "x": 0,
                                "y": 8,
                                "width": 14,
                                "height": 14,
                                "imageShape": "circle",
                                "zIndex": 0,
                            },
                            "commonData": {},
                        },
                        {
                            "id": "logo-c5c3513a-e520-4002-b985-f6a7057b2e1f",
                            "type": "logo",
                            "landscape": {
                                "x": 0,
                                "y": 0,
                                "width": 13,
                                "height": 3,
                                "layoutAlignment": "flex-start",
                                "zIndex": 0,
                            },
                            "portrait": {
                                "x": 0,
                                "y": 0,
                                "width": 12,
                                "height": 3,
                                "layoutAlignment": "flex-start",
                                "zIndex": 0,
                            },
                            "commonData": {},
                        },
                        {
                            "id": "badgeDate-f280b3e0-70b6-48d8-8115-74cd2f5710a6",
                            "type": "badgeDate",
                            "landscape": {
                                "x": 27,
                                "y": 17,
                                "width": 5,
                                "height": 7,
                                "textStyle": "transparentBackground",
                                "dateLayout": "vertical",
                                "zIndex": 0,
                            },
                            "portrait": {
                                "x": 19,
                                "y": 0,
                                "width": 5,
                                "height": 7,
                                "textStyle": "transparentBackground",
                                "dateLayout": "vertical",
                                "zIndex": 0,
                            },
                            "commonData": {},
                        },
                        {
                            "id": "guestType-5392228b-a57f-46f4-b318-7b755fdd2346",
                            "type": "guestType",
                            "landscape": {
                                "x": 0,
                                "y": 4,
                                "width": 16,
                                "height": 4,
                                "layoutAlignment": "flex-start",
                                "zIndex": 0,
                            },
                            "portrait": {
                                "x": 0,
                                "y": 4,
                                "width": 17,
                                "height": 3,
                                "layoutAlignment": "flex-start",
                                "zIndex": 0,
                            },
                            "commonData": {},
                        },
                        {
                            "id": "guestName-4f90cd88-da37-45a4-9265-c4894879c8e8",
                            "type": "guestName",
                            "landscape": {
                                "x": 0,
                                "y": 15,
                                "width": 27,
                                "height": 9,
                                "textStyle": "transparentBackground",
                                "layoutAlignment": "flex-start",
                                "nameLines": "double",
                                "nameParts": "full",
                                "zIndex": 0,
                            },
                            "portrait": {
                                "x": 0,
                                "y": 23,
                                "width": 24,
                                "height": 9,
                                "textStyle": "transparentBackground",
                                "layoutAlignment": "flex-start",
                                "nameLines": "double",
                                "nameParts": "full",
                                "zIndex": 0,
                            },
                            "commonData": {},
                        },
                    ],
                },
                "translations": {
                    "en_US": {
                        "name": "GuestTypeName",
                        "locale": "en_US",
                        "closingMessage": "Thank you for signing into Site 1",
                    }
                },
                "issueWifiCredentials": False,
                "smsWifiCredentials": False,
                "sendHostWifiCredentials": False,
                "_visitorTypeCategory": "STANDARD",
            }
        },
        response={
            "visitorType": {
                "accessControlVisitorType": None,
                "allowIntercomCheckIn": False,
                "allowSelfSignOut": False,
                "applicantVisitorTypeIds": [],
                "attendance": None,
                "attendanceCode": None,
                "badgeConfig": {
                    "badgeBorderColor": {
                        "defaultSelectedValue": "#000000",
                        "rules": [],
                    },
                    "badgeBorderTreatment": {
                        "defaultSelectedValue": "NONE",
                        "rules": [],
                    },
                    "badgeOrientationPortrait": {
                        "defaultSelectedValue": False,
                        "rules": [],
                    },
                    "enableBotd": True,
                    "printHost": True,
                    "printName": True,
                    "printPhoto": True,
                    "printQuestionResponse": None,
                },
                "badgeConfigV2": {
                    "badgeStyles": {
                        "background": {
                            "color": "",
                            "colorValue": {
                                "colorSchemeKey": "backgroundColor",
                                "hex": "",
                            },
                        },
                        "border": {
                            "color": "#000000",
                            "colorValue": {"hex": "#000000"},
                            "style": "NONE",
                        },
                        "orientation": "landscape",
                    },
                    "components": [
                        {
                            "commonData": {},
                            "id": "guestPhoto-a7ba8af2-4094-43df-999b-16ba3d9ccc99",
                            "landscape": {
                                "height": 15,
                                "imageShape": "circle",
                                "width": 15,
                                "x": 17,
                                "y": 0,
                                "zIndex": 0,
                            },
                            "portrait": {
                                "height": 14,
                                "imageShape": "circle",
                                "width": 14,
                                "x": 0,
                                "y": 8,
                                "zIndex": 0,
                            },
                            "type": "guestPhoto",
                        },
                        {
                            "commonData": {},
                            "id": "logo-c5c3513a-e520-4002-b985-f6a7057b2e1f",
                            "landscape": {
                                "height": 3,
                                "layoutAlignment": "flex-start",
                                "width": 13,
                                "x": 0,
                                "y": 0,
                                "zIndex": 0,
                            },
                            "portrait": {
                                "height": 3,
                                "layoutAlignment": "flex-start",
                                "width": 12,
                                "x": 0,
                                "y": 0,
                                "zIndex": 0,
                            },
                            "type": "logo",
                        },
                        {
                            "commonData": {},
                            "id": "badgeDate-f280b3e0-70b6-48d8-8115-74cd2f5710a6",
                            "landscape": {
                                "dateLayout": "vertical",
                                "height": 7,
                                "textStyle": "transparentBackground",
                                "width": 5,
                                "x": 27,
                                "y": 17,
                                "zIndex": 0,
                            },
                            "portrait": {
                                "dateLayout": "vertical",
                                "height": 7,
                                "textStyle": "transparentBackground",
                                "width": 5,
                                "x": 19,
                                "y": 0,
                                "zIndex": 0,
                            },
                            "type": "badgeDate",
                        },
                        {
                            "commonData": {},
                            "id": "guestType-5392228b-a57f-46f4-b318-7b755fdd2346",
                            "landscape": {
                                "height": 4,
                                "layoutAlignment": "flex-start",
                                "width": 16,
                                "x": 0,
                                "y": 4,
                                "zIndex": 0,
                            },
                            "portrait": {
                                "height": 3,
                                "layoutAlignment": "flex-start",
                                "width": 17,
                                "x": 0,
                                "y": 4,
                                "zIndex": 0,
                            },
                            "type": "guestType",
                        },
                        {
                            "commonData": {},
                            "id": "guestName-4f90cd88-da37-45a4-9265-c4894879c8e8",
                            "landscape": {
                                "height": 9,
                                "layoutAlignment": "flex-start",
                                "nameLines": "double",
                                "nameParts": "full",
                                "textStyle": "transparentBackground",
                                "width": 27,
                                "x": 0,
                                "y": 15,
                                "zIndex": 0,
                            },
                            "portrait": {
                                "height": 9,
                                "layoutAlignment": "flex-start",
                                "nameLines": "double",
                                "nameParts": "full",
                                "textStyle": "transparentBackground",
                                "width": 24,
                                "x": 0,
                                "y": 23,
                                "zIndex": 0,
                            },
                            "type": "guestName",
                        },
                    ],
                    "designedFor": "monochrome",
                    "featureMode": "basic",
                },
                "badgeImageIds": [],
                "blocksPrinting": False,
                "checkApplicantVisitorType": False,
                "checkInOutConfig": "CHECK_IN_AND_OUT",
                "contactUserIds": [],
                "displayConfigBySite": {
                    "a7779867-99a9-47ef-b061-f21a0904c95d": {
                        "hidden": False,
                        "hideFromDevice": False,
                        "hideFromInvite": False,
                        "hideFromReceptionist": False,
                        "hideFromWeb": False,
                        "inviteAlias": "guesttypename",
                        "order": 0,
                        "siteId": "a7779867-99a9-47ef-b061-f21a0904c95d",
                    }
                },
                "enableFaceMatch": False,
                "enableFastpass": True,
                "form": {
                    "deleted": False,
                    "formId": "924844fb-3cdb-4e53-91d9-b6ff7eb1075f",
                    "formType": "STANDARD",
                    "nextVersion": None,
                    "orgId": "12f68738-490f-4261-9878-0ca6352c4f8d",
                    "published": False,
                    "replacedWith": None,
                    "scanIdStep": None,
                    "siteId": "a7779867-99a9-47ef-b061-f21a0904c95d",
                    "startingStepId": "919deea7-a122-4610-922f-bda0bea7292a",
                    "steps": {
                        "5fb23446-d30b-4e60-bfbc-1495812aa9fb": {
                            "blockPrinting": False,
                            "nextStepId": "b6110bec-c0e5-4445-82bf-496d953be491",
                            "shouldRemember": False,
                            "stableKey": "131da13b-d1c8-44bb-a4f1-45e0d8e60d7f",
                            "stepId": "5fb23446-d30b-4e60-bfbc-1495812aa9fb",
                            "stepType": "VisitorNameStep",
                        },
                        "919deea7-a122-4610-922f-bda0bea7292a": {
                            "blockPrinting": False,
                            "nextStepId": "5fb23446-d30b-4e60-bfbc-1495812aa9fb",
                            "requireEitherPhoneOrEmail": True,
                            "requireEmail": False,
                            "requirePhone": False,
                            "shouldRemember": True,
                            "stableKey": "b2067db5-395d-4bd2-a4c5-f21d2249ebbc",
                            "stepId": "919deea7-a122-4610-922f-bda0bea7292a",
                            "stepType": "ContactInfoStep",
                        },
                        "b6110bec-c0e5-4445-82bf-496d953be491": {
                            "blockPrinting": False,
                            "detectFace": False,
                            "identityListId": None,
                            "nextStepId": None,
                            "shouldRemember": False,
                            "stableKey": "8ead45e0-d773-4f10-8755-926f849abee5",
                            "stepId": "b6110bec-c0e5-4445-82bf-496d953be491",
                            "stepType": "GuestPhotoStep",
                        },
                    },
                },
                "guestSelfSignOut": "ANYWHERE",
                "hasReceptionistForm": False,
                "hidden": None,
                "invitesEnabled": True,
                "issueWifiCredentials": False,
                "minimumAppVersion": None,
                "orgId": "12f68738-490f-4261-9878-0ca6352c4f8d",
                "printBadge": True,
                "receptionistForm": None,
                "reviewVisitInformation": True,
                "securityScreenReviewers": [],
                "sendHostWifiCredentials": False,
                "siteId": "a7779867-99a9-47ef-b061-f21a0904c95d",
                "smsWifiCredentials": False,
                "translations": {
                    "en_US": {
                        "closingMessage": "Thank you for signing into Site 1",
                        "locale": "en_US",
                        "name": "GuestTypeName",
                        "welcomeInfo": None,
                    }
                },
                "visitorTypeAccessControl": None,
                "visitorTypeId": "a74b5bf8-3b12-4ac3-ad6c-f667c1f7b9f3",
            }
        },
    ),
    "guest_type.list": Endpoint(
        method="GET",
        subdomain="vdoorman",
        path="site/settings/v2/org/{org_id}/site/{site_id}",
        payload={},
        response={
            "sites": [
                {
                    "siteId": "<site_id>",
                    "siteName": "<site_name>",
                }
            ],
            "standardVisitorTypes": {
                "<guest_type_id>": {
                    "orgId": "<org_id>",
                    "siteId": "<site_id>",
                    "visitorTypeId": "<guest_type_id>",
                }
            },
            "visitorTypes": [],
        },
    ),
    "guest_type.delete": Endpoint(
        method="DELETE",
        subdomain="vdoorman",
        path="visitor_type/v2/standard/org/{org_id}/site/{site_id}?visitorTypeId={guest_type_id}",
        payload={},
        response={},
    ),
    "mailroom.activate_trial": Endpoint(
        method="POST",
        subdomain="vdoorman",
        path="package_org/preferences/{org_id}",
        payload={},
        response={"orgId": "<org_id>"},
    ),
    "mailroom.create": Endpoint(
        method="POST",
        subdomain="vdoorman",
        path="package_site/org/{org_id}",
        payload={
            "siteId": "<site_id>",
            "latitude": 0,
            "longitude": 0,
            "fullAddress": "<address>",
        },
        response={"packageLocationId": "<mailroom_id>", "siteId": "<site_id>"},
    ),
    "mailroom.list": Endpoint(
        method="GET",
        subdomain="vdoorman",
        path="package_site/org/{org_id}",
        payload={},
        response={
            "package_sites": [
                {
                    "orgId": "<org_id>",
                    "packageLocations": [
                        {
                            "locationName": "<mailroom_location_name>",
                            "packageLocationId": "<mailroom_id>",
                        }
                    ],
                    "siteId": "<site_id>",
                    "siteName": "<site_name>",
                }
            ]
        },
    ),
    "mailroom.delete": Endpoint(
        method="DELETE",
        subdomain="vdoorman",
        path="package_site/org/{org_id}?siteId={site_id}",
        payload={},
        response={"siteId": "<site_id>"},
    ),
    # ── Alarms ───────────────────────────────────────────────────────
    "alarm.site.create": Endpoint(
        method="POST",
        subdomain="vagent",
        path="response/site/create",
        payload={
            "organizationId": "<org_id>",
            "siteId": "<site_id>",
            "businessName": "<business_name>",
            "permitNumber": "",
            "locationRequest": {
                "latitude": 0,
                "longitude": 0,
                "street1": "<address>",
                "street2": "",
                "apt": "",
                "city": "<city>",
                "state": "<state>",
                "zipcode": "<zipcode>",
                "country": "<country_code>",
                "timezone": "<timezone>",
            },
            "adminContactUserId": "<user_id>",
        },
        response={
            "responseSite": {
                "id": "<alarm_site_id>",
                "siteId": "<site_id>",
                "orgId": "<org_id>",
                "businessName": "<business_name>",
                "locationId": "<location_id>",
            },
            "responseConfigs": [
                {
                    "id": "<alarm_response_id>",
                    "responseSiteId": "<alarm_site_id>",
                    "locationId": "<location_id>",
                    "name": "<response_name>",
                }
            ],
        },
    ),
    "alarm.site.activate_trial": Endpoint(
        method="POST",
        subdomain="vagent",
        path="site/software_trial/create",
        payload={"siteId": "<site_id>"},
        response={},
    ),
    "alarm.site.list": Endpoint(
        method="POST",
        subdomain="vagent",
        path="response/site/get",
        payload={
            "includeMonthlyAlarmCounts": True,
            "includePsapInfo": True,
            "siteId": "<site_id>",
        },
        response={
            "responseSite": {
                "id": "<alarm_site_id>",
                "siteId": "<site_id>",
                "orgId": "<org_id>",
                "businessName": "<business_name>",
                "locationId": "<location_id>",
                "adminContactUserId": "<user_id>",
            },
            "location": {
                "id": "<location_id>",
            },
            "responseConfigs": [
                {
                    "id": "<alarm_response_id>",
                    "responseSiteId": "<alarm_site_id>",
                    "locationId": "<location_id>",
                }
            ],
        },
    ),
    "alarm.site.set_self_monitored": Endpoint(
        method="POST",
        subdomain="vagent",
        path="response/config/update",
        payload={
            "siteId": "<site_id>",
            "responseConfigId": "<alarm_response_id>",
            "updateType": "CONFIG_UPDATE_TYPE_UPDATE_RESPONSE_LEVEL",
            "updateResponseLevelInput": {
                "responseLevel": "RESPONSE_LEVEL_SELF_MONITORED"
            },
        },
        response={
            "responseConfig": {
                "id": "<alarm_response_id>",
                "responseSiteId": "<alarm_site_id>",
                "locationId": "<location_id>",
                "responseLevel": "RESPONSE_LEVEL_SELF_MONITORED",
                "name": "<response_name>",
            },
            "location": {
                "id": "<location_id>",
            },
        },
    ),
    "alarm.site.delete": Endpoint(
        method="POST",
        subdomain="vagent",
        path="response/site/delete",
        payload={"siteId": "<site_id>", "responseSiteId": "<alarm_site_id>"},
        response={},
    ),
    "alarm.system.create": Endpoint(
        method="POST",
        subdomain="vproconfig",
        path="alarm_system/create",
        payload={"orgId": "<org_id>", "siteId": "<site_id>"},
        response={
            "alarmSystem": {
                "id": "<alarm_system_id>",
                "organizationId": "<org_id>",
                "siteId": "<site_id>",
            }
        },
    ),
    "alarm.system.list": Endpoint(
        method="POST",
        subdomain="vproconfig",
        path="alarm_system/list",
        payload={"orgId": "<org_id>"},
        response={
            "alarmSystems": [
                {
                    "id": "<alarm_system_id>",
                    "organizationId": "<org_id>",
                    "siteId": "<site_id>",
                    "leaderDeviceId": "<alarm_panel_id>",
                }
            ]
        },
    ),
    "alarm.system.delete": Endpoint(
        method="POST",
        subdomain="vproconfig",
        path="alarm_system/delete",
        payload={"alarmSystemId": "<alarm_system_id>"},
        response={
            "alarmSystem": {
                "id": "<alarm_system_id>",
                "organizationId": "<org_id>",
                "siteId": "<site_id>",
                "deleted": True,
            }
        },
    ),
    "alarm.system.create_general_keycode": Endpoint(
        method="POST",
        subdomain="vproconfig",
        path="keycode/create",
        payload={
            "alarmSystemId": "<alarm_system_id>",
            "name": "<keycode_name>",
            "code": "<keycode>",
            "partitionIds": [],
            "firePermissionScope": "FIRE_PERMISSION_SCOPE_OPERATION",
        },
        response={
            "keycode": {
                "id": "<keycode_id>",
                "code": "<keycode>",
                "name": "<keycode_name>",
                "isDuressCode": False,
                "alarmSystemId": "<alarm_system_id>",
                "isPartitionScoped": False,
                "partitionScopes": [],
                "firePermissionScope": "FIRE_PERMISSION_SCOPE_OPERATION",
                "isIntrusion": True,
            }
        },
    ),
    "alarm.partition.create": Endpoint(
        method="POST",
        subdomain="vproconfig",
        path="partition/create",
        payload={
            "alarmSystemId": "<alarm_system_id>",
            "name": "<partition_name>",
        },
        response={
            "partition": {
                "id": "<partition_id>",
                "alarmSystemId": "<alarm_system_id>",
                "name": "<partition_name>",
                "responseConfigId": "<alarm_response_id>",
            }
        },
    ),
    "alarm.partition.assign_response": Endpoint(
        method="POST",
        subdomain="vproconfig",
        path="partition/assign_response_config",
        payload={
            "partitionId": "<partition_id>",
            "responseConfigId": "<alarm_response_id>",
        },
        response={
            "partition": {
                "id": "<partition_id>",
                "alarmSystemId": "<alarm_system_id>",
                "name": "<partition_name>",
                "responseConfigId": "<alarm_response_id>",
            }
        },
    ),
    "alarm.partition.list": Endpoint(
        method="POST",
        subdomain="vproconfig",
        path="alarm_system/get_all",
        payload={
            "alarmSystemId": "<alarm_system_id>",
        },
        response={
            "partitions": [
                {
                    "id": "<partition_id>",
                    "alarmSystemId": "<alarm_system_id>",
                    "name": "<partition_name>",
                    "responseConfigId": "<alarm_response_id>",
                },
            ],
        },
    ),
    "alarm.partition.delete": Endpoint(
        method="POST",
        subdomain="vproconfig",
        path="partition/delete",
        payload={"partitionId": "<partition_id>"},
        response={
            "partition": {
                "id": "<partition_id>",
                "alarmSystemId": "<alarm_system_id>",
                "name": "<partition_name>",
                "deleted": True,
                "responseConfigId": "<alarm_response_id>",
            }
        },
    ),
    "alarm.guard.create": Endpoint(
        method="POST",
        subdomain="vguard",
        path="web/create_guard",
        payload={
            "siteId": "<site_id>",
            "organizationId": "<org_id>",
            "name": "camera_partition_name",
            "cameraIds": ["<camera_id>"],
            "cameras": [{"cameraId": "<camera_id>", "cameraType": "C_M42_SECURE"}],
            "schedules": [
                {
                    "startDay": 0,
                    "startMinute": 1110,
                    "startSecond": 0,
                    "endDay": 1,
                    "endMinute": 390,
                    "endSecond": 0,
                },
                {
                    "startDay": 1,
                    "startMinute": 1110,
                    "startSecond": 0,
                    "endDay": 2,
                    "endMinute": 390,
                    "endSecond": 0,
                },
                {
                    "startDay": 2,
                    "startMinute": 1110,
                    "startSecond": 0,
                    "endDay": 3,
                    "endMinute": 390,
                    "endSecond": 0,
                },
                {
                    "startDay": 3,
                    "startMinute": 1110,
                    "startSecond": 0,
                    "endDay": 4,
                    "endMinute": 390,
                    "endSecond": 0,
                },
                {
                    "startDay": 4,
                    "startMinute": 1110,
                    "startSecond": 0,
                    "endDay": 5,
                    "endMinute": 390,
                    "endSecond": 0,
                },
                {
                    "startDay": 5,
                    "startMinute": 1110,
                    "startSecond": 0,
                    "endDay": 6,
                    "endMinute": 390,
                    "endSecond": 0,
                },
                {
                    "startDay": 6,
                    "startMinute": 1110,
                    "startSecond": 0,
                    "endDay": 0,
                    "endMinute": 390,
                    "endSecond": 0,
                },
            ],
            "responseConfigId": "<alarm_response_id>",
            "timezoneIana": "<timezone>",
        },
        response={
            "guard": {
                "id": "<guard_id>",
                "orgId": "<org_id>",
                "siteId": "<site_id>",
                "name": "<camera_partition_name>",
                "isActive": False,
                "responseConfigId": "<alarm_response_id>",
                "timezoneIana": "<timezone>",
            },
            "guardCameras": [
                {
                    "id": "<guard_camera_id>",
                    "guardId": "<guard_id>",
                    "cameraId": "<camera_id>",
                }
            ],
        },
    ),
    "alarm.guard.list": Endpoint(
        method="POST",
        subdomain="vguard",
        path="web/guard_list",
        payload={"organizationId": "org_id", "siteId": "site_id"},
        response={
            "guards": [
                {
                    "id": "<guard_id>",
                    "orgId": "<org_id>",
                    "siteId": "<site_id>",
                    "name": "<camera_partition_name>",
                    "responseConfigId": "<response_id>",
                    "timezoneIana": "<timezone>",
                    "cameraIds": ["<camera_id>"],
                }
            ]
        },
    ),
    "alarm.guard.delete": Endpoint(
        method="POST",
        subdomain="vguard",
        path="web/delete_guard",
        payload={"guardId": "<guard_id>"},
        response={},
    ),
    "alarm.panel.create": Endpoint(
        method="POST",
        subdomain="vproconfig",
        path="unassigned_device/setup_colossus",
        payload={
            "alarmSystemId": "<alarm_system_id>",
            "deviceId": "<alarm_panel_id>",
            "name": "<alarm_panel_name>",
            "replaceExistingLeader": False,
        },
        response={
            "device": {
                "id": "<alarm_panel_id>",
                "alarmSystemId": "<alarm_system_id>",
                "name": "<alarm_panel_name>",
                "verkadaDeviceConfig": {
                    "serialNumber": "<serial_number>",
                },
            }
        },
    ),
    "alarm.panel.list": Endpoint(
        method="POST",
        subdomain="vproconfig",
        path="alarm_system/get_devices",
        payload={
            "alarmSystemId": "<alarm_system_id>",
        },
        response={
            "devices": [
                {
                    "id": "<alarm_panel_id>",
                    "alarmSystemId": "<alarm_system_id>",
                    "name": "<alarm_panel_name>",
                    "type": "COLOSSUS",
                    "verkadaDeviceConfig": {"serialNumber": "<serial_number>"},
                },
            ]
        },
    ),
    "alarm.panel.delete": Endpoint(
        method="POST",
        subdomain="vproconfig",
        path="device/decommission",
        payload={"deviceId": "<alarm_panel_id>"},
        response={"error": ""},
    ),
    "alarm.keypad.create": Endpoint(
        method="POST",
        subdomain="vproconfig",
        path="unassigned_device/set_up_alarm_device",
        payload={
            "alarmSystemId": "<alarm_system_id>",
            "deviceId": "<alarm_keypad_id>",
            "serialNumber": "<serial_number>",
            "name": "<alarm_keypad_name>",
        },
        response={
            "device": {
                "id": "<alarm_keypad_id>",
                "alarmSystemId": "<alarm_system_id>",
                "name": "<alarm_keypad_name>",
                "type": "SYLVIE",
                "verkadaDeviceConfig": {"serialNumber": "<serial_number>"},
            }
        },
    ),
    "alarm.keypad.list": Endpoint(
        method="POST",
        subdomain="vproconfig",
        path="alarm_system/get_devices",
        payload={
            "alarmSystemId": "<alarm_system_id>",
        },
        response={
            "devices": [
                {
                    "id": "<alarm_keypad_id>",
                    "alarmSystemId": "<alarm_system_id>",
                    "name": "<alarm_keypad_name>",
                    "type": "SYLVIE",
                    "verkadaDeviceConfig": {"serialNumber": "<serial_number>"},
                },
            ]
        },
    ),
    "alarm.keypad.delete": Endpoint(
        method="POST",
        subdomain="vproconfig",
        path="device/decommission",
        payload={"deviceId": "<alarm_keypad_id>"},
        response={"error": ""},
    ),
    "alarm.expander.create": Endpoint(
        method="POST",
        subdomain="vproconfig",
        path="unassigned_device/set_up_alarm_device",
        payload={
            "alarmSystemId": "<alarm_system_id>",
            "deviceId": "<alarm_expander_id>",
            "serialNumber": "<serial_number>",
            "name": "<alarm_expander_name>",
        },
        response={
            "device": {
                "id": "<alarm_expander_id>",
                "alarmSystemId": "<alarm_system_id>",
                "name": "<alarm_expander_name>",
                "type": "KURIBO",
                "verkadaDeviceConfig": {"serialNumber": "<serial_number>"},
            }
        },
    ),
    "alarm.expander.list": Endpoint(
        method="POST",
        subdomain="vproconfig",
        path="alarm_system/get_devices",
        payload={
            "alarmSystemId": "<alarm_system_id>",
        },
        response={
            "devices": [
                {
                    "id": "<alarm_expander_id>",
                    "alarmSystemId": "<alarm_system_id>",
                    "name": "<alarm_expander_name>",
                    "type": "KURIBO",
                    "verkadaDeviceConfig": {"serialNumber": "<serial_number>"},
                },
            ]
        },
    ),
    "alarm.expander.delete": Endpoint(
        method="POST",
        subdomain="vproconfig",
        path="device/decommission",
        payload={"deviceId": "<alarm_expander_id>"},
        response={"error": ""},
    ),
    "alarm.wireless_contact_sensor.create": Endpoint(
        method="POST",
        subdomain="vproconfig",
        path="unassigned_device/bulk_set_up_wireless_contact_sensor",
        payload={
            "alarmSystemId": "<alarm_system_id>",
            "devices": [
                {
                    "deviceId": "<wireless_contact_sensor_id>",
                    "alarmSystemId": "<alarm_system_id>",
                    "serialNumber": "<serial_number>",
                    "name": "<wireless_contact_sensor_name>",
                    "partitionId": "<partition_id>",
                    "contactSensorType": "DOOR",
                }
            ],
        },
        response={
            "devices": [
                {
                    "id": "<wireless_contact_sensor_id>",
                    "alarmSystemId": "<alarm_system_id>",
                    "name": "<wireless_contact_sensor_name>",
                    "type": "WIRELESS_CONTACT_SENSOR",
                    "partitionId": "<partition_id>",
                    "verkadaDeviceConfig": {"serialNumber": "<serial_number>"},
                }
            ]
        },
    ),
    "alarm.wireless_contact_sensor.list": Endpoint(
        method="POST",
        subdomain="vproconfig",
        path="alarm_system/get_devices",
        payload={
            "alarmSystemId": "<alarm_system_id>",
        },
        response={
            "devices": [
                {
                    "id": "<wireless_contact_sensor_id>",
                    "alarmSystemId": "<alarm_system_id>",
                    "name": "<wireless_contact_sensor_name>",
                    "type": "WIRELESS_CONTACT_SENSOR",
                    "partitionId": "<partition_id>",
                    "verkadaDeviceConfig": {"serialNumber": "<serial_number>"},
                },
            ]
        },
    ),
    "alarm.wireless_contact_sensor.delete": Endpoint(
        method="POST",
        subdomain="vproconfig",
        path="device/decommission",
        payload={"deviceId": "<wireless_contact_sensor_id>"},
        response={"error": ""},
    ),
    "alarm.wireless_panic_button.create": Endpoint(
        method="POST",
        subdomain="vproconfig",
        path="unassigned_device/bulk_set_up_wireless_panic_button",
        payload={
            "alarmSystemId": "<alarm_system_id>",
            "devices": [
                {
                    "deviceId": "<wireless_panic_button_id>",
                    "alarmSystemId": "<alarm_system_id>",
                    "serialNumber": "<serial_number>",
                    "name": "<wireless_panic_button_name>",
                    "partitionId": "<partition_id>",
                    "gestureType": "SINGLE_PRESS",
                }
            ],
        },
        response={
            "devices": [
                {
                    "id": "<wireless_panic_button_id>",
                    "alarmSystemId": "<alarm_system_id>",
                    "name": "<wireless_panic_button_name>",
                    "type": "WIRELESS_PANIC_BUTTON",
                    "partitionId": "<partition_id>",
                    "verkadaDeviceConfig": {"serialNumber": "<serial_number>"},
                }
            ]
        },
    ),
    "alarm.wireless_panic_button.list": Endpoint(
        method="POST",
        subdomain="vproconfig",
        path="alarm_system/get_devices",
        payload={
            "alarmSystemId": "<alarm_system_id>",
        },
        response={
            "devices": [
                {
                    "id": "<wireless_panic_button_id>",
                    "alarmSystemId": "<alarm_system_id>",
                    "name": "<wireless_panic_button_name>",
                    "type": "WIRELESS_PANIC_BUTTON",
                    "partitionId": "<partition_id>",
                    "verkadaDeviceConfig": {"serialNumber": "<serial_number>"},
                },
            ]
        },
    ),
    "alarm.wireless_panic_button.delete": Endpoint(
        method="POST",
        subdomain="vproconfig",
        path="device/decommission",
        payload={"deviceId": "<wireless_panic_button_id>"},
        response={"error": ""},
    ),
    "alarm.wireless_universal_transmitter.create": Endpoint(
        method="POST",
        subdomain="vproconfig",
        path="unassigned_device/bulk_set_up_universal_transmitter",
        payload={
            "alarmSystemId": "<alarm_system_id>",
            "devices": [
                {
                    "deviceId": "<wireless_universal_transmitter_id>",
                    "alarmSystemId": "<alarm_system_id>",
                    "serialNumber": "<serial_number>",
                    "name": "<wireless_universal_transmitter_name>",
                    "partitionId": "<partition_id>",
                }
            ],
        },
        response={
            "devices": [
                {
                    "id": "<wireless_universal_transmitter_id>",
                    "alarmSystemId": "<alarm_system_id>",
                    "type": "UNIVERSAL_TRANSMITTER",
                    "verkadaDeviceConfig": {"serialNumber": "<serial_number>"},
                }
            ]
        },
    ),
    "alarm.wireless_universal_transmitter.list": Endpoint(
        method="POST",
        subdomain="vproconfig",
        path="alarm_system/get_devices",
        payload={
            "alarmSystemId": "<alarm_system_id>",
        },
        response={
            "devices": [
                {
                    "id": "<wireless_universal_transmitter_id>",
                    "alarmSystemId": "<alarm_system_id>",
                    "name": "<wireless_universal_transmitter_name>",
                    "type": "UNIVERSAL_TRANSMITTER",
                    "verkadaDeviceConfig": {"serialNumber": "<serial_number>"},
                },
            ]
        },
    ),
    "alarm.wireless_universal_transmitter.delete": Endpoint(
        method="POST",
        subdomain="vproconfig",
        path="device/decommission",
        payload={"deviceId": "<wireless_universal_transmitter_id>"},
        response={"error": ""},
    ),
    "alarm.wired_output.create": Endpoint(
        method="POST",
        subdomain="vproconfig",
        path="device/create_wired_output",
        payload={
            "device": {"name": "<wired_output_name>", "type": "WIRED_GENERIC_OUTPUT"},
            "alarmSystemId": "<alarm_system_id>",
            "hubId": "<alarm_panel_id>",
            "pinNum": 0,
        },
        response={
            "device": {
                "id": "<wired_output_id>",
                "alarmSystemId": "<alarm_system_id>",
                "name": "<wired_output_name>",
                "type": "WIRED_GENERIC_OUTPUT",
                "wiredOutputConfig": {"hubId": "<alarm_panel_id>", "pinNum": 0},
            }
        },
    ),
    "alarm.wired_output.list": Endpoint(
        method="POST",
        subdomain="vproconfig",
        path="alarm_system/get_devices",
        payload={
            "alarmSystemId": "<alarm_system_id>",
        },
        response={
            "devices": [
                {
                    "id": "<wired_output_id>",
                    "alarmSystemId": "<alarm_system_id>",
                    "name": "<wired_output_name>",
                    "type": "WIRED_GENERIC_OUTPUT",
                    "wiredOutputConfig": {"hubId": "<alarm_panel_id>", "pinNum": 0},
                },
            ]
        },
    ),
    "alarm.wired_output.delete": Endpoint(
        method="POST",
        subdomain="vproconfig",
        path="device/delete",
        payload={"deviceId": "<wired_output_id>"},
        response={
            "device": {
                "id": "<wired_output_id>",
                "alarmSystemId": "<alarm_system_id>",
                "name": "<wired_output_name>",
                "type": "WIRED_GENERIC_OUTPUT",
                "deleted": True,
                "wiredOutputConfig": {"hubId": "<alarm_panel_name>", "pinNum": 0},
            }
        },
    ),
    "alarm.wired_input.create": Endpoint(
        method="POST",
        subdomain="vproconfig",
        path="device/create_wired_input",
        payload={
            "device": {
                "name": "<wired_input_name>",
                "type": "WIRED_CONTACT_SENSOR",
                "sensorConfig": {
                    "wiredContactSensorConfig": {"type": "DOOR", "doorHeldOpenDelay": 0}
                },
            },
            "alarmSystemId": "<alarm_system_id>",
            "partitionId": "<partition_id>",
            "hubId": "<alarm_panel_id>",
            "pinNum": 0,
            "normalState": "CLOSED",
        },
        response={
            "device": {
                "id": "<wired_input_id>",
                "alarmSystemId": "<alarm_system_id>",
                "name": "<wired_input_name>",
                "type": "WIRED_CONTACT_SENSOR",
                "partitionId": "<partition_id>",
                "wiredInputConfig": {
                    "hubId": "<alarm_panel_id>",
                    "pinNum": 0,
                    "normalState": "CLOSED",
                },
            }
        },
    ),
    "alarm.wired_input.list": Endpoint(
        method="POST",
        subdomain="vproconfig",
        path="alarm_system/get_devices",
        payload={
            "alarmSystemId": "<alarm_system_id>",
        },
        response={
            "devices": [
                {
                    "id": "<wired_input_id>",
                    "alarmSystemId": "<alarm_system_id>",
                    "name": "<wired_input_name>",
                    "type": "WIRED_CONTACT_SENSOR",
                    "partitionId": "<partition_id>",
                    "wiredInputConfig": {
                        "hubId": "<alarm_panel_id>",
                        "pinNum": 0,
                        "normalState": "CLOSED",
                    },
                },
            ]
        },
    ),
    "alarm.wired_input.delete": Endpoint(
        method="POST",
        subdomain="vproconfig",
        path="device/delete",
        payload={"deviceId": "<wired_input_id>"},
        response={
            "device": {
                "id": "<wired_input_id>",
                "alarmSystemId": "<alarm_system_id>",
                "name": "<wired_input_name>",
                "type": "WIRED_CONTACT_SENSOR",
                "partitionId": "<partition_id>",
                "deleted": True,
                "wiredInputConfig": {
                    "hubId": "<alarm_panel_id>",
                    "pinNum": 0,
                    "normalState": "CLOSED",
                },
            }
        },
    ),
    # ── Observed in the Command web app (live recordings, 2026-10-27) ──
    # Not called by vCommander; registered so the calls are documented.
    "org.features.get": Endpoint(
        # Feature Manager state per feature (ENABLED / DISABLED, pending
        # removal); the web app reads it before camera setup.
        method="GET",
        subdomain="vcorgi",
        path="org/{org_id}/features",
        payload={},
        response={
            "aiSummarization": {
                "state": "ENABLED",
                "pendingRemoval": False,
                "lastUpdated": "<iso8601>",
                "updatedBy": "<email>",
            },
        },
    ),
    "access_controller.list.v4": Endpoint(
        method="GET",
        subdomain=API_GATEWAY_SUBDOMAIN,
        path="access/v4/user/access_controllers",
        payload={},
        response={"accessControllers": []},
    ),
    "door.list.v4": Endpoint(
        method="GET",
        subdomain=API_GATEWAY_SUBDOMAIN,
        path="access/v4/user/doors",
        payload={},
        response={"doors": []},
    ),
    "door.set_nearby_cameras": Endpoint(
        # After creating a door the web app attaches nearby cameras
        # (position "doorway" / "interior" / "exterior").
        method="POST",
        subdomain=API_GATEWAY_SUBDOMAIN,
        path="door/set_nearby_cameras",
        payload={
            "doorId": "<door_id>",
            "cameras": [{"cameraId": "<camera_id>", "position": "doorway", "offset": 1}],
        },
        response={"doors": [{"doorId": "<door_id>"}]},
    ),
    "access.roles.modify": Endpoint(
        # Access site roles. The web app grants the user Access Site Admin on
        # a site when it sets up an access controller there; on a site Access
        # doesn't know yet it fails 400 "Unknown entity" and the setup stops.
        method="POST",
        subdomain="vcerberus",
        path="access/v2/user/roles/modify",
        payload={
            "grants": [
                {
                    "granteeId": "<user_id>",
                    "entityId": "<site_id>",
                    "roleKey": "ACCESS_CONTROL_SITE_ADMIN",
                    "role": "ACCESS_CONTROL_SITE_ADMIN",
                }
            ],
            "revokes": [],
        },
        response={},
    ),
    "camera.recommended_settings.apply": Endpoint(
        # The camera Set Up dialog's Apply: codec, analytics features and
        # wildcard settings in one call (vCommander uses camera.create.feature).
        method="POST",
        subdomain="vcorgi",
        path="device/recommended_default_settings/apply",
        payload={
            "organizationId": "<org_id>",
            "siteId": "<site_id>",
            "deviceType": "camera",
            "deviceIds": ["<camera_id>"],
            "configs": [{"name": "stream-configs.high.stream-encoding", "value": "HEVC"}],
            "features": [
                {"name": "people-history", "value": True},
                {"name": "person-attributes", "value": True},
                {"name": "face-detection", "value": True},
            ],
            "wildcard": [{"name": "low-bandwidth-mode", "value": False}],
        },
        response={"configs": [], "features": [], "wildcard": []},
    ),
    "camera.rotate": Endpoint(
        # Sent before LPR mode is turned on (LPR needs normal orientation).
        method="POST",
        subdomain="vprovision",
        path="camera/rotate",
        payload={"cameraId": "<camera_id>", "rotate": "0"},
        response={"cameraConfigParams": [{"paramName": "camera-config.camera-rotate"}]},
    ),
    "camera.create.ptz_install.web": Endpoint(
        # The web app's PTZ Installation Mode switch (vCommander's
        # camera.create.ptz_install_disable uses vdeviceconfig with cameraIds).
        method="POST",
        subdomain="vprovision",
        path="user/camera/config/set",
        payload={
            "cameraId": "<camera_id>",
            "params": {"peripheral-motor-ctrl.disable-pan-tilt": False},
        },
        response={},
    ),
    "alarm.keycode.generate": Endpoint(
        # A random unused code, used to pre-fill the Add Keycode dialog.
        method="POST",
        subdomain="vproconfig",
        path="keycode/generate",
        payload={"alarmSystemId": "<alarm_system_id>"},
        response={"code": "<6 digits>"},
    ),
    # ── Persons of interest (videntity), as Cameras → People uses them ──
    "poi.list": Endpoint(
        method="POST",
        subdomain="videntity",
        path="identity/list",
        payload={
            "organizationId": "<org_id>",
            "filter": {"isHidden": False},
            "sort": {"field": "created", "sortDirection": "desc"},
            "skipAuditLogAdd": True,
            "paging": {"limit": 5000},
        },
        response={
            "identities": [
                {
                    "personId": "<person_id>",
                    "name": "<label>",
                    "accessId": None,
                    "guestId": None,
                    "identityListIds": ["<list_id>"],
                }
            ],
            "paging": {"nextToken": None, "totalItems": 1},
        },
    ),
    "poi.delete": Endpoint(
        # Several people per call (People → person → Remove this person).
        method="POST",
        subdomain="videntity",
        path="identity/delete",
        payload={"organizationId": "<org_id>", "personIds": ["<person_id>"]},
        response={},
    ),
    "poi.lists": Endpoint(
        method="POST",
        subdomain="videntity",
        path="identity_list/bulk",
        payload={"organizationId": "<org_id>"},
        response={"lists": [{"listId": "<list_id>", "name": "People of Interest"}]},
    ),
}
