"""Block until the database accepts connections, then exit.

The Docker entrypoint runs this before starting the app so migrations and
the web server never race the database container. Connection details come
from the environment; see ``env.example``.
"""
import os
import sys
import time

import pymysql


def main() -> int:
    host = os.environ.get("DB_HOST", "db")
    port = int(os.environ.get("DB_PORT", "3306"))
    user = os.environ.get("DB_USER", "sample_platform")
    password = os.environ.get("DB_PASSWORD", "sample_platform")
    timeout = int(os.environ.get("DB_WAIT_TIMEOUT", "90"))

    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            pymysql.connect(
                host=host, port=port, user=user, password=password,
                connect_timeout=3,
            ).close()
            print(f"database reachable at {host}:{port}", flush=True)
            return 0
        except pymysql.Error as exc:
            print(f"waiting for database at {host}:{port} ({exc})", flush=True)
            time.sleep(2)

    print(f"gave up waiting for database after {timeout}s", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
