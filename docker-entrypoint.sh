#!/bin/bash
set -e

# Professional Logging Function
log() {
    local message="$1"
    echo -e "\033[1;34m[Platform]\033[0m ${message}"
    return 0
}

# --- 1. Ensure Secret Key Files Exist ---

if [[ ! -f "/app/secret_key" ]]; then
    log "Generating secret_key file..."
    head -c 24 /dev/urandom > /app/secret_key
fi
if [[ ! -f "/app/secret_csrf" ]]; then
    log "Generating secret_csrf file..."
    head -c 24 /dev/urandom > /app/secret_csrf
fi

# --- 2. Ensure Git Repo Exists ---
git config --global --add safe.directory /app
if [[ ! -d "/app/.git" ]]; then
    log "Initializing git repository (required by GitPython for build commit display)..."
    git init /app > /dev/null 2>&1
    git -C /app config user.email "docker@sample-platform.local"
    git -C /app config user.name "Docker"
    git -C /app add -A > /dev/null 2>&1
    git -C /app commit -m "Docker build" --allow-empty > /dev/null 2>&1
fi

# --- 3. Ensure GCP Service Account File Exists ---
SA_PATH="/app/service-account.json"
REAL_SA_PATH="$SA_PATH"

# Docker mounts a directory if the host file doesn't exist.
if [[ -d "$SA_PATH" ]]; then
    log "WARNING: $SA_PATH is a directory (likely because ./service-account.json is missing on host)."
    log "Using internal path for generated credentials..."
    REAL_SA_PATH="/app/generated-service-account.json"
    export GOOGLE_APPLICATION_CREDENTIALS="$REAL_SA_PATH"
    export SERVICE_ACCOUNT_FILE="generated-service-account.json"
fi

if [[ ! -f "$REAL_SA_PATH" ]]; then
    log "Generating dummy service-account.json at $REAL_SA_PATH (GCS will use local fallback)..."
    python3 -c "
import json
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives import serialization

try:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pem = key.private_bytes(serialization.Encoding.PEM,
        serialization.PrivateFormat.TraditionalOpenSSL,
        serialization.NoEncryption()).decode()
except Exception as e:
    print(f'WARNING: Key generation failed: {e}')
    pem = 'DUMMY_KEY'

sa = {
    'type': 'service_account',
    'project_id': 'docker-dev',
    'private_key_id': 'docker-dev-key',
    'private_key': pem,
    'client_email': 'docker-dev@docker-dev.iam.gserviceaccount.com',
    'client_id': '000000000000',
    'auth_uri': 'https://accounts.google.com/o/oauth2/auth',
    'token_uri': 'https://oauth2.googleapis.com/token',
}
with open('$REAL_SA_PATH', 'w') as f:
    json.dump(sa, f, indent=2)
"
fi

# Ensure logs directory exists (critical for gunicorn)
mkdir -p logs

# --- 4. Configure & Mount Storage ---
# Determine where the repository is located.
# If GCS_BUCKET_NAME is set, we mount it to a clean path and use that.
# Otherwise, we use the default volume mount at /repository.

if [[ -n "$GCS_BUCKET_NAME" ]] && [[ -f "$REAL_SA_PATH" ]]; then
    log "GCS_BUCKET_NAME is set to '$GCS_BUCKET_NAME'. Configuring GCS mount..."
    
    # Use a separate mount point to avoid conflict with local volume at /repository
    GCS_MOUNT_POINT="/mnt/gcs_repository"
    mkdir -p "$GCS_MOUNT_POINT"
    
    log "Mounting '$GCS_BUCKET_NAME' to '$GCS_MOUNT_POINT'..."
    set +e
    gcsfuse --key-file "$REAL_SA_PATH" \
            --implicit-dirs \
            --uid 1001 --gid 1001 \
            --file-mode 666 --dir-mode 777 \
            -o allow_other \
            --debug_gcs \
            --debug_fuse \
            --log-file /tmp/gcsfuse_debug.log \
            --log-format text \
            "$GCS_BUCKET_NAME" "$GCS_MOUNT_POINT" > /tmp/gcsfuse.log 2>&1
    MOUNT_STATUS=$?
    set -e

    if [[ $MOUNT_STATUS -eq 0 ]]; then
        log "SUCCESS: GCS bucket mounted at $GCS_MOUNT_POINT"
        export SAMPLE_REPOSITORY="$GCS_MOUNT_POINT"
    else
        log "CRITICAL ERROR: Failed to mount GCS bucket."
        log "--- gcsfuse stderr ---"
        cat /tmp/gcsfuse.log
        log "----------------------"
        if [[ -f "/tmp/gcsfuse_debug.log" ]]; then
            log "--- gcsfuse debug log (last 20 lines) ---"
            tail -n 20 /tmp/gcsfuse_debug.log
            log "----------------------"
        fi
        exit 1
    fi
else
    log "GCS not configured. Using local storage."
    # Default to /repository if not set
    export SAMPLE_REPOSITORY="${SAMPLE_REPOSITORY:-/repository}"
fi

# --- 5. Setup Repository Structure ---
REPO="$SAMPLE_REPOSITORY"
log "Ensuring repository structure exists in: $REPO"

mkdir -p "${REPO}/ci-tests"
mkdir -p "${REPO}/unsafe-ccextractor"
mkdir -p "${REPO}/TempFiles"
mkdir -p "${REPO}/LogFiles"
mkdir -p "${REPO}/TestResults"
mkdir -p "${REPO}/TestFiles"
mkdir -p "${REPO}/TestFiles/media"
mkdir -p "${REPO}/QueuedFiles"
mkdir -p "${REPO}/TestData/ci-linux"
mkdir -p "${REPO}/TestData/ci-windows"
mkdir -p "${REPO}/vm_data"

# Ensure appuser has write access to the repository
chown -R appuser:appuser "$REPO" 2>/dev/null || true

# --- 6. Install Initial Data (if requested) ---
if [[ "${INSTALL_SAMPLE_DATA}" = "true" ]] && [[ -d "/app/install/sample_files" ]]; then
    log "Copying sample files to ${REPO}/TestFiles/..."
    cp -rn /app/install/sample_files/* "${REPO}/TestFiles/" 2>/dev/null || true
fi

if [[ -d "/app/install/ci-vm/ci-windows/ci" ]]; then
    cp -rn /app/install/ci-vm/ci-windows/ci/* "${REPO}/TestData/ci-windows/" 2>/dev/null || true
fi
if [[ -d "/app/install/ci-vm/ci-linux/ci" ]]; then
    cp -rn /app/install/ci-vm/ci-linux/ci/* "${REPO}/TestData/ci-linux/" 2>/dev/null || true
fi

# --- 7. Wait for Database Service ---
log "Waiting for MySQL at ${DB_HOST:-db}:${DB_PORT:-3306}..."
timeout=60
counter=0
DB_HOST="${DB_HOST:-db}"
DB_PORT="${DB_PORT:-3306}"
while ! nc -z "$DB_HOST" "$DB_PORT"; do
  sleep 1
  counter=$((counter + 1))
  if [[ $counter -ge $timeout ]]; then
    log "ERROR: MySQL connection timeout after ${timeout} seconds"
    exit 1
  fi
done
log "MySQL is up and reachable."

# Give MySQL extra time to finish initialization
sleep 3

# --- 8. Database Schema Setup ---
# Two schema mechanisms exist in this codebase:
#   a) database.py → create_session() calls Base.metadata.create_all() when the app is imported
#   b) Flask-Migrate (Alembic) for versioned migrations

ALEMBIC_EXISTS=$(python3 -c "
import pymysql, os
try:
    conn = pymysql.connect(host='${DB_HOST}', port=${DB_PORT},
        user='${MYSQL_USER:-root}', password='${MYSQL_ROOT_PASSWORD:-root}',
        database='${MYSQL_DATABASE:-sample_platform}')
    cursor = conn.cursor()
    cursor.execute(\"SHOW TABLES LIKE 'alembic_version'\")
    result = cursor.fetchone()
    conn.close()
    print('yes' if result else 'no')
except Exception:
    print('no')
" 2>/dev/null)

if [[ "$ALEMBIC_EXISTS" = "no" ]]; then
    log "Fresh database detected. Setting up schema..."

    # Ensure migrations directory is properly initialized
    if [[ ! -d "migrations/versions" ]]; then
        log "Initializing fresh migrations folder..."
        rm -rf migrations
        flask db init || {
            log "ERROR: Failed to initialize migrations"
            exit 1
        }
    fi

    # Import the app (triggers create_all via create_session), then stamp HEAD.
    log "Creating tables and stamping migration head..."
    flask db stamp head || {
        log "ERROR: Could not stamp migration head. Cannot proceed."
        exit 1
    }

    flask db migrate -m "Docker auto-migration" 2>/dev/null || log "No new migrations needed"
    flask db upgrade 2>/dev/null || log "No upgrades needed"
else
    log "Existing database detected. Applying any pending migrations..."

    if [[ ! -d "migrations/versions" ]]; then
        rm -rf migrations
        flask db init || {
            log "ERROR: Failed to initialize migrations"
            exit 1
        }
        flask db stamp head || {
            log "ERROR: Could not stamp migration head."
            exit 1
        }
    fi

    flask db migrate -m "Docker auto-migration" 2>/dev/null || log "No new migrations detected"
    flask db upgrade 2>/dev/null || log "No upgrades to apply"
fi

log "Database schema is ready."

# --- 9. Initialize Admin User and Sample Data ---
ADMIN_EXISTS=$(python3 -c "
import pymysql, os
try:
    conn = pymysql.connect(host='${DB_HOST}', port=${DB_PORT},
        user='${MYSQL_USER:-root}', password='${MYSQL_ROOT_PASSWORD:-root}',
        database='${MYSQL_DATABASE:-sample_platform}')
    cursor = conn.cursor()
    cursor.execute(\"SELECT COUNT(*) FROM user WHERE role = 'admin'\")
    result = cursor.fetchone()
    conn.close()
    print('yes' if result and result[0] > 0 else 'no')
except Exception:
    print('no')
" 2>/dev/null)

if [[ -f "install/init_db.py" ]]; then
    if [[ "$ADMIN_EXISTS" = "no" ]]; then
        log "Creating Admin User..."

        python3 install/init_db.py \
            "$SQLALCHEMY_DATABASE_URI" \
            "${ADMIN_USERNAME:-admin}" \
            "${ADMIN_EMAIL:-admin@example.com}" \
            "${ADMIN_PASSWORD:-admin}" || log "Admin creation skipped (may already exist)"

        if [[ "$INSTALL_SAMPLE_DATA" = "true" ]] && [[ -f "install/sample_db.py" ]]; then
            log "Populating sample data..."
            python3 install/sample_db.py "$SQLALCHEMY_DATABASE_URI" || log "Sample data population skipped"
        fi
    else
        log "Admin user already exists — skipping initialization"
    fi
else
    log "WARNING: install/init_db.py not found — skipping admin user creation"
fi

# --- 10. Start Server ---
chown -R appuser:appuser /app 2>/dev/null || true

log "Starting Gunicorn on 0.0.0.0:5000 as appuser..."
log "Application accessible at http://localhost:${APP_PORT:-5000}"

exec gosu appuser gunicorn \
    --workers 4 \
    --bind 0.0.0.0:5000 \
    --timeout 120 \
    --access-logfile - \
    --error-logfile - \
    --log-level info \
    run:app