from typing import NamedTuple


class Endpoint(NamedTuple):
    method: str  # 'GET', 'POST', 'DELETE'
    subdomain: str  # e.g. 'vprovision', 'vcerberus', 'api'
    path: str  # str.format template; {org_id}, {device_id}, ...
    payload: dict  # example request body (placeholder values)
    response: dict | list | None  # example response body (placeholder values)


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


api_region = "api"

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
    {"paramName": "polling-frequency-ms", "paramValue": "10000"},
    {"paramName": "c3po-in1-type", "paramValue": "NONE"},
    {"paramName": "c3po-in2-type", "paramValue": "NONE"},
    {"paramName": "replace-ios-with-security-relay", "paramValue": "False"},
]

_FACE_STATION_PRO_DOOR_CREATE_CONFIGS = [
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
    {"paramName": "replace-ios-with-security-relay", "paramValue": False},
    {"paramName": "face-unlock-enabled", "paramValue": "true"},
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
    {"paramName": "polling-frequency-ms", "paramValue": "10000"},
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


def build_url(endpoint: Endpoint, org_short_name: str, formatted_path: str) -> str:
    """Compose the full request URL from an endpoint and a pre-formatted path."""
    return (
        f"https://{endpoint.subdomain}.command.verkada.com/__v/"
        f"{org_short_name}/{formatted_path}"
    )


ENDPOINTS: dict[str, Endpoint] = {
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
        subdomain=api_region,
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
        subdomain=api_region,
        path="users/delete",
        payload={
            "organizationId": "<org_id>",
            "userIds": ["<user_id>"],
        },
        response={},
    ),
    "user.add_license_plate": Endpoint(
        method="POST",
        subdomain=api_region,
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
        subdomain=api_region,
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
        subdomain=api_region,
        path="vinter/v1/user/async/organization/{org_id}/device/{object_id}",
        payload={"sharding": True},
        response={},
    ),
    "desk_station.list": Endpoint(
        method="GET",
        subdomain=api_region,
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
        subdomain=api_region,
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
        subdomain=api_region,
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
    "face_station_pro.create": Endpoint(
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
            "deviceId": "<face_station_pro_id>",
            "name": "<face_station_pro_name>",
            "organizationId": "<org_id>",
            "serialNumber": "<serial_number>",
            "timezone": "<timezone>",
            "vconductorModelId": "MOODY",
        },
    ),
    "face_station_pro.set_door_controller": Endpoint(
        method="POST",
        subdomain=api_region,
        path="door/create",
        payload={
            "name": "<door_name>",
            "floorId": "<floor_id>",
            "accessControllerId": "<access_controller_id>",
            "deviceIos": _DOOR_CREATE_IOS,
            "configs": _FACE_STATION_PRO_DOOR_CREATE_CONFIGS,
            "doorType": "moody_as_acu",
        },
        response={
            "doors": [
                {
                    "accessControllerId": "<face_station_pro_id>",
                    "doorId": "<door_id>",
                    "floorId": "<floor_id>",
                    "name": "<door_name>",
                    "nearbyCameras": [
                        {
                            "cameraId": "<face_station_pro_id>",
                        }
                    ],
                }
            ]
        },
    ),
    "face_station_pro.list": Endpoint(
        method="GET",
        subdomain=api_region,
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
    "face_station_pro.delete": Endpoint(
        method="POST",
        subdomain="vcerberus",
        path="access_device/decommission",
        payload={"deviceId": "<face_station_pro_id>", "sharding": True},
        response={},
    ),
    "door.create": Endpoint(
        method="POST",
        subdomain=api_region,
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
        subdomain=api_region,
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
        subdomain=api_region,
        path="door/delete",
        payload={
            "doorId": "<door_id>",
        },
        response={},
    ),
    "door.pair_lpr_camera": Endpoint(
        method="POST",
        subdomain=api_region,
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
    "access_group.create": Endpoint(
        method="POST",
        subdomain=api_region,
        path="user_groups/add_group",
        payload={"organizationId": "<org_id>", "groupName": "<access_group_name>"},
        response={"groupId": "<access_group_id>"},
    ),
    "access_group.list": Endpoint(
        method="POST",
        subdomain=api_region,
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
        subdomain=api_region,
        path="user_groups/remove_group",
        payload={"groupId": "<access_group_id>", "organizationId": "<org_id>"},
        response={},
    ),
    "access_group.add_user": Endpoint(
        method="POST",
        subdomain=api_region,
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
        subdomain=api_region,
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
    "visitor_access.create": Endpoint(
        method="POST",
        subdomain=api_region,
        path="access/v2/user/visit_types",
        payload={
            "cardEnabled": False,
            "codeEnabled": False,
            "qrCodeEnabled": False,
            "lpEnabled": False,
            "liveLinkEnabled": False,
            "bleEnabled": False,
            "remoteUnlockEnabled": False,
            "faceUnlockEnabled": False,
            "rollCallEnabled": True,
            "sites": ["<site_id>"],
            "doors": [],
            "updatedSchedule": False,
            "rollCallSiteIds": ["<site_id>"],
            "maximumDurationSeconds": 10800,
            "schedules": [],
            "directoryId": None,
            "name": "<visitor_access_name>",
            "description": "<visitor_access_name>",
        },
        response={
            "name": "<visitor_access_name>",
            "organizationId": "<org_id>",
            "visitTypeId": "<visitor_access_id>",
        },
    ),
    "visitor_access.list": Endpoint(
        method="GET",
        subdomain=api_region,
        path="access/v2/user/visit_types",
        payload={},
        response={
            "visitTypes": [
                {
                    "name": "<visitor_access_name>",
                    "organizationId": "<org_id>",
                    "visitTypeId": "<visitor_access_id>",
                }
            ]
        },
    ),
    "visitor_access.delete": Endpoint(
        method="DELETE",
        subdomain=api_region,
        path="access/v2/user/visit_types/{visitor_access_id}",
        payload={},
        response={
            "visitTypes": [
                {
                    "name": "<visitor_access_name>",
                    "organizationId": "<org_id>",
                    "visitTypeId": "<visitor_access_id>",
                }
            ]
        },
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
    # "guest.list" - Handled by External API Call
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
        subdomain="vproconfig",
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
}
