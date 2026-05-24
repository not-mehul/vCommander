"""
Registry of Verkada internal (Command) API endpoints used by this app.

Each entry is fully self-describing: HTTP method, host subdomain, path
template, an example payload, an example response, and the date the
endpoint was last confirmed working against Command. When something
breaks after a Verkada release, the registry tells you exactly what
shape used to work, where to send the call, and (via last_verified) how
stale our assumption is.

URL shape:
    https://{subdomain}.command.verkada.com/__v/{org_short_name}/{path}

`path` is a `str.format` template — `{org_id}`, `{device_id}`, etc. get
filled at request time via `path_params=` to `_request()`.

`payload` and `response` are example dicts (not strict schemas). Scalar
values are placeholder strings like "<org_id>" or actual literals when
the wire format requires a specific value (e.g. `"loginMethod":
"password"`). Lists hold one representative element. For empty bodies
use `{}`.

When you update an endpoint after a Verkada change, also update its
payload/response examples and bump `last_verified`.
"""

from typing import NamedTuple


class Endpoint(NamedTuple):
    method: str  # 'GET', 'POST', 'DELETE'
    subdomain: str  # e.g. 'vprovision', 'vcerberus', 'api'
    path: str  # str.format template; {org_id}, {device_id}, ...
    payload: dict  # example request body (placeholder values)
    response: dict  # example response body (placeholder values)
    last_verified: str  # YYYY-MM-DD — bump when re-confirmed
    notes: str = ""  # optional human note (quirks, error codes, etc.)


ENDPOINTS: dict[str, Endpoint] = {
    # ── Auth ──────────────────────────────────────────────────────────
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
            # On verify_mfa, an additional field is sent:
            # "otp": "<otp_code>",
        },
        response={
            "loggedIn": True,
            "csrfToken": "<csrf>",
            "userToken": "<user_token>",
            "organizationId": "<org_id>",
            "userId": "<user_id>",
            # MFA path: {"message": "2FA invalid for <user>",
            #            "data": {"smsSent": "<last4>"}}
        },
        last_verified="2026-05-23",
        notes="Pre-auth. Same URL for initial login and MFA verify.",
    ),
    # ── Org / users / settings ────────────────────────────────────────
    "site.create": Endpoint(
        method="POST",
        subdomain="vprovision",
        path="org/camera_group/create",
        payload={"organizationId": "<org_id>", "name": "<site_name>"},
        response={"cameraGroups": [{"cameraGroupId": "<site_id>"}]},
        last_verified="2026-05-23",
    ),
    "user.invite": Endpoint(
        method="POST",
        subdomain="vprovision",
        path="org/invite",
        payload={
            "organizationId": "<org_id>",
            "email": "<email>",
            "orgAdmin": True,
            "commandUserAdmin": False,
            "firstName": "<first>",
            "lastName": "<last>",
            "inviteFf": True,
        },
        response={
            "orgInvitation": [{"orgInvitationId": "<inv_id>"}],
            "users": [
                {"userId": "<user_id>", "email": "<email>", "name": "<full_name>"}
            ],
        },
        last_verified="2026-05-23",
        notes="Returns id=cannot_invite_existing on 4xx if user already in org.",
    ),
    "apikey.create": Endpoint(
        method="POST",
        subdomain="apiadmin",
        path="admin/orgs/{org_id}/v2/granular_apikeys",
        payload={
            "api_key_name": "<key_name>",
            "expires_at": 0,  # unix seconds
            "roles": ["PUBLIC_API_CAMERA_READ_WRITE", "<...>"],
        },
        response={"apiKey": "<api_key>"},
        last_verified="2026-05-23",
        notes="Returns 400 'Would exceed 10 api keys limit' when capped.",
    ),
    "access.roles.modify": Endpoint(
        method="POST",
        subdomain="vcerberus",
        path="access/v2/user/roles/modify",
        payload={
            "grants": [
                {
                    "entityId": "<org_id>",
                    "granteeId": "<user_id>",
                    "roleKey": "ACCESS_CONTROL_SYSTEM_ADMIN",
                    "role": "ACCESS_CONTROL_SYSTEM_ADMIN",
                },
            ],
        },
        response={},
        last_verified="2026-05-23",
    ),
    "org.settings.update": Endpoint(
        method="POST",
        subdomain="vprovision",
        path="org/settings/update",
        payload={
            "organizationId": "<org_id>",
            "settings": {"globalSiteAdmin": True},
        },
        response={},
        last_verified="2026-05-23",
    ),
    "org.sign_agreement": Endpoint(
        method="POST",
        subdomain="vcorgi",
        path="{org_id}/sign_agreement",
        payload={"agreementKey": "<CV_ANALYTICS|LPR>", "userEmail": "<email>"},
        response={},
        last_verified="2026-05-23",
    ),
    "org.feature.set": Endpoint(
        method="POST",
        subdomain="vdeviceconfig",
        path="user/org/feature/set",
        payload={
            "organizationId": "<org_id>",
            "params": {"<feature_flag>": True},
            "annotations": {"timestamp": 0, "userId": "<user_id>"},
        },
        response={},
        last_verified="2026-05-23",
    ),
    "org.custom_roles.enable": Endpoint(
        method="POST",
        subdomain="vauth",
        path="org/{org_id}/custom_roles/enable",
        payload={},
        response={},
        last_verified="2026-05-23",
    ),
    # ── Camera features / config ──────────────────────────────────────
    "camera.feature.set": Endpoint(
        method="POST",
        subdomain="vdeviceconfig",
        path="user/camera/feature/set",
        payload={
            "cameraIds": ["<camera_id>"],
            "params": {"<feature_flag>": True},
        },
        response={},
        last_verified="2026-05-23",
    ),
    "camera.config.set": Endpoint(
        method="POST",
        subdomain="vprovision",
        path="user/camera/config/set",
        payload={
            "cameraId": "<camera_id>",
            "params": {"camera-config.operating-mode": "lpr"},
        },
        response={},
        last_verified="2026-05-23",
        notes="Singular cameraId only — one camera per call.",
    ),
    "camera.name.set": Endpoint(
        method="POST",
        subdomain="vprovision",
        path="camera/name/set",
        payload={"cameraId": "<camera_id>", "name": "<name>"},
        response={},
        last_verified="2026-05-23",
    ),
    "camera.site.batch.set": Endpoint(
        method="POST",
        subdomain="vprovision",
        path="camera/site/batch/set",
        payload={
            "cameraIds": ["<camera_id>"],
            "destinationSiteId": "<site_id>",
        },
        response={},
        last_verified="2026-05-23",
    ),
    "camera.location.set": Endpoint(
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
        response={},
        last_verified="2026-05-23",
    ),
    # ── Doors / access control ────────────────────────────────────────
    "door.config.set": Endpoint(
        method="POST",
        subdomain="api",
        path="door/config/set",
        payload={
            "doorId": "<door_id>",
            "action": "grant",
            "paramName": "<param>",
            "paramValue": "<value>",
        },
        response={},
        last_verified="2026-05-23",
    ),
    "door.device_io": Endpoint(
        method="POST",
        subdomain="api",
        path="door/{door_id}/device_io",
        payload={
            "configs": {"lprCameraId": "<camera_id>"},
            "ioDeviceTypeName": "lpr-camera",
            "ioSlotType": "lpr-camera",
            "ioSlotIndex": 0,
        },
        response={},
        last_verified="2026-05-23",
    ),
    "door.create": Endpoint(
        method="POST",
        subdomain="api",
        path="door/create",
        payload={
            "accessControllerId": "<controller_id>",
            "configs": [{"paramName": "<param>", "paramValue": "<value>"}],
            "deviceIos": [
                {
                    "configs": {},
                    "ioDeviceTypeName": "lock",
                    "ioSlotIndex": 0,
                    "ioSlotType": "lock",
                }
            ],
            "doorType": "standard",
            "floorId": "<floor_id>",
            "name": "<door_name>",
        },
        response={"doors": [{"doorId": "<door_id>"}]},
        last_verified="2026-05-23",
    ),
    "controller.setup": Endpoint(
        method="POST",
        subdomain="vcerberus",
        path="access/v2/user/access_device/setup",
        payload={
            "configs": {"acu-mode": "normal"},
            "deviceId": "<device_id>",
            "floorId": "<floor_id>",
            "name": "<name>",
            "siteId": "<site_id>",
            "timezone": "<timezone>",
        },
        response={"accessControllerId": "<controller_id>"},
        last_verified="2026-05-23",
    ),
    "access.schedules.create": Endpoint(
        method="POST",
        subdomain="vcerberus",
        path="access/v2/user/schedules",
        payload={
            "defaultDoorLockState": "ACCESS_CONTROL",
            "defaultDoorPermissionState": "DENY",
            "deleted": False,
            "doors": ["<door_id>"],
            "endDateTime": None,
            "events": [
                {
                    "date": None,
                    "doorPermissionState": "ALLOW",
                    "endTime": "23:59:59.999",
                    "startTime": "00:00:00.000",
                    "weekday": 1,
                }
            ],
            "name": "<name>",
            "priority": "SCHEDULE",
            "sites": ["<site_id>"],
            "startDateTime": None,
            "type": "USER",
            "userGroups": ["<group_id>"],
        },
        response={},
        last_verified="2026-05-23",
        notes="Time format HH:MM:SS.mmm (period before ms, not colon).",
    ),
    # ── Buildings ─────────────────────────────────────────────────────
    "building.create": Endpoint(
        method="POST",
        subdomain="vprovision",
        path="building/create",
        payload={
            "name": "<name>",
            "organizationId": "<org_id>",
            "address": "<label>",
            "latitude": 0.0,
            "longitude": 0.0,
            "floors": [{"name": "<floor>", "...": "..."}],
        },
        response={"floors": [{"floorId": "<floor_id>"}]},
        last_verified="2026-05-23",
    ),
    # ── Alarm response sites / systems ────────────────────────────────
    "alarm.response_site.create": Endpoint(
        method="POST",
        subdomain="vagent",
        path="response/site/create",
        payload={
            "adminContactUserId": "<user_id>",
            "businessName": "<name>",
            "dispatchEnabled": True,
            "locationRequest": {
                "apt": "",
                "city": "<city>",
                "country": "<country>",
                "latitude": 0.0,
                "longitude": 0.0,
                "state": "<state>",
                "street1": "<street>",
                "street2": "",
                "timezone": "<tz>",
                "zipcode": "<zip>",
            },
            "permitNumber": "",
            "siteId": "<site_id>",
        },
        response={"responseSite": {"id": "<response_site_id>"}},
        last_verified="2026-05-23",
    ),
    "alarm.software_trial.create": Endpoint(
        method="POST",
        subdomain="vagent",
        path="site/software_trial/create",
        payload={"siteId": "<site_id>"},
        response={},
        last_verified="2026-05-23",
    ),
    "alarm.system.create": Endpoint(
        method="POST",
        subdomain="vproconfig",
        path="alarm_system/create",
        payload={"orgId": "<org_id>", "siteId": "<site_id>"},
        response={"alarmSystem": {"id": "<alarm_system_id>"}},
        last_verified="2026-05-23",
    ),
    "alarm.panel.setup": Endpoint(
        method="POST",
        subdomain="vproconfig",
        path="unassigned_device/setup_colossus",
        payload={
            "alarmSystemId": "<alarm_system_id>",
            "deviceId": "<device_id>",
            "name": "<name>",
            "replaceExistingLeader": False,
        },
        response={},
        last_verified="2026-05-23",
    ),
    "alarm.keypad.setup": Endpoint(
        method="POST",
        subdomain="vproconfig",
        path="unassigned_device/set_up_alarm_device",
        payload={
            "alarmSystemId": "<alarm_system_id>",
            "deviceId": "<device_id>",
            "name": "<name>",
            "serialNumber": "<serial>",
        },
        response={},
        last_verified="2026-05-23",
    ),
    # ── Guest / mailroom / connectors ─────────────────────────────────
    "guest.site.create": Endpoint(
        method="POST",
        subdomain="vdoorman",
        path="site/org/{org_id}",
        payload={
            "siteId": "<site_id>",
            "fullAddress": "<full_address>",
            "latitude": 0.0,
            "longitude": 0.0,
            "countryCode": "<cc>",
        },
        response={"siteId": "<guest_site_id>"},
        last_verified="2026-05-23",
    ),
    "guest.trial.create": Endpoint(
        method="POST",
        subdomain="vdoorman",
        path="guest/trial/org/{org_id}/site/{site_id}",
        payload={"productType": "GUEST"},
        response={},
        last_verified="2026-05-23",
    ),
    "connector.update_box": Endpoint(
        method="POST",
        subdomain="vprovision",
        path="vfortress/update_box",
        payload={
            "deviceId": "<device_id>",
            "locationLabel": "<label>",
            "locationLat": 0.0,
            "locationLon": 0.0,
            "name": "<name>",
            "siteId": "<site_id>",
        },
        response={"deviceId": "<device_id>"},
        last_verified="2026-05-23",
    ),
    # ── Device lifecycle (commission) ─────────────────────────────────
    "device.commission": Endpoint(
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
        last_verified="2026-05-23",
        notes="Same endpoint commissions any device type by serial.",
    ),
    # ── List endpoints ────────────────────────────────────────────────
    "intercoms.list": Endpoint(
        method="GET",
        subdomain="api",
        path="vinter/v1/user/organization/{org_id}/device",
        payload={},
        response={
            "intercoms": [
                {"deviceId": "<id>", "name": "<name>", "serialNumber": "<serial>"},
            ]
        },
        last_verified="2026-05-23",
    ),
    "access_controllers.list": Endpoint(
        method="GET",
        subdomain="vcerberus",
        path="access/v2/user/access_controllers",
        payload={},
        response={
            "accessControllers": [
                {
                    "accessControllerId": "<id>",
                    "name": "<name>",
                    "serialNumber": "<serial>",
                },
            ]
        },
        last_verified="2026-05-23",
    ),
    "sensors.list": Endpoint(
        method="POST",
        subdomain="vsensor",
        path="devices/list",
        payload={"organizationId": "<org_id>"},
        response={
            "sensorDevice": [
                {
                    "deviceId": "<id>",
                    "name": "<name>",
                    "claimedSerialNumber": "<serial>",
                },
            ]
        },
        last_verified="2026-05-23",
    ),
    "mailroom_sites.list": Endpoint(
        method="GET",
        subdomain="vdoorman",
        path="package_site/org/{org_id}",
        payload={},
        response={"package_sites": [{"siteId": "<id>", "siteName": "<name>"}]},
        last_verified="2026-05-23",
    ),
    "desk_stations.list": Endpoint(
        method="GET",
        subdomain="api",
        path="vinter/v1/user/organization/{org_id}/device",
        payload={},
        response={
            "deskApps": [
                {"deviceId": "<id>", "name": "<name>", "serialNumber": "<serial>"},
            ]
        },
        last_verified="2026-05-23",
        notes="Same URL as intercoms.list; response key differs (deskApps).",
    ),
    "connectors.list": Endpoint(
        method="POST",
        subdomain="vprovision",
        path="vfortress/list_boxes",
        payload={"organizationId": "<org_id>"},
        response={
            "items": [
                {
                    "deviceId": "<id>",
                    "name": "<name>",
                    "claimedSerialNumber": "<serial>",
                },
            ]
        },
        last_verified="2026-05-23",
    ),
    "alarm_sites.list": Endpoint(
        method="POST",
        subdomain="vagent",
        path="response/site/list",
        payload={"includeResponseConfigs": True},
        response={
            "responseSites": [
                {
                    "id": "<response_site_id>",
                    "siteId": "<site_id>",
                    "alarmSystemId": "<alarm_system_id>",
                    "businessName": "<name>",
                }
            ]
        },
        last_verified="2026-05-23",
    ),
    "alarm_devices.list": Endpoint(
        method="POST",
        subdomain="vproconfig",
        path="org/get_devices_and_alarm_systems",
        payload={"organizationId": "<org_id>"},
        response={
            "devices": [
                {
                    "id": "<id>",
                    "name": "<name>",
                    "verkadaDeviceConfig": {"serialNumber": "<serial>"},
                }
            ]
        },
        last_verified="2026-05-23",
    ),
    "unassigned_devices.list": Endpoint(
        method="GET",
        subdomain="vconductor",
        path="org/{org_id}/unassigned_devices",
        payload={},
        response={
            "devices": [
                {"deviceId": "<id>", "name": "<name>", "serialNumber": "<serial>"},
            ]
        },
        last_verified="2026-05-23",
    ),
    # ── Delete endpoints ──────────────────────────────────────────────
    "intercoms.delete": Endpoint(
        method="DELETE",
        subdomain="api",
        path="vinter/v1/user/async/organization/{org_id}/device/{object_id}",
        payload={},
        response={},
        last_verified="2026-05-23",
    ),
    "access_controllers.delete": Endpoint(
        method="POST",
        subdomain="vcerberus",
        path="access_device/decommission",
        payload={"deviceId": "<id>", "sharding": True},
        response={},
        last_verified="2026-05-23",
    ),
    "sensors.delete": Endpoint(
        method="POST",
        subdomain="vsensor",
        path="devices/decommission",
        payload={"deviceId": "<id>", "sharding": True},
        response={},
        last_verified="2026-05-23",
    ),
    "mailroom_sites.delete": Endpoint(
        method="DELETE",
        subdomain="vdoorman",
        path="package_site/org/{org_id}?siteId={object_id}",
        payload={},
        response={},
        last_verified="2026-05-23",
    ),
    "desk_stations.delete": Endpoint(
        method="DELETE",
        subdomain="api",
        path="vinter/v1/user/async/organization/{org_id}/device/{object_id}",
        payload={"sharding": True},
        response={},
        last_verified="2026-05-23",
    ),
    "connectors.delete": Endpoint(
        method="POST",
        subdomain="vprovision",
        path="vfortress/decommission",
        payload={"deviceId": "<id>", "organizationId": "<org_id>"},
        response={},
        last_verified="2026-05-23",
    ),
    "alarm_systems.delete": Endpoint(
        method="POST",
        subdomain="vproconfig",
        path="alarm_system/delete",
        payload={"alarmSystemId": "<id>"},
        response={},
        last_verified="2026-05-23",
    ),
    "alarm_devices.delete": Endpoint(
        method="POST",
        subdomain="vproconfig",
        path="device/decommission",
        payload={"deviceId": "<id>"},
        response={},
        last_verified="2026-05-23",
    ),
    "alarm_sites.delete": Endpoint(
        method="POST",
        subdomain="vagent",
        path="response/site/delete",
        payload={
            "responseSiteId": "<response_site_id>",
            "siteId": "<site_id>",
        },
        response={},
        last_verified="2026-05-23",
    ),
    "guest_sites.delete": Endpoint(
        method="DELETE",
        subdomain="vdoorman",
        path="site/org/{org_id}?siteId={object_id}",
        payload={},
        response={},
        last_verified="2026-05-23",
    ),
    "cameras.delete": Endpoint(
        method="POST",
        subdomain="vprovision",
        path="camera/decommission",
        payload={"cameraId": "<id>"},
        response={},
        last_verified="2026-05-23",
    ),
}


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
