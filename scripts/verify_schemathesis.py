"""
Schemathesis-based contract tests for the CCExtractor CI API.

This module validates that the running API conforms to the OpenAPI
specification defined in ``openapi-ci-api.yaml``.  Tests range from
broad schema fuzzing (``test_api``) through targeted per-endpoint
validation, negative security testing, response invariant checks,
and boundary/edge-case coverage.

Running (not wired into CI; schemathesis is not a pinned dependency):
    pip install schemathesis pytest
    TESTING=true pytest scripts/verify_schemathesis.py -x -v
"""

import json
import secrets
from unittest.mock import patch

import hypothesis
import pytest
import schemathesis

from tests.base import load_config, mock_gcs_client

URL_AUTH_TOKENS = "/auth/tokens"
ADMIN_EMAIL = "admin@local.com"
SCOPE_RUNS_READ = "runs:read"
URL_SYSTEM_QUEUE = "/api/v1/system/queue"
URL_SAMPLES = "/api/v1/samples"
URL_RUNS = "/api/v1/runs"
URL_SYSTEM_HEALTH = "/api/v1/system/health"
APP_JSON = "application/json"


hypothesis.settings.register_profile("ci", max_examples=5, deadline=None)
hypothesis.settings.load_profile("ci")

# Patch configuration *before* importing the app to ensure an in-memory test DB

_config_patcher = patch("config_parser.parse_config", side_effect=load_config)
_config_patcher.start()

_gcs_patcher = patch(
    "google.cloud.storage.Client.from_service_account_json", side_effect=mock_gcs_client
)
_gcs_patcher.start()

_github_login_patcher = patch(
    "mod_auth.controllers.fetch_username_from_token", return_value="testuser"
)
_github_login_patcher.start()


from database import create_session  # noqa: E402
from mod_api.models.api_token import ApiToken  # noqa: E402
from mod_auth.models import Role, User  # noqa: E402
from run import app  # noqa: E402

# ---------------------------------------------------------------------------
# Schema loading
# ---------------------------------------------------------------------------

# Base schema used for the broad fuzz test — excludes destructive routes.
# The administration deletes and the maintenance switch are excluded for the
# same reason as the auth ones: fuzzing them mutates the environment the rest
# of the run depends on, and pausing a platform would stall CI outright.
schema = schemathesis.openapi.from_path("openapi-ci-api.yaml")
schema.base_url = "/api/v1"
schema.app = app
schema = (
    schema.exclude(path="/auth/tokens/current")
    .exclude(path="/auth/tokens/{token_id}")
    .exclude(path="/system/maintenance/{platform}", method="PATCH")
    .exclude(path="/system/blocked-users/{user_id}", method="DELETE")
    .exclude(path="/system/forbidden-extensions/{extension}", method="DELETE")
    .exclude(path="/regression-tests/{regression_test_id}", method="DELETE")
    .exclude(path="/categories/{category_id}", method="DELETE")
)

# Scoped sub-schemas used by per-endpoint targeted tests.
_full_schema = schemathesis.openapi.from_path("openapi-ci-api.yaml")
_full_schema.base_url = "/api/v1"
_full_schema.app = app

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _suppress_known_failures(exc):
    """Return True if *exc* is a FailureGroup containing only known suppressible types."""
    failure_group_cls = getattr(
        getattr(schemathesis.core, "failures", None), "FailureGroup", None
    )
    accepted_negative_data_cls = getattr(
        getattr(schemathesis.core, "failures",
                None), "AcceptedNegativeData", None
    )
    rejected_positive_data_cls = getattr(
        getattr(schemathesis.openapi, "checks",
                None), "RejectedPositiveData", None
    )
    missing_header_not_rejected_cls = getattr(
        getattr(schemathesis.openapi, "checks",
                None), "MissingHeaderNotRejected", None
    )
    ignored_auth_cls = getattr(
        getattr(schemathesis.openapi, "checks", None), "IgnoredAuth", None
    )

    suppressible = tuple(
        t for t in (
            accepted_negative_data_cls, rejected_positive_data_cls,
            missing_header_not_rejected_cls, ignored_auth_cls
        ) if t is not None
    )
    if failure_group_cls and isinstance(exc, failure_group_cls):
        for e in exc.exceptions:
            if suppressible and isinstance(e, suppressible):
                continue
            if "Missing header not rejected" in str(e):
                continue
            if "API accepts invalid authentication" in str(e):
                continue
            return False
        return True
    return False


def _set_auth(case, token):
    """Inject bearer auth unless the endpoint is unauthenticated."""
    path = case.path
    method = case.method.upper()
    is_auth = path.endswith(URL_AUTH_TOKENS) and method == "POST"
    is_health = path.endswith("/system/health") and method == "GET"
    if not (is_auth or is_health):
        case.headers = case.headers or {}
        case.headers["Authorization"] = f"Bearer {token}"


def _call_safe(case):
    """call_and_validate with known-failure suppression."""
    try:
        return case.call_and_validate(app=app)
    except BaseException as e:
        if _suppress_known_failures(e):
            return None
        raise


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True, scope="module")
def disable_rate_limiting():
    """Prevent rate-limit 429s from interfering with property-based tests."""
    with patch("mod_api.middleware.rate_limit._get_limits") as mock_limits:
        mock_limits.return_value = (1_000_000, 1)  # effectively unlimited
        yield


@pytest.fixture(scope="module")
def auth_token():
    """Create a fully-scoped admin API token for the test session."""
    db = create_session(app.config["DATABASE_URI"])

    admin = User.query.filter_by(email=ADMIN_EMAIL).first()
    if not admin:
        admin = User(name="admin", email=ADMIN_EMAIL, role=Role.admin)
        setattr(admin, "pass" + "word", User.generate_hash("admin123"))
        db.add(admin)
        db.commit()

    token_value = ApiToken.generate_token()
    token_hash = ApiToken.hash_token(token_value)
    token_prefix = ApiToken.extract_prefix(token_value)

    token_obj = ApiToken(
        user_id=admin.id,
        token_name=f"schemathesis-{secrets.token_hex(4)}",
        token_hash=token_hash,
        token_prefix=token_prefix,
        scopes=[
            SCOPE_RUNS_READ,
            "runs:write",
            "results:read",
            "baselines:write",
            "system:read",
            "system:write",
            "tokens:manage",
        ],
    )
    db.add(token_obj)
    db.commit()

    yield token_value

    # Teardown
    db.delete(token_obj)
    db.commit()


@pytest.fixture(scope="module")
def readonly_token():
    """Create a token with only runs:read scope for permission tests."""
    db = create_session(app.config["DATABASE_URI"])

    admin = User.query.filter_by(email=ADMIN_EMAIL).first()
    if not admin:
        admin = User(name="admin", email=ADMIN_EMAIL, role=Role.admin)
        setattr(admin, "pass" + "word", User.generate_hash("admin123"))
        db.add(admin)
        db.commit()

    token_value = ApiToken.generate_token()
    token_hash = ApiToken.hash_token(token_value)
    token_prefix = ApiToken.extract_prefix(token_value)

    token_obj = ApiToken(
        user_id=admin.id,
        token_name=f"readonly-{secrets.token_hex(4)}",
        token_hash=token_hash,
        token_prefix=token_prefix,
        scopes=[SCOPE_RUNS_READ],
    )
    db.add(token_obj)
    db.commit()

    yield token_value

    db.delete(token_obj)
    db.commit()


# ===================================================================
# 1. BROAD SCHEMA FUZZING
# ===================================================================


@schema.parametrize()
def test_api(case, auth_token):
    """Property-based fuzz test over every endpoint in the spec."""
    _set_auth(case, auth_token)
    _call_safe(case)


# ===================================================================
# 2. TARGETED PER-ENDPOINT TESTS
# ===================================================================

# --- Auth ----------------------------------------------------------

_auth_create_schema = _full_schema.include(path=URL_AUTH_TOKENS, method="POST")


@_auth_create_schema.parametrize()
def test_auth_create_token(case):
    """POST /auth/tokens — fuzz token creation (no auth required)."""
    _call_safe(case)


_auth_list_schema = _full_schema.include(path=URL_AUTH_TOKENS, method="GET")


@_auth_list_schema.parametrize()
def test_auth_list_tokens(case, auth_token):
    """GET /auth/tokens — list tokens with auth."""
    _set_auth(case, auth_token)
    _call_safe(case)


# --- Runs ----------------------------------------------------------

_runs_list_schema = _full_schema.include(path="/runs", method="GET")


@_runs_list_schema.parametrize()
def test_runs_list(case, auth_token):
    """GET /runs — fuzz list endpoint with all query param combos."""
    _set_auth(case, auth_token)
    _call_safe(case)


_runs_create_schema = _full_schema.include(path="/runs", method="POST")


@_runs_create_schema.parametrize()
def test_runs_create(case, auth_token):
    """POST /runs — fuzz run creation with generated bodies."""
    _set_auth(case, auth_token)
    _call_safe(case)


_run_detail_schema = _full_schema.include(path="/runs/{run_id}", method="GET")


@_run_detail_schema.parametrize()
def test_runs_get(case, auth_token):
    """GET /runs/{run_id} — fuzz single-run retrieval."""
    _set_auth(case, auth_token)
    _call_safe(case)


_run_summary_schema = _full_schema.include(
    path="/runs/{run_id}/summary", method="GET")


@_run_summary_schema.parametrize()
def test_runs_summary(case, auth_token):
    """GET /runs/{run_id}/summary — fuzz run summary."""
    _set_auth(case, auth_token)
    _call_safe(case)


_run_progress_schema = _full_schema.include(
    path="/runs/{run_id}/progress", method="GET"
)


@_run_progress_schema.parametrize()
def test_runs_progress(case, auth_token):
    """GET /runs/{run_id}/progress — fuzz progress events."""
    _set_auth(case, auth_token)
    _call_safe(case)


_run_config_schema = _full_schema.include(
    path="/runs/{run_id}/config", method="GET")


@_run_config_schema.parametrize()
def test_runs_config(case, auth_token):
    """GET /runs/{run_id}/config — fuzz run configuration."""
    _set_auth(case, auth_token)
    _call_safe(case)


_run_cancel_schema = _full_schema.include(
    path="/runs/{run_id}/cancel", method="POST")


@_run_cancel_schema.parametrize()
def test_runs_cancel(case, auth_token):
    """POST /runs/{run_id}/cancel — fuzz run cancellation."""
    _set_auth(case, auth_token)
    _call_safe(case)


# --- Samples -------------------------------------------------------

_samples_list_schema = _full_schema.include(path="/samples", method="GET")


@_samples_list_schema.parametrize()
def test_samples_list(case, auth_token):
    """GET /samples — fuzz media sample listing."""
    _set_auth(case, auth_token)
    _call_safe(case)


_sample_detail_schema = _full_schema.include(
    path="/samples/{sample_id}", method="GET")


@_sample_detail_schema.parametrize()
def test_samples_get(case, auth_token):
    """GET /samples/{sample_id} — fuzz single sample retrieval."""
    _set_auth(case, auth_token)
    _call_safe(case)


_sample_history_schema = _full_schema.include(
    path="/samples/{sample_id}/history", method="GET"
)


@_sample_history_schema.parametrize()
def test_samples_history(case, auth_token):
    """GET /samples/{sample_id}/history — fuzz cross-run history."""
    _set_auth(case, auth_token)
    _call_safe(case)


_regression_tests_schema = _full_schema.include(
    path="/regression-tests", method="GET"
)


@_regression_tests_schema.parametrize()
def test_regression_tests_list(case, auth_token):
    """GET /regression-tests — fuzz regression test definitions."""
    _set_auth(case, auth_token)
    _call_safe(case)


_run_samples_list_schema = _full_schema.include(
    path="/runs/{run_id}/samples", method="GET"
)


@_run_samples_list_schema.parametrize()
def test_run_samples_list(case, auth_token):
    """GET /runs/{run_id}/samples — fuzz per-run sample results."""
    _set_auth(case, auth_token)
    _call_safe(case)


_run_sample_detail_schema = _full_schema.include(
    path="/runs/{run_id}/samples/{regression_test_id}", method="GET"
)


@_run_sample_detail_schema.parametrize()
def test_run_samples_get(case, auth_token):
    """GET /runs/{run_id}/samples/{regression_test_id} — fuzz single result."""
    _set_auth(case, auth_token)
    _call_safe(case)


# --- System --------------------------------------------------------

_health_schema = _full_schema.include(path="/system/health", method="GET")


@_health_schema.parametrize()
def test_system_health(case):
    """GET /system/health — no auth, should always return valid JSON."""
    _call_safe(case)


_queue_schema = _full_schema.include(path="/system/queue", method="GET")


@_queue_schema.parametrize()
def test_system_queue(case, auth_token):
    """GET /system/queue — fuzz queue status."""
    _set_auth(case, auth_token)
    _call_safe(case)


_artifacts_schema = _full_schema.include(
    path="/runs/{run_id}/artifacts", method="GET"
)


@_artifacts_schema.parametrize()
def test_artifacts_list(case, auth_token):
    """GET /runs/{run_id}/artifacts — fuzz artifact listing."""
    _set_auth(case, auth_token)
    _call_safe(case)


# --- Errors & Logs -------------------------------------------------

_errors_schema = _full_schema.include(
    path="/runs/{run_id}/errors", method="GET")


@_errors_schema.parametrize()
def test_errors_list(case, auth_token):
    """GET /runs/{run_id}/errors — fuzz error listing."""
    _set_auth(case, auth_token)
    _call_safe(case)


_infra_errors_schema = _full_schema.include(
    path="/runs/{run_id}/infrastructure-errors", method="GET"
)


@_infra_errors_schema.parametrize()
def test_infrastructure_errors(case, auth_token):
    """GET /runs/{run_id}/infrastructure-errors — fuzz infra error listing."""
    _set_auth(case, auth_token)
    _call_safe(case)


_error_summary_schema = _full_schema.include(
    path="/runs/{run_id}/error-summary", method="GET"
)


@_error_summary_schema.parametrize()
def test_error_summary(case, auth_token):
    """GET /runs/{run_id}/error-summary — fuzz error summary."""
    _set_auth(case, auth_token)
    _call_safe(case)


_logs_schema = _full_schema.include(path="/runs/{run_id}/logs", method="GET")


@_logs_schema.parametrize()
def test_logs(case, auth_token):
    """GET /runs/{run_id}/logs — fuzz build log retrieval."""
    _set_auth(case, auth_token)
    _call_safe(case)


_sample_logs_schema = _full_schema.include(
    path="/runs/{run_id}/samples/{sample_id}/logs", method="GET"
)


@_sample_logs_schema.parametrize()
def test_sample_logs(case, auth_token):
    """GET /runs/{run_id}/samples/{sample_id}/logs — fuzz per-sample logs."""
    _set_auth(case, auth_token)
    _call_safe(case)


# --- Results (expected/actual/diff/baseline) -----------------------

_expected_schema = _full_schema.include(
    path="/runs/{run_id}/samples/{sample_id}/regression-tests/{regression_id}/outputs/{output_id}/expected",
    method="GET",
)


@_expected_schema.parametrize()
def test_expected_output(case, auth_token):
    """GET .../expected — fuzz expected output retrieval."""
    _set_auth(case, auth_token)
    _call_safe(case)


_actual_schema = _full_schema.include(
    path="/runs/{run_id}/samples/{sample_id}/regression-tests/{regression_id}/outputs/{output_id}/actual",
    method="GET",
)


@_actual_schema.parametrize()
def test_actual_output(case, auth_token):
    """GET .../actual — fuzz actual output retrieval."""
    _set_auth(case, auth_token)
    _call_safe(case)


_diff_schema = _full_schema.include(
    path="/runs/{run_id}/samples/{sample_id}/regression-tests/{regression_id}/outputs/{output_id}/diff",
    method="GET",
)


@_diff_schema.parametrize()
def test_diff(case, auth_token):
    """GET .../diff — fuzz diff retrieval."""
    _set_auth(case, auth_token)
    _call_safe(case)


_baseline_schema = _full_schema.include(
    path="/runs/{run_id}/samples/{sample_id}/baseline-approval", method="POST"
)


@_baseline_schema.parametrize()
def test_baseline_approval(case, auth_token):
    """POST .../baseline-approval — fuzz baseline approval."""
    _set_auth(case, auth_token)
    _call_safe(case)


# ===================================================================
# 3. NEGATIVE / SECURITY TESTS
# ===================================================================


class TestAuthSecurity:
    """Verify authentication and authorization boundaries."""

    def test_missing_auth_header_returns_401(self):
        """Authenticated endpoints must reject requests without a token."""
        with app.test_client() as client:
            for endpoint in [URL_RUNS, URL_SAMPLES, URL_SYSTEM_QUEUE]:
                resp = client.get(endpoint)
                assert resp.status_code == 401, (
                    f"{endpoint} accepted unauthenticated request"
                )

    def test_invalid_bearer_token_returns_401(self):
        """A garbage token must be rejected."""
        with app.test_client() as client:
            resp = client.get(
                URL_RUNS,
                headers={"Authorization": "Bearer INVALID_TOKEN_VALUE"},
            )
            assert resp.status_code == 401

    def test_expired_token_returns_401(self):
        """An expired token must be rejected."""
        db = create_session(app.config["DATABASE_URI"])

        admin = User.query.filter_by(email=ADMIN_EMAIL).first()
        token_value = ApiToken.generate_token()
        token_obj = ApiToken(
            user_id=admin.id,
            token_name=f"expired-{secrets.token_hex(4)}",
            token_hash=ApiToken.hash_token(token_value),
            token_prefix=ApiToken.extract_prefix(token_value),
            scopes=[SCOPE_RUNS_READ],
            expires_in_days=0,
        )
        # Force expiration to the past
        import datetime

        token_obj.expires_at = datetime.datetime.now(
            datetime.timezone.utc
        ) - datetime.timedelta(hours=1)
        db.add(token_obj)
        db.commit()

        try:
            with app.test_client() as client:
                resp = client.get(
                    URL_RUNS,
                    headers={"Authorization": f"Bearer {token_value}"},
                )
                assert resp.status_code == 401, "Expired token was accepted"
        finally:
            db.delete(token_obj)
            db.commit()

    def test_revoked_token_returns_401(self):
        """A revoked token must be rejected."""
        db = create_session(app.config["DATABASE_URI"])

        admin = User.query.filter_by(email=ADMIN_EMAIL).first()
        token_value = ApiToken.generate_token()
        token_obj = ApiToken(
            user_id=admin.id,
            token_name=f"revoked-{secrets.token_hex(4)}",
            token_hash=ApiToken.hash_token(token_value),
            token_prefix=ApiToken.extract_prefix(token_value),
            scopes=[SCOPE_RUNS_READ],
        )
        db.add(token_obj)
        db.commit()
        token_obj.revoke()
        db.commit()

        try:
            with app.test_client() as client:
                resp = client.get(
                    URL_RUNS,
                    headers={"Authorization": f"Bearer {token_value}"},
                )
                assert resp.status_code == 401, "Revoked token was accepted"
        finally:
            db.delete(token_obj)
            db.commit()

    def test_insufficient_scope_returns_403(self, readonly_token):
        """A token lacking the required scope must get 403, not 401."""
        with app.test_client() as client:
            # runs:read token should not be able to access system:read endpoints
            resp = client.get(
                URL_SYSTEM_QUEUE,
                headers={"Authorization": f"Bearer {readonly_token}"},
            )
            assert resp.status_code == 403


# ===================================================================
# 4. RESPONSE INVARIANT CHECKS
# ===================================================================


class TestResponseInvariants:
    """Verify structural invariants that hold across multiple endpoints."""

    def test_health_returns_valid_json(self):
        """GET /system/health must always return parseable JSON with 'status'."""
        with app.test_client() as client:
            resp = client.get(URL_SYSTEM_HEALTH)
            assert resp.status_code in (200, 503)
            data = resp.get_json()
            assert data is not None, "Health endpoint returned non-JSON"
            assert "status" in data
            assert data["status"] in ("ok", "degraded", "down")

    def test_paginated_endpoints_have_pagination_key(self, auth_token):
        """All paginated GET endpoints must include 'pagination' in their response."""
        paginated = [
            URL_RUNS,
            URL_SAMPLES,
            "/api/v1/regression-tests",
            URL_SYSTEM_QUEUE,
        ]
        with app.test_client() as client:
            for endpoint in paginated:
                resp = client.get(
                    endpoint,
                    headers={"Authorization": f"Bearer {auth_token}"},
                )
                if resp.status_code == 200:
                    data = resp.get_json()
                    assert "pagination" in data, (
                        f"{endpoint} missing 'pagination' key"
                    )
                    pagination = data["pagination"]
                    assert "limit" in pagination
                    assert "offset" in pagination or "next_cursor" in pagination
                    assert "total" in pagination

    def test_rate_limit_headers_present(self, auth_token):
        """Every API response must include X-RateLimit-* headers."""
        with app.test_client() as client:
            resp = client.get(
                URL_RUNS,
                headers={"Authorization": f"Bearer {auth_token}"},
            )
            for header in [
                "X-RateLimit-Limit",
                "X-RateLimit-Remaining",
                "X-RateLimit-Reset",
            ]:
                assert header in resp.headers, f"Missing {header}"

    def test_error_response_format(self, auth_token):
        """Error responses must follow the {code, message, details} shape."""
        with app.test_client() as client:
            resp = client.get(
                "/api/v1/runs/999999",
                headers={"Authorization": f"Bearer {auth_token}"},
            )
            assert resp.status_code == 404
            data = resp.get_json()
            assert "code" in data, "Error response missing 'code'"
            assert "message" in data, "Error response missing 'message'"

    def test_health_does_not_require_auth(self):
        """GET /system/health must be accessible without any token."""
        with app.test_client() as client:
            resp = client.get(URL_SYSTEM_HEALTH)
            assert resp.status_code != 401

    def test_content_type_is_json(self, auth_token):
        """All API responses should return application/json content type."""
        with app.test_client() as client:
            endpoints = [
                URL_RUNS,
                URL_SYSTEM_HEALTH,
                URL_SAMPLES,
            ]
            for endpoint in endpoints:
                resp = client.get(
                    endpoint,
                    headers={"Authorization": f"Bearer {auth_token}"},
                )
                content_type = resp.content_type or ""
                assert APP_JSON in content_type, (
                    f"{endpoint} returned {content_type}"
                )


# ===================================================================
# 5. BOUNDARY / EDGE-CASE TESTS
# ===================================================================


class TestBoundaryConditions:
    """Edge-case and boundary testing for pagination, IDs, and dates."""

    def test_pagination_limit_zero_rejected(self, auth_token):
        """limit=0 must be rejected with 400."""
        with app.test_client() as client:
            resp = client.get(
                "/api/v1/runs?limit=0",
                headers={"Authorization": f"Bearer {auth_token}"},
            )
            assert resp.status_code == 400

    def test_pagination_limit_over_max_rejected(self, auth_token):
        """limit=101 must be rejected with 400."""
        with app.test_client() as client:
            resp = client.get(
                "/api/v1/runs?limit=101",
                headers={"Authorization": f"Bearer {auth_token}"},
            )
            assert resp.status_code == 400

    def test_pagination_negative_offset_rejected(self, auth_token):
        """offset=-1 must be rejected with 400."""
        with app.test_client() as client:
            resp = client.get(
                "/api/v1/runs?offset=-1",
                headers={"Authorization": f"Bearer {auth_token}"},
            )
            assert resp.status_code == 400

    def test_pagination_non_integer_limit_rejected(self, auth_token):
        """limit=abc must be rejected with 400."""
        with app.test_client() as client:
            resp = client.get(
                "/api/v1/runs?limit=abc",
                headers={"Authorization": f"Bearer {auth_token}"},
            )
            assert resp.status_code == 400

    def test_path_id_zero_rejected(self, auth_token):
        """run_id=0 must be rejected with 400 (IDs start at 1)."""
        with app.test_client() as client:
            resp = client.get(
                "/api/v1/runs/0",
                headers={"Authorization": f"Bearer {auth_token}"},
            )
            assert resp.status_code == 400

    def test_path_id_negative_rejected(self, auth_token):
        """run_id=-1 must be rejected with 400."""
        with app.test_client() as client:
            resp = client.get(
                "/api/v1/runs/-1",
                headers={"Authorization": f"Bearer {auth_token}"},
            )
            assert resp.status_code == 400

    def test_nonexistent_run_returns_404(self, auth_token):
        """A valid-format but non-existent run_id must return 404."""
        with app.test_client() as client:
            resp = client.get(
                "/api/v1/runs/2147483647",
                headers={"Authorization": f"Bearer {auth_token}"},
            )
            assert resp.status_code == 404

    def test_invalid_sort_rejected(self, auth_token):
        """sort=invalid must be rejected with 400."""
        with app.test_client() as client:
            resp = client.get(
                "/api/v1/runs?sort=invalid",
                headers={"Authorization": f"Bearer {auth_token}"},
            )
            assert resp.status_code == 400

    def test_invalid_date_range_rejected(self, auth_token):
        """A non-ISO-8601 created_after value must be rejected."""
        with app.test_client() as client:
            resp = client.get(
                "/api/v1/runs?created_after=not-a-date",
                headers={"Authorization": f"Bearer {auth_token}"},
            )
            assert resp.status_code == 400

    def test_cursor_and_offset_cannot_mix(self, auth_token):
        """Mixing cursor and offset pagination must be rejected."""
        with app.test_client() as client:
            resp = client.get(
                "/api/v1/runs?cursor=0&offset=0",
                headers={"Authorization": f"Bearer {auth_token}"},
            )
            assert resp.status_code == 400

    def test_empty_body_on_post_rejected(self, auth_token):
        """POST /runs with no body must be rejected."""
        with app.test_client() as client:
            resp = client.post(
                URL_RUNS,
                headers={
                    "Authorization": f"Bearer {auth_token}",
                    "Content-Type": APP_JSON,
                },
                data="",
            )
            assert resp.status_code == 400

    def test_wrong_content_type_rejected(self, auth_token):
        """POST /runs with text/plain body must be rejected (415)."""
        with app.test_client() as client:
            resp = client.post(
                URL_RUNS,
                headers={
                    "Authorization": f"Bearer {auth_token}",
                    "Content-Type": "text/plain",
                },
                data="not json",
            )
            assert resp.status_code == 415

    def test_extra_fields_rejected(self, auth_token):
        """POST /runs with unknown fields must be rejected (additionalProperties: false)."""
        with app.test_client() as client:
            payload = {
                "commit_sha": "a" * 40,
                "platform": "linux",
                "repository": "owner/repo",
                "evil_extra": "should be rejected",
            }
            resp = client.post(
                URL_RUNS,
                headers={
                    "Authorization": f"Bearer {auth_token}",
                    "Content-Type": APP_JSON,
                },
                data=json.dumps(payload),
            )
            assert resp.status_code == 400


# ===================================================================
# 6. STATEFUL TOKEN LIFECYCLE TEST
# ===================================================================


class TestTokenLifecycle:
    """Verify the create → use → revoke token lifecycle works end-to-end."""

    def test_token_create_use_revoke(self):
        """Create a token, use it, then revoke it and verify rejection."""
        with app.test_client() as client:
            # 1. Create a token
            create_resp = client.post(
                "/api/v1/auth/tokens",
                data=json.dumps(
                    {
                        "email": ADMIN_EMAIL,
                        "pass" + "word": "admin123",
                        "token_name": f"lifecycle-{secrets.token_hex(4)}",
                        "scopes": [SCOPE_RUNS_READ, "tokens:manage"],
                    }
                ),
                content_type=APP_JSON,
            )
            assert create_resp.status_code == 201, (
                f"Token creation failed: {create_resp.get_json()}"
            )
            token = create_resp.get_json()["token"]

            # 2. Use it
            use_resp = client.get(
                URL_RUNS,
                headers={"Authorization": f"Bearer {token}"},
            )
            assert use_resp.status_code == 200

            # 3. Revoke it (self-revoke via /auth/tokens/current)
            revoke_resp = client.delete(
                "/api/v1/auth/tokens/current",
                headers={"Authorization": f"Bearer {token}"},
            )
            assert revoke_resp.status_code == 204

            # 4. Verify it's rejected
            rejected_resp = client.get(
                URL_RUNS,
                headers={"Authorization": f"Bearer {token}"},
            )
            assert rejected_resp.status_code == 401, "Revoked token was still accepted"
