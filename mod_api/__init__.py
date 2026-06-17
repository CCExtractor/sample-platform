"""
mod_api: JSON REST API blueprint for the CCExtractor CI platform.

Registered at /api/v1. All endpoints return structured JSON, use scoped
Bearer token auth, and enforce per-client rate limiting.
"""

from flask import Blueprint

mod_api = Blueprint('api', __name__)

# Middleware (registers before_request hooks and error handlers)
# WARNING: auth must be imported before rate_limit. The auth middleware
# manually calls check_rate_limit() for unauthenticated paths. If
# rate_limit is imported first, its before_request hook fires first and
# the auth middleware's manual call would double-count requests.
from mod_api.middleware import auth  # noqa: E402, F401
from mod_api.middleware import error_handler  # noqa: E402, F401
from mod_api.middleware import rate_limit  # noqa: E402, F401
from mod_api.middleware import security  # noqa: E402, F401
# Route modules (registers endpoint functions on the blueprint)
from mod_api.routes import auth as auth_routes  # noqa: E402, F401
from mod_api.routes import errors_logs  # noqa: E402, F401
from mod_api.routes import results  # noqa: E402, F401
from mod_api.routes import runs  # noqa: E402, F401
from mod_api.routes import samples  # noqa: E402, F401
from mod_api.routes import system  # noqa: E402, F401
