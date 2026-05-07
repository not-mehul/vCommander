from typing import Any

import requests
from requests.adapters import HTTPAdapter
from requests.exceptions import JSONDecodeError, RequestException
from urllib3.util.retry import Retry

from utils.logger import log_api_call

_VALID_REGIONS = frozenset({"api", "api.eu", "api.au"})


class VerkadaExternalAPIClient:
    """
    Client for the public Verkada API (https://apidocs.verkada.com/).

    Uses a granular API key (created via the internal client) to generate a
    short-lived token for authenticated requests.
    """

    def __init__(self, api_key: str, org_short_name: str, region: str = "api"):
        self.api_key = api_key
        self.org_short_name = org_short_name
        self.region = region or "api"
        if region not in _VALID_REGIONS:
            raise ValueError(
                f"Invalid region: {region!r}; expected one of {sorted(_VALID_REGIONS)}"
            )

        self.session = requests.Session()

        # Retry on transient failures with exponential backoff
        retries = Retry(
            total=4,
            backoff_factor=0.5,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods={"POST", "GET", "DELETE", "PUT"},
        )
        adapter = HTTPAdapter(max_retries=retries)
        self.session.mount("https://", adapter)
        self.session.mount("http://", adapter)

        self.api_token = self._generate_api_token()

    # ------------------------------------------------------------------
    # Auth
    # ------------------------------------------------------------------

    def _generate_api_token(self) -> str:
        """
        Exchanges the long-lived API key for a short-lived API token.

        Stays inline (rather than going through _request) because it runs
        before self.api_token exists and uses a different auth header
        (x-api-key) than every other endpoint on this client.

        Raises:
            ConnectionError: If token generation fails.
        """
        url = f"https://{self.region}.verkada.com/token"
        headers = {"accept": "application/json", "x-api-key": self.api_key}

        try:
            response = self.session.post(url, headers=headers)
            data = response.json()
        except JSONDecodeError:
            raise ConnectionError("Failed to generate API token: non-JSON response.")
        except RequestException as e:
            raise ConnectionError(f"Failed to generate API token: {e}")

        if not response.ok:
            msg = data.get("message", response.text)
            raise ConnectionError(f"Failed to generate API token: {msg}")

        token = data.get("token")
        if not token:
            raise ConnectionError(
                "Failed to generate API token: response missing 'token' key."
            )

        log_api_call(
            "POST",
            f"{self.region}.verkada.com/token",
            '{"x-api-key": "***"}',
            str(response.status_code),
            '{"token": "***"}',
        )
        return token

    def _auth_headers(self, *, with_content_type: bool = False) -> dict[str, str]:
        """Standard headers for authenticated public-API calls."""
        headers = {"accept": "application/json", "x-verkada-auth": self.api_token}
        if with_content_type:
            headers["content-type"] = "application/json"
        return headers

    def _request(
        self,
        method: str,
        url: str,
        *,
        json: dict | None = None,
        params: dict | None = None,
        error_context: str,
        empty_on_400_signature: str | None = None,
    ) -> dict:
        """
        Execute an authenticated public-API request and return parsed JSON.

        Centralizes the request, JSON-decode handling, empty-body tolerance,
        and error-message extraction that every method on this client needs.

        Args:
            method: HTTP verb ('GET', 'POST', 'PUT', 'DELETE').
            url: Full request URL.
            json: Optional JSON body. If provided, content-type is added.
            params: Optional query params.
            error_context: Prefix used in raised ConnectionError messages,
                e.g. "Failed to fetch cameras". The server's error message
                (or response text) is appended after a colon.
            empty_on_400_signature: If set, a 400 response containing this
                substring is treated as an empty result (returns `{}`)
                instead of raising. Used by endpoints that signal "no items
                exist" via 400 rather than 200 with an empty list.

        Returns:
            Parsed JSON body, or `{}` for empty responses or tolerated 400s.
            The HTTP status code is stashed under `__status_code__` so
            callers can include it in their log_api_call invocations.

        Raises:
            ConnectionError: On any HTTP, transport, or decode failure.
        """
        headers = self._auth_headers(with_content_type=json is not None)
        try:
            response = self.session.request(
                method, url, json=json, params=params, headers=headers
            )
        except RequestException as e:
            raise ConnectionError(f"{error_context}: {e}")

        # Tolerate the "400 = no items" signature some endpoints use.
        if (
            empty_on_400_signature is not None
            and response.status_code == 400
            and empty_on_400_signature in response.text
        ):
            return {"__status_code__": response.status_code}

        if response.content:
            try:
                data = response.json()
            except JSONDecodeError:
                if not response.ok:
                    raise ConnectionError(
                        f"{error_context}: {response.text or 'non-JSON response.'}"
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
            raise ConnectionError(f"{error_context}: {msg or 'unknown error'}")

        data_dict.setdefault("__status_code__", response.status_code)
        return data_dict

    @staticmethod
    def _status(data: dict) -> str:
        """Pull the helper-stashed HTTP status code as a string for logging."""
        return str(data.get("__status_code__", ""))

    # ------------------------------------------------------------------
    # Generic getter
    # ------------------------------------------------------------------

    def get_object(self, categories: str) -> list[dict[str, Any]]:
        """
        Fetches objects via the external (public) API.

        Args:
            categories: One of 'cameras', 'guest_sites', 'users'.

        Returns:
            List of dicts with standardized 'id' and 'name' keys.

        Raises:
            ValueError: If an unknown category is requested.
            ConnectionError: If the API call fails.
        """
        empty_on_400_signature: str | None = None

        match categories:
            case "cameras":
                object_type = "cameras"
                path = "cameras/v1/devices"
                # The cameras endpoint returns 400 (not 200 with []) when no
                # cameras exist on the org. Treat that case as empty.
                empty_on_400_signature = "must include cameras"

                def mapping_func(x: dict[str, Any]) -> dict[str, Any]:
                    return {
                        "id": x["camera_id"],
                        "name": x["name"],
                        "serial_number": x["serial"],
                    }

            case "guest_sites":
                object_type = "guest_sites"
                path = "guest/v1/sites"

                def mapping_func(x: dict[str, Any]) -> dict[str, Any]:
                    return {"id": x["site_id"], "name": x["site_name"]}

            case "users":
                object_type = "access_members"
                path = "access/v1/access_users"

                def mapping_func(x: dict[str, Any]) -> dict[str, Any]:
                    return {
                        "id": x["user_id"],
                        "name": x["full_name"],
                        "email": x["email"],
                    }

            case _:
                raise ValueError(f"Unknown external API category: {categories!r}")

        url = f"https://{self.region}.verkada.com/{path}"
        data = self._request(
            "GET",
            url,
            params={"page_size": 200},
            error_context=f"Failed to fetch {categories}",
            empty_on_400_signature=empty_on_400_signature,
        )

        results = [mapping_func(item) for item in data.get(object_type, [])]
        log_api_call(
            "GET",
            f"{self.region}.verkada.com/{path}",
            "{}",
            self._status(data),
            f'{{"count": {len(results)}}}',
        )
        return results

    # ------------------------------------------------------------------
    # Concrete getters
    # ------------------------------------------------------------------

    def get_guest_sites(self) -> list[dict[str, Any]]:
        """Returns guest sites as {id, name} for decommission scan."""
        return self.get_object("guest_sites")

    def get_sites(self) -> list[dict[str, Any]]:
        """Returns guest sites, remapped to {site_id, name} for compatibility."""
        items = self.get_object("guest_sites")
        return [{"site_id": item["id"], "name": item["name"]} for item in items]

    def get_cameras(self) -> list[dict[str, Any]]:
        return self.get_object("cameras")

    def get_access_users(self) -> list[dict[str, Any]]:
        return self.get_users()

    def get_users(
        self,
        exclude_user_id: str | None = None,
        exclude_email: str | None = None,
    ) -> list[dict[str, Any]]:
        """
        Returns all access users with optional filtering to avoid self-deletion.

        Args:
            exclude_user_id: User ID to exclude (e.g. the admin running the script).
            exclude_email: Email address to exclude.
        """
        users = self.get_object("users")

        if exclude_user_id is not None:
            clean_id = str(exclude_user_id).strip()
            users = [u for u in users if str(u.get("id", "")).strip() != clean_id]

        if exclude_email:
            clean_email = exclude_email.strip().lower()
            users = [
                u for u in users if u.get("email", "").strip().lower() != clean_email
            ]

        return users

    def get_guest_visits(
        self, site_id: str, start_time: int, end_time: int
    ) -> list[dict[str, Any]]:
        """
        Returns guest visits for a site within a time range (UNIX timestamps).

        Names are split into first/last on the rightmost space so that
        "Alpha Beta Gamma" → first="Alpha Beta", last="Gamma".
        """
        url = f"https://{self.region}.verkada.com/guest/v1/visits"

        def _split_name(x: dict[str, Any]) -> dict[str, Any]:
            guest = x.get("guest", {})
            full_name = guest.get("full_name", "")
            email = guest.get("email")
            if " " in full_name:
                first, last = full_name.rsplit(" ", 1)
            else:
                first = last = full_name
            return {"first_name": first, "last_name": last, "email": email}

        data = self._request(
            "GET",
            url,
            params={
                "site_id": site_id,
                "start_time": start_time,
                "end_time": end_time,
                "page_size": 100,
            },
            error_context=f"Failed to fetch guest visits for site {site_id}",
        )

        results = [_split_name(item) for item in data.get("visits", [])]
        log_api_call(
            "GET",
            f"{self.region}.verkada.com/guest/v1/visits",
            f'{{"site_id": "{site_id}", "start_time": {start_time}, "end_time": {end_time}}}',
            self._status(data),
            f'{{"count": {len(results)}}}',
        )
        return results

    # ------------------------------------------------------------------
    # Create methods
    # ------------------------------------------------------------------

    def create_access_group(self, group_name: str) -> str:
        """
        Creates a new access user group.

        Args:
            group_name: Display name for the access group.

        Returns:
            The new group's group_id.

        Raises:
            ConnectionError: If the API call fails or the response is missing
                a group_id.
        """
        url = "https://api.verkada.com/access/v1/access_groups/group"
        data = self._request(
            "POST",
            url,
            json={"name": group_name},
            error_context=f"create_access_group '{group_name}'",
        )

        group_id = data.get("group_id")
        if not group_id:
            raise ConnectionError(
                f"create_access_group '{group_name}': missing 'group_id' in response."
            )

        log_api_call(
            "POST",
            "api.verkada.com/access/v1/access_groups/group",
            f'{{"name": "{group_name}"}}',
            self._status(data),
            f'{{"group_id": "{group_id}"}}',
        )
        return group_id

    def add_user_to_access_group(self, user_id: str, group_id: str) -> str:
        """
        Adds an access user to an access group.

        Args:
            user_id: The access user to add.
            group_id: The target access group.

        Returns:
            The user_id of the successfully added user (echoed by the API).

        Raises:
            ConnectionError: If the API call fails or the response contains
                no successful_adds entry.
        """
        url = "https://api.verkada.com/access/v1/access_groups/group/user"
        data = self._request(
            "PUT",
            url,
            params={"group_id": group_id},
            json={"user_id": user_id},
            error_context=f"add_user_to_access_group user={user_id} group={group_id}",
        )

        adds = data.get("successful_adds") or []
        if not adds:
            raise ConnectionError(
                f"add_user_to_access_group user={user_id} group={group_id}: "
                f"no successful_adds in response."
            )

        log_api_call(
            "PUT",
            "api.verkada.com/access/v1/access_groups/group/user",
            f'{{"user_id": "{user_id}", "group_id": "{group_id}"}}',
            self._status(data),
            f'{{"successful_adds": ["{adds[0]}"]}}',
        )
        return adds[0]

    def add_license_plate_to_user(self, user_id: str, license_plate: str) -> str:
        """
        Attaches a license plate credential to an access user.

        Args:
            user_id: The access user to credential.
            license_plate: The license plate number.

        Returns:
            The license plate number echoed back by the API.

        Raises:
            ConnectionError: If the API call fails or the response is missing
                license_plate_number.
        """
        url = "https://api.verkada.com/access/v1/credentials/license_plate"
        data = self._request(
            "POST",
            url,
            params={"user_id": user_id},
            json={"active": True, "license_plate_number": license_plate},
            error_context=f"add_license_plate_to_user user={user_id}",
        )

        plate = data.get("license_plate_number")
        if not plate:
            raise ConnectionError(
                f"add_license_plate_to_user user={user_id}: "
                f"missing 'license_plate_number' in response."
            )

        log_api_call(
            "POST",
            "api.verkada.com/access/v1/credentials/license_plate",
            f'{{"user_id": "{user_id}", "license_plate_number": "{license_plate}"}}',
            self._status(data),
            f'{{"license_plate_number": "{plate}"}}',
        )
        return plate

    # ------------------------------------------------------------------
    # Delete methods
    # ------------------------------------------------------------------

    def delete_user(self, user_id: str) -> None:
        """
        Permanently removes a user from the organization.

        Raises:
            ConnectionError: If the deletion fails.
        """
        url = f"https://{self.region}.verkada.com/core/v1/user"
        data = self._request(
            "DELETE",
            url,
            params={"user_id": user_id},
            error_context=f"Failed to delete user {user_id}",
        )

        log_api_call(
            "DELETE",
            f"{self.region}.verkada.com/core/v1/user",
            f'{{"user_id": "{user_id}"}}',
            self._status(data),
            "{}",
        )

    def delete_access_user(self, user_id: str) -> None:
        return self.delete_user(user_id)
