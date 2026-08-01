"""Write a throwaway Google service-account file for local development.

run.py builds a storage client at import time, which needs a syntactically
valid service-account JSON even when there is no GCP project behind it. The
key generated here authenticates nothing.
"""
import json
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

# Matches SERVICE_ACCOUNT_FILE in config.docker.py. Not a command line
# argument: nothing needs to pick the location, and accepting one would only
# be a way to write outside the application directory.
TARGET = Path(__file__).resolve().parent.parent / 'service-account.json'


def main() -> None:
    """Write the credentials file unless one is already present."""
    if TARGET.exists():
        return

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private_key = key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.TraditionalOpenSSL,
        serialization.NoEncryption(),
    ).decode()

    TARGET.write_text(json.dumps({
        "type": "service_account",
        "project_id": "sample-platform-dev",
        "private_key_id": "dev",
        "private_key": private_key,
        "client_email": "dev@sample-platform-dev.iam.gserviceaccount.com",
        "client_id": "0",
        "auth_uri": "https://accounts.google.com/o/oauth2/auth",
        "token_uri": "https://oauth2.googleapis.com/token",
    }, indent=2))


if __name__ == "__main__":
    main()
