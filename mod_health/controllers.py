"""Health check endpoints for deployment verification and monitoring."""

import os
import subprocess
from datetime import datetime
from typing import Any, Dict, Optional, Tuple

from flask import Blueprint, current_app, jsonify
from sqlalchemy import text

mod_health = Blueprint('health', __name__)


def check_database() -> Dict[str, Any]:
    """
    Check database connectivity.

    :return: Dictionary with status and optional error message
    :rtype: Dict[str, Any]
    """
    try:
        from database import create_session
        db = create_session(current_app.config['DATABASE_URI'])
        db.execute(text('SELECT 1'))
        # remove() returns the scoped session's connection to the pool
        db.remove()
        return {'status': 'ok'}
    except Exception:
        current_app.logger.exception('Health check database connection failed')
        return {'status': 'error', 'message': 'Database connection failed'}


def check_config() -> Dict[str, Any]:
    """
    Check that required configuration is loaded.

    :return: Dictionary with status and optional error message
    :rtype: Dict[str, Any]
    """
    required_keys = [
        'DATABASE_URI',
        'GITHUB_TOKEN',
        'GITHUB_OWNER',
        'GITHUB_REPOSITORY',
    ]

    missing = [key for key in required_keys if not current_app.config.get(key)]

    if missing:
        return {'status': 'error', 'message': f'Missing config keys: {missing}'}
    return {'status': 'ok'}


@mod_health.route('/health')
def health_check() -> Tuple[Any, int]:
    """
    Health check endpoint for deployment verification.

    Returns 200 if all critical checks pass, 503 if any fail.
    Used by deployment pipeline to verify successful deployment.

    :return: JSON response with health status and HTTP status code
    :rtype: Tuple[Any, int]
    """
    check_results: Dict[str, Dict[str, Any]] = {}
    all_healthy = True

    # Check 1: Database connectivity
    db_check = check_database()
    check_results['database'] = db_check
    if db_check['status'] != 'ok':
        all_healthy = False

    # Check 2: Configuration loaded
    config_check = check_config()
    check_results['config'] = config_check
    if config_check['status'] != 'ok':
        all_healthy = False

    checks: Dict[str, Any] = {
        'status': 'healthy' if all_healthy else 'unhealthy',
        'timestamp': datetime.utcnow().isoformat() + 'Z',
        'checks': check_results
    }

    return jsonify(checks), 200 if all_healthy else 503


@mod_health.route('/health/live')
def liveness_check() -> Tuple[Any, int]:
    """
    Liveness check endpoint.

    Minimal check, just returns 200 if Flask is responding.
    Useful for load balancers and container orchestration.

    :return: JSON response with alive status
    :rtype: Tuple[Any, int]
    """
    return jsonify({
        'status': 'alive',
        'timestamp': datetime.utcnow().isoformat() + 'Z'
    }), 200


@mod_health.route('/health/ready')
def readiness_check() -> Tuple[Any, int]:
    """
    Readiness check endpoint.

    Same as health check but can be extended for more checks.
    Useful for Kubernetes readiness probes.

    :return: JSON response with readiness status
    :rtype: Tuple[Any, int]
    """
    return health_check()


def get_git_info() -> Dict[str, Optional[str]]:
    """
    Get git repository information for the deployed version.

    :return: Dictionary with git commit hash, short hash, and branch
    :rtype: Dict[str, Optional[str]]
    """
    result: Dict[str, Optional[str]] = {
        'commit': None,
        'short': None,
        'branch': None,
    }

    try:
        # Get the installation folder from config, fallback to current directory
        install_folder = current_app.config.get('INSTALL_FOLDER', os.getcwd())

        # Get full commit hash
        commit = subprocess.check_output(
            ['git', 'rev-parse', 'HEAD'],
            cwd=install_folder,
            stderr=subprocess.DEVNULL
        ).decode().strip()
        result['commit'] = commit
        result['short'] = commit[:7]

        # Get current branch
        branch = subprocess.check_output(
            ['git', 'rev-parse', '--abbrev-ref', 'HEAD'],
            cwd=install_folder,
            stderr=subprocess.DEVNULL
        ).decode().strip()
        result['branch'] = branch

    except (subprocess.CalledProcessError, FileNotFoundError, OSError):
        # Git not available or not a git repository
        current_app.logger.warning('Could not retrieve git version information')

    return result


@mod_health.route('/health/version')
def version_check() -> Tuple[Any, int]:
    """
    Version endpoint to verify deployed commit.

    Returns the current git commit hash, useful for verifying
    that a deployment has completed successfully.

    :return: JSON response with version information
    :rtype: Tuple[Any, int]
    """
    git_info = get_git_info()

    response = {
        'timestamp': datetime.utcnow().isoformat() + 'Z',
        'git': git_info,
    }

    # Return 200 if we have version info, 503 if we couldn't get it
    if git_info['commit']:
        return jsonify(response), 200
    else:
        response['error'] = 'Could not retrieve version information'
        return jsonify(response), 503
