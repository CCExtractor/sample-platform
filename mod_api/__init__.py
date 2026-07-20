"""
mod_api: JSON REST API blueprint for the CCExtractor CI platform.

Registered at /api/v1. All endpoints return structured JSON, use scoped
Bearer token auth, and enforce per-client rate limiting.
"""

from flask import Blueprint

mod_api = Blueprint('api', __name__)

# Middleware imports
from mod_api.middleware import auth  # noqa: E402
from mod_api.middleware import error_handler  # noqa: E402
from mod_api.middleware import rate_limit  # noqa: E402
from mod_api.middleware import security  # noqa: E402

# Explicitly register before_request hooks in the exact order they should run
mod_api.before_request(auth.authenticate_request)
mod_api.before_request(rate_limit.check_rate_limit)
mod_api.before_request(auth.enforce_auth_error)

# Explicitly register after_request hooks.
# NOTE: Flask executes after_request hooks in REVERSE registration order.
# Registration:  security → rate_limit → (convert is app-level, see below)
# Execution:     rate_limit → security
# This means rate-limit headers are added first, then security headers layer
# on top — both on the same response object.
mod_api.after_request(security.add_security_headers)
mod_api.after_request(rate_limit.add_rate_limit_headers)

# Registered as after_app_request so it fires for ALL requests (including
# routing-level 404s/405s that never enter the blueprint).
mod_api.after_app_request(error_handler.convert_api_errors_to_json)

# Route modules register themselves against the blueprint; the rest of
# the stack adds one module per PR.
from mod_api.routes import auth as auth_routes  # noqa: E402, F401
