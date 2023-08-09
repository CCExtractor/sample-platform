"""auto-generated module, using install.sh, to store configuration for the app."""

# For manual installation, fill in the fields below. If you are using
# install.sh, the config.py should have been generated for you.
APPLICATION_ROOT = None
CSRF_ENABLED = True
DATABASE_URI = 'mysql+pymysql://root:@localhost:3306/test?charset=utf8'
GITHUB_BOT = ''
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
LINUX_INSTANCE_FAMILY_NAME = "ubuntu-minimal-2204-lts"
GCP_INSTANCE_MAX_RUNTIME = 120  # In minutes
GCS_BUCKET_NAME = 'spdev'
GCS_SIGNED_URL_EXPIRY_LIMIT = 720  # In minutes
