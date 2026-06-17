"""
Storage helpers for resolving artifact locations.

Artifacts can live in local SAMPLE_REPOSITORY, GCS, or both. When both
exist, GCS is preferred and a signed URL is returned. When only local
exists, storage_status is 'degraded'. When neither exists, it's 'missing'.
"""

import os
from datetime import timedelta
from typing import Optional, Tuple


def resolve_artifact(relative_path: str) -> Tuple[Optional[str], str]:
    """
    Look for an artifact in local storage and GCS.

    Returns (download_url_or_None, storage_status).
    """
    from run import config, storage_client_bucket

    sample_repo = config.get('SAMPLE_REPOSITORY', '')
    local_path = os.path.join(sample_repo, relative_path)
    local_exists = os.path.isfile(local_path)

    gcs_url = None
    if storage_client_bucket:
        try:
            blob = storage_client_bucket.blob(relative_path)
            gcs_url = blob.generate_signed_url(
                version='v4',
                expiration=timedelta(minutes=config.get(
                    'GCS_SIGNED_URL_EXPIRY_LIMIT', 60)),
                method='GET',
            )
        except Exception:
            gcs_url = None

    if local_exists and gcs_url:
        return gcs_url, 'ok'
    elif gcs_url:
        # We don't block on blob.exists(), so we let the client handle 404s
        return gcs_url, 'degraded'
    elif local_exists:
        return None, 'degraded'
    else:
        return None, 'missing'


def get_log_file_path(run_id: int) -> Optional[str]:
    """Return the absolute path to a run's build log, or None if it doesn't exist."""
    from run import config

    sample_repo = config.get('SAMPLE_REPOSITORY', '')
    log_path = os.path.join(sample_repo, 'LogFiles', f'{run_id}.txt')

    if os.path.isfile(log_path):
        return log_path
    return None


def get_test_results_base_path() -> str:
    """Return the base directory where TestResults files are stored."""
    from run import config
    return os.path.join(config.get('SAMPLE_REPOSITORY', ''), 'TestResults')
