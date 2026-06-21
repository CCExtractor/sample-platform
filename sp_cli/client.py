"""HTTP client for the CCExtractor CI System API (`/api/v1`)."""

from typing import Any, Dict, List, Optional

import requests  # type: ignore[import-untyped]


class ApiError(Exception):
    """Raised when an API request fails, carrying the structured error envelope."""

    def __init__(self, code: str, message: str, status: Optional[int] = None,
                 details: Optional[Dict[str, Any]] = None) -> None:
        """
        Build an API error.

        :param code: Stable machine-readable error code (e.g. ``not_found``).
        :type code: str
        :param message: Human-readable explanation.
        :type message: str
        :param status: HTTP status code, if the failure was an HTTP response.
        :type status: Optional[int]
        :param details: Optional structured context echoed from the API.
        :type details: Optional[Dict[str, Any]]
        """
        super().__init__(message)
        self.code = code
        self.message = message
        self.status = status
        self.details = details

    @property
    def exit_code(self) -> int:
        """
        Map the error to a process exit code so callers can branch on it.

        :return: 3 connection · 4 not-found · 5 validation · 6 auth · 7 rate-limited · 1 other.
        :rtype: int
        """
        if self.code == 'connection_error':
            return 3
        if self.status == 404:
            return 4
        if self.status in (400, 422):
            return 5
        if self.status in (401, 403):
            return 6
        if self.status == 429:
            return 7
        return 1


class ApiClient:
    """Minimal client over the JSON API. Sends a bearer token when configured."""

    def __init__(self, base_url: str, token: Optional[str] = None, timeout: int = 30) -> None:
        """
        Configure the client.

        :param base_url: Root URL of the platform (without the ``/api/v1`` prefix).
        :type base_url: str
        :param token: Optional opaque bearer token sent on every request.
        :type token: Optional[str]
        :param timeout: Per-request timeout in seconds.
        :type timeout: int
        """
        self.base_url = base_url.rstrip('/')
        self.token = token
        self.timeout = timeout
        self.session = requests.Session()

    def _headers(self) -> Dict[str, str]:
        """
        Build request headers, including the bearer token when set.

        :return: Header mapping.
        :rtype: Dict[str, str]
        """
        headers = {'Accept': 'application/json'}
        if self.token:
            headers['Authorization'] = f'Bearer {self.token}'
        return headers

    def request(self, method: str, path: str, params: Optional[Dict[str, Any]] = None,
                json_body: Optional[Dict[str, Any]] = None) -> Any:
        """
        Perform a request against an API path and return the decoded JSON body.

        :param method: HTTP method (``GET``, ``POST``, ``DELETE`` …).
        :type method: str
        :param path: API path below ``/api/v1`` (e.g. ``/runs``).
        :type path: str
        :param params: Optional query-string parameters.
        :type params: Optional[Dict[str, Any]]
        :param json_body: Optional JSON request body.
        :type json_body: Optional[Dict[str, Any]]
        :raises ApiError: on connection failure, a non-JSON body, or an HTTP error.
        :return: The decoded JSON response body (or ``None`` for ``204``).
        :rtype: Any
        """
        url = f"{self.base_url}{path}"
        try:
            response = self.session.request(method, url, params=params, json=json_body,
                                            headers=self._headers(), timeout=self.timeout)
        except requests.RequestException as exc:
            raise ApiError('connection_error', f'Could not reach {url}: {exc}')

        if response.status_code == 204:
            return None

        try:
            payload = response.json()
        except ValueError:
            raise ApiError('invalid_response',
                           f'Expected JSON but got HTTP {response.status_code}', response.status_code)

        if response.status_code >= 400:
            error = payload if isinstance(payload, dict) else {}
            raise ApiError(
                error.get('code', 'http_error'),
                error.get('message', f'Request failed with HTTP {response.status_code}'),
                response.status_code,
                error.get('details'),
            )

        return payload

    def get(self, path: str, params: Optional[Dict[str, Any]] = None) -> Any:
        """
        Perform a GET and return the decoded body.

        :param path: API path below ``/api/v1``.
        :type path: str
        :param params: Optional query-string parameters.
        :type params: Optional[Dict[str, Any]]
        :return: The decoded JSON body.
        :rtype: Any
        """
        return self.request('GET', path, params=params)

    def get_paginated(self, path: str, params: Optional[Dict[str, Any]] = None,
                      max_items: int = 1000) -> List[Any]:
        """
        Follow offset pagination and return the combined ``data`` list.

        :param path: API path below ``/api/v1``.
        :type path: str
        :param params: Optional query-string parameters (``limit``/``offset`` are managed).
        :type params: Optional[Dict[str, Any]]
        :param max_items: Safety cap on total items collected.
        :type max_items: int
        :return: All items across pages.
        :rtype: List[Any]
        """
        merged = dict(params or {})
        merged.setdefault('limit', 100)
        offset = 0
        items: List[Any] = []
        while True:
            merged['offset'] = offset
            payload = self.get(path, params=merged)
            data = payload.get('data', []) if isinstance(payload, dict) else []
            items.extend(data)
            pagination = payload.get('pagination', {}) if isinstance(payload, dict) else {}
            next_offset = pagination.get('next_offset')
            if not data or next_offset is None or len(items) >= max_items:
                break
            offset = next_offset
        return items
