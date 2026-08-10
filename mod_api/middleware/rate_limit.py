"""
Per-client fixed-window rate limiting for API endpoints.

Limits:
    POST /auth/tokens      5 req / 15 min (keyed by IP)
    POST/DELETE/PUT/PATCH  20 req / min   (keyed by token)
    GET                    120 req / min  (keyed by token)

Includes X-RateLimit-* headers on every response.

Note: This is a fixed-window implementation (counter resets when the
window expires). For true sliding-window behavior, consider migrating
to Redis with a sorted-set approach. State is per-process, so multiple
Gunicorn workers enforce limits independently.
"""

import threading
import time

from flask import current_app, g, request

from mod_api.middleware.error_handler import make_error_response

_rate_limit_store = {}  # key -> {'count': int, 'window_start': float}
_rate_limit_lock = threading.Lock()
_eviction_counter = 0
_EVICTION_INTERVAL = 100  # run cleanup every N requests
_MAX_ENTRIES = 10000  # hard limit on stored keys to prevent memory exhaustion


def _evict_stale_entries():
    """Prune entries older than 15 min to bound memory usage."""
    global _eviction_counter
    with _rate_limit_lock:
        _eviction_counter += 1
        if _eviction_counter < _EVICTION_INTERVAL:
            return
        _eviction_counter = 0
        now = time.time()
        stale_keys = [
            key for key, entry in _rate_limit_store.items()
            if (now - entry['window_start']) > 900
        ]
        for key in stale_keys:
            del _rate_limit_store[key]

        if len(_rate_limit_store) > _MAX_ENTRIES:
            # Sort by window_start (oldest first) and evict until we are at 90% capacity
            sorted_keys = sorted(
                _rate_limit_store.keys(),
                key=lambda k: _rate_limit_store[k]['window_start']
            )
            keys_to_remove = len(_rate_limit_store) - int(_MAX_ENTRIES * 0.9)
            for key in sorted_keys[:keys_to_remove]:
                del _rate_limit_store[key]


def _get_client_ip():
    """Extract the real client IP (ProxyFix handles X-Forwarded-For securely)."""
    return request.remote_addr


# Endpoints reached without a token, so there is nothing to key on but the
# address. All of them either hand out credentials or send mail to an address
# the caller names, which is worth rationing tightly.
_UNAUTHENTICATED_ENDPOINTS = frozenset([
    'api.create_token',
    'api.signup',
    'api.request_password_reset',
    'api.complete_password_reset',
])


def _get_rate_limit_key():
    """Build the rate-limit bucket key for this request."""
    if request.endpoint in _UNAUTHENTICATED_ENDPOINTS:
        return f'ip:{_get_client_ip()}'
    token = getattr(g, 'api_token', None)
    if token:
        return f'token:{token.id}'
    return f'ip:{_get_client_ip()}'


def _get_limits():
    """Return (max_requests, window_seconds) for the current endpoint."""
    if request.endpoint in _UNAUTHENTICATED_ENDPOINTS:
        return 5, 900
    if request.method in ('POST', 'DELETE', 'PUT', 'PATCH'):
        return 20, 60
    return 120, 60


def check_rate_limit():
    """Apply rate limits based on client IP or API token."""
    if current_app.config.get('TESTING'):
        return

    _evict_stale_entries()

    key = _get_rate_limit_key()
    max_requests, window_seconds = _get_limits()
    now = time.time()

    with _rate_limit_lock:
        entry = _rate_limit_store.get(key)

        if entry is None or (now - entry['window_start']) >= window_seconds:
            _rate_limit_store[key] = {'count': 1, 'window_start': now}
        else:
            entry['count'] += 1
            if entry['count'] > max_requests:
                reset_at = int(entry['window_start'] + window_seconds)
                retry_after = max(1, reset_at - int(now))

                response = make_error_response(
                    'rate_limited',
                    f'Rate limit exceeded. Retry after {retry_after} seconds.',
                    details={
                        'retry_after': retry_after,
                        'limit': max_requests,
                        'window': f'{window_seconds}s',
                    },
                    http_status=429,
                )
                response.headers['Retry-After'] = str(retry_after)
                response.headers['X-RateLimit-Limit'] = str(max_requests)
                response.headers['X-RateLimit-Remaining'] = '0'
                response.headers['X-RateLimit-Reset'] = str(reset_at)
                return response


def add_rate_limit_headers(response):
    """Inject X-RateLimit-* headers based on the current window."""
    if current_app.config.get('TESTING') or response.status_code == 429:
        return response

    key = _get_rate_limit_key()
    max_requests, window_seconds = _get_limits()
    now = time.time()

    with _rate_limit_lock:
        entry = _rate_limit_store.get(key)
        if entry:
            remaining = max(0, max_requests - entry['count'])
            reset_at = int(entry['window_start'] + window_seconds)
        else:
            remaining = max_requests
            reset_at = int(now + window_seconds)

    response.headers['X-RateLimit-Limit'] = str(max_requests)
    response.headers['X-RateLimit-Remaining'] = str(remaining)
    response.headers['X-RateLimit-Reset'] = str(reset_at)

    return response
