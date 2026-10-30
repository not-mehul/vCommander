import re
from typing import Any

from requests.exceptions import JSONDecodeError, RequestException

from apis.http import build_session
from utils.logger import log_api_call

# The public API lives at https://<region>.verkada.com, where region is the
# label for the org's shard ("api", "api.oh", "api.eu", "api.au"; see
# OrgShard.public_api_region). Only well-formed host labels are accepted.
_REGION = re.compile(r"^api(\.[a-z0-9]([a-z0-9-]*[a-z0-9])?)*$")

# Public-API list endpoints page with `page_size` + `page_token`, returning
# `next_page_token` until the last page. The cap only guards against a
# server that keeps handing back a token forever.
_MAX_PAGES = 500


class VerkadaExternalAPIClient:
    """
    Client for the public Verkada API (https://apidocs.verkada.com/).

    Used by the Users tool only, to read the source org's sites and guest
    visits with the API key the user enters. The key is exchanged for a
    short-lived token for authenticated requests.
    """

    def __init__(self, api_key: str, org_short_name: str, region: str = "api"):
        region = region or "api"
        if not _REGION.match(region):
            raise ValueError(f"Invalid public API region: {region!r}")
        self.api_key = api_key
        self.org_short_name = org_short_name
        self.region = region

        # Session carries retry + a default timeout (see apis/http.py); the
        # missing timeout previously let a stalled token/scan call hang forever.
        self.session = build_session()

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
        host = f"{self.region}.verkada.com"
        headers = {"accept": "application/json", "x-api-key": self.api_key}

        def fail(status: str, reason: str) -> ConnectionError:
            # Failures are logged too: without this line a rejected key left
            # no trace between the key's creation and its cleanup.
            log_api_call("POST", f"{host}/token", '{"x-api-key": "***"}', status, reason)
            return ConnectionError(f"Failed to generate API token at {host}: {reason}")

        try:
            response = self.session.post(f"https://{host}/token", headers=headers)
        except RequestException as e:
            raise fail("error", str(e)) from e
        try:
            data = response.json()
        except JSONDecodeError:
            data = None
        status = str(response.status_code)
        if not isinstance(data, dict):
            raise fail(status, response.text[:200] or "non-JSON response.")

        if not response.ok:
            raise fail(status, str(data.get("message") or response.text[:200]))

        token = data.get("token")
        if not token:
            raise fail(status, "response missing 'token' key.")

        log_api_call("POST", f"{host}/token", '{"x-api-key": "***"}', status, '{"token": "***"}')
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
        _allow_refresh: bool = True,
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
                e.g. "Failed to fetch guest sites". The server's error
                message (or response text) is appended after a colon.

        Returns:
            Parsed JSON body, or `{}` for an empty response.
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
            raise ConnectionError(f"{error_context}: {e}") from e

        # The API token is short-lived and generated once when this client is
        # created. On a long scan/delete it can expire mid-run, surfacing as a
        # 401 "failed to authenticate". Regenerate the token once and retry.
        if response.status_code in (401, 403) and _allow_refresh:
            self.api_token = self._generate_api_token()
            return self._request(
                method,
                url,
                json=json,
                params=params,
                error_context=error_context,
                _allow_refresh=False,
            )

        if response.content:
            try:
                data = response.json()
            except JSONDecodeError:
                if not response.ok:
                    raise ConnectionError(
                        f"{error_context}: {response.text or 'non-JSON response.'}"
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
            log_api_call(
                method,
                url.removeprefix("https://"),
                "-",
                str(response.status_code),
                str(msg or "unknown error")[:300],
            )
            raise ConnectionError(
                f"{error_context} (HTTP {response.status_code}): "
                f"{msg or 'unknown error'}"
            )

        data_dict.setdefault("__status_code__", response.status_code)
        return data_dict

    @staticmethod
    def _status(data: dict) -> str:
        """Pull the helper-stashed HTTP status code as a string for logging."""
        return str(data.get("__status_code__", ""))

    def _get_all(
        self,
        url: str,
        list_key: str,
        *,
        params: dict,
        error_context: str,
    ) -> tuple[list[dict[str, Any]], str]:
        """
        GET every page of a public-API list endpoint.

        Follows `next_page_token` (sent back as `page_token`) until the
        server stops returning one, so orgs larger than one page are listed
        in full. Endpoints that don't paginate simply return no token and
        end after the first request.

        Returns:
            (items, status) — the concatenated `list_key` arrays and the
            last response's HTTP status (for logging).
        """
        items: list[dict[str, Any]] = []
        seen_tokens: set[str] = set()
        page_params = dict(params)
        data: dict = {}
        for _ in range(_MAX_PAGES):
            data = self._request(
                "GET",
                url,
                params=page_params,
                error_context=error_context,
            )
            items.extend(data.get(list_key) or [])
            token = data.get("next_page_token")
            if not token or token in seen_tokens:
                break
            seen_tokens.add(token)
            page_params = {**params, "page_token": token}
        return items, self._status(data)

    # ------------------------------------------------------------------
    # Getters (Users tool)
    # ------------------------------------------------------------------

    def get_sites(self) -> list[dict[str, Any]]:
        """The source org's guest sites as {site_id, name}, every page."""
        path = "guest/v1/sites"
        items, status = self._get_all(
            f"https://{self.region}.verkada.com/{path}",
            "guest_sites",
            params={"page_size": 200},
            error_context="Failed to fetch guest sites",
        )
        results = [{"site_id": x["site_id"], "name": x["site_name"]} for x in items]
        log_api_call(
            "GET",
            f"{self.region}.verkada.com/{path}",
            "{}",
            status,
            f'{{"count": {len(results)}}}',
        )
        return results

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
            image_url = guest.get("image_url")
            if " " in full_name:
                first, last = full_name.rsplit(" ", 1)
            else:
                first = last = full_name
            return {"first_name": first, "last_name": last, "email": email, "image_url": image_url}

        visits, status = self._get_all(
            url,
            "visits",
            params={
                "site_id": site_id,
                "start_time": start_time,
                "end_time": end_time,
                "page_size": 100,
            },
            error_context=f"Failed to fetch guest visits for site {site_id}",
        )

        results = [_split_name(item) for item in visits]
        log_api_call(
            "GET",
            f"{self.region}.verkada.com/guest/v1/visits",
            f'{{"site_id": "{site_id}", "start_time": {start_time}, "end_time": {end_time}}}',
            status,
            f'{{"count": {len(results)}}}',
        )
        return results
