"""
Storage helpers for resolving artifact locations.

Artifacts can live in local SAMPLE_REPOSITORY, GCS, or both. When both
exist, GCS is preferred and a signed URL is returned. When only local
exists, storage_status is 'degraded'. When neither exists, it's 'missing'.
"""

import logging
import os
from datetime import timedelta
from typing import Optional, Tuple

logger = logging.getLogger(__name__)


def resolve_artifact(relative_path: str) -> Tuple[Optional[str], str]:
    """
    Look for an artifact in local storage and GCS.

    Returns (download_url_or_None, storage_status).
    """
    from run import config, storage_client_bucket

    sample_repo = config.get('SAMPLE_REPOSITORY', '')
    local_path = os.path.join(sample_repo, relative_path)
    # Prevent path traversal: resolved path must stay within sample_repo
    real_base = os.path.realpath(sample_repo)
    real_path = os.path.realpath(local_path)
    if not (real_path.startswith(real_base + os.sep) or real_path == real_base):
        return None, 'missing'
    local_exists = os.path.isfile(local_path)

    gcs_url = None
    if storage_client_bucket:
        try:
            blob = storage_client_bucket.blob(relative_path)
            if blob.exists():
                gcs_url = blob.generate_signed_url(
                    version='v4',
                    # int() guards against a string value in config, which
                    # would otherwise raise inside timedelta and be swallowed
                    # by the except below as a silent 'degraded'.
                    expiration=timedelta(minutes=int(config.get(
                        'GCS_SIGNED_URL_EXPIRY_LIMIT', 60))),
                    method='GET',
                )
        except Exception as e:
            logger.warning(f"Failed to generate GCS signed URL for {relative_path}: {e}")
            gcs_url = None

    if local_exists and gcs_url:
        return gcs_url, 'ok'
    elif gcs_url:
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
