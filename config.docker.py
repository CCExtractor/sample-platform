"""Container configuration for the Sample Platform.

Copied to ``config.py`` inside the image at build time. Every value is read
from the environment (see ``env.example``) with local-development defaults,
so the repository never carries a real secret. Override every placeholder
before pointing this at anything but a throwaway database.
"""
import os


def _int(name: str, default: int) -> int:
    try:
        return int(os.environ[name])
    except (KeyError, ValueError):
        return default


APPLICATION_ROOT = None
CSRF_ENABLED = True

DATABASE_URI = os.environ.get(
    "SQLALCHEMY_DATABASE_URI",
    "mysql+pymysql://sample_platform:sample_platform@db/sample_platform?charset=utf8mb4",
)
SERVER_NAME = os.environ.get("SERVER_NAME", "localhost:5000")
SESSION_COOKIE_PATH = "/"

INSTALL_FOLDER = os.environ.get("INSTALL_FOLDER", "/app")
SAMPLE_REPOSITORY = os.environ.get("SAMPLE_REPOSITORY", "/repository")

HMAC_KEY = os.environ.get("HMAC_KEY", "dev-hmac-key")
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "")
GITHUB_OWNER = os.environ.get("GITHUB_OWNER", "CCExtractor")
GITHUB_REPOSITORY = os.environ.get("GITHUB_REPOSITORY", "ccextractor")
GITHUB_CI_KEY = os.environ.get("GITHUB_CI_KEY", "")
GITHUB_CLIENT_ID = os.environ.get("GITHUB_CLIENT_ID", "")
GITHUB_CLIENT_KEY = os.environ.get("GITHUB_CLIENT_KEY", "")

EMAIL_DOMAIN = os.environ.get("EMAIL_DOMAIN", "")
EMAIL_API_KEY = os.environ.get("EMAIL_API_KEY", "")

FTP_PORT = _int("FTP_PORT", 21)
MAX_CONTENT_LENGTH = 512 * 1024 * 1024
MIN_PWD_LEN = 10
MAX_PWD_LEN = 500

# GCP / Cloud Storage. The build generates a throwaway service account so the
# storage client can initialise offline; file serving falls back to local disk.
SCOPES = ["https://www.googleapis.com/auth/cloud-platform"]
SERVICE_ACCOUNT_FILE = os.environ.get("SERVICE_ACCOUNT_FILE", "service-account.json")
ZONE = "us-west4-b"
PROJECT_NAME = "ccextractor-sampleplatform"
MACHINE_TYPE = f"zones/{ZONE}/machineTypes/n1-standard-1"
WINDOWS_INSTANCE_PROJECT_NAME = "windows-cloud"
WINDOWS_INSTANCE_FAMILY_NAME = "windows-2019"
LINUX_INSTANCE_PROJECT_NAME = "ubuntu-os-cloud"
LINUX_INSTANCE_FAMILY_NAME = "ubuntu-minimal-2404-lts-amd64"
GCP_INSTANCE_MAX_RUNTIME = 120
GCS_BUCKET_NAME = os.environ.get("GCS_BUCKET_NAME", "sample-platform-dev")
GCS_SIGNED_URL_EXPIRY_LIMIT = 720
