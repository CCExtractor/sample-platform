"""auto-generated module, using install.sh, to store configuration for the app."""

# For manual installation, fill in the fields below. If you are using
# install.sh, the config.py should have been generated for you.
APPLICATION_ROOT = None
CSRF_ENABLED = True
DATABASE_URI = 'mysql+pymysql://root:@localhost:3306/test?charset=utf8'
GITHUB_TOKEN = ''
GITHUB_OWNER = 'CCExtractor'
GITHUB_REPOSITORY = 'ccextractor'
SERVER_NAME = 'localhost'
EMAIL_DOMAIN = ''
EMAIL_API_KEY = ''
HMAC_KEY = ''
GITHUB_CI_KEY = ''
GITHUB_CLIENT_ID = ''
GITHUB_CLIENT_KEY = ''
INSTALL_FOLDER = '/path/to/installation'
SAMPLE_REPOSITORY = '/path/to/samples'
SESSION_COOKIE_PATH = '/'
FTP_PORT = 21
MAX_CONTENT_LENGTH = 512 * 1024 * 1024
MIN_PWD_LEN = 10
MAX_PWD_LEN = 500


# GCP SPECIFIC CONFIG
SCOPES = ['https://www.googleapis.com/auth/cloud-platform']
SERVICE_ACCOUNT_FILE = 'service-account.json'
ZONE = "us-west4-b"
PROJECT_NAME = "ccextractor-sampleplatform"
MACHINE_TYPE = f"zones/{ZONE}/machineTypes/n1-standard-1"
WINDOWS_INSTANCE_PROJECT_NAME = "windows-cloud"
WINDOWS_INSTANCE_FAMILY_NAME = "windows-2019"
LINUX_INSTANCE_PROJECT_NAME = "ubuntu-os-cloud"
LINUX_INSTANCE_FAMILY_NAME = "ubuntu-minimal-2404-lts-amd64"
GCP_INSTANCE_MAX_RUNTIME = 120  # In minutes
GCS_BUCKET_NAME = 'spdev'
GCS_SIGNED_URL_EXPIRY_LIMIT = 720  # In minutes


# CELERY TASK QUEUE CONFIG
CELERY_BROKER_URL = 'redis://localhost:6379/0'
CELERY_RESULT_BACKEND = 'redis://localhost:6379/0'
CELERY_TASK_SERIALIZER = 'json'
CELERY_RESULT_SERIALIZER = 'json'
CELERY_ACCEPT_CONTENT = ['json']
CELERY_TIMEZONE = 'UTC'
CELERY_ENABLE_UTC = True
CELERY_TASK_ACKS_LATE = True  # Task acknowledged after completion
CELERY_WORKER_PREFETCH_MULTIPLIER = 1  # One task at a time per worker
CELERY_TASK_REJECT_ON_WORKER_LOST = True  # Requeue tasks if worker dies
CELERY_TASK_SOFT_TIME_LIMIT = 3600  # 1 hour soft limit
CELERY_TASK_TIME_LIMIT = 3900  # 1 hour 5 minutes hard limit

# Feature flag for gradual migration (set to True to enable Celery, False for cron fallback)
USE_CELERY_TASKS = False
