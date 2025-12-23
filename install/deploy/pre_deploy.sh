#!/bin/bash
# Pre-deployment checks - run before any deployment actions
# Exit codes: 0 = success, 1 = failure
#
# This script validates the environment before deployment and stores
# information needed for potential rollback.

set -e

INSTALL_FOLDER="${INSTALL_FOLDER:-/var/www/sample-platform}"
BACKUP_DIR="/tmp/sp-deploy-$(date +%Y%m%d-%H%M%S)"
LOCK_FILE="/tmp/sp-deploy.lock"

echo "=== Pre-deployment checks ==="
echo "Timestamp: $(date -Iseconds)"

# Check for concurrent deployments
if [ -f "$LOCK_FILE" ]; then
    LOCK_AGE=$(($(date +%s) - $(stat -c %Y "$LOCK_FILE" 2>/dev/null || echo 0)))
    if [ "$LOCK_AGE" -lt 600 ]; then  # 10 minute lock
        echo "ERROR: Deployment already in progress (lock age: ${LOCK_AGE}s)"
        echo "If this is stale, remove: $LOCK_FILE"
        exit 1
    fi
    echo "WARNING: Stale lock file found (age: ${LOCK_AGE}s), removing..."
    rm -f "$LOCK_FILE"
fi

# Create lock file
echo "$$" > "$LOCK_FILE"
trap 'rm -f "$LOCK_FILE"' EXIT

# Create backup directory
mkdir -p "$BACKUP_DIR"
echo "Backup directory: $BACKUP_DIR"

# Check 1: Verify we're in the right directory
if [ ! -f "$INSTALL_FOLDER/run.py" ]; then
    echo "ERROR: run.py not found in $INSTALL_FOLDER"
    exit 1
fi
echo "✓ Install folder verified: $INSTALL_FOLDER"

cd "$INSTALL_FOLDER"

# Check 2: Verify config.py exists
if [ ! -f "$INSTALL_FOLDER/config.py" ]; then
    echo "ERROR: config.py not found"
    exit 1
fi
echo "✓ config.py exists"

# Check 3: Test database connection
echo "Testing database connection..."
python3 -c "
import sys
sys.path.insert(0, '$INSTALL_FOLDER')
try:
    from config_parser import parse_config
    config = parse_config('config')
    from sqlalchemy import create_engine
    engine = create_engine(config['DATABASE_URI'])
    conn = engine.connect()
    conn.execute('SELECT 1')
    conn.close()
    print('Database connection OK')
except Exception as e:
    print(f'Database connection FAILED: {e}')
    sys.exit(1)
" || {
    echo "ERROR: Database connection failed"
    exit 1
}
echo "✓ Database connection OK"

# Check 4: Store current state for rollback
CURRENT_COMMIT=$(git rev-parse HEAD)
echo "$CURRENT_COMMIT" > "$BACKUP_DIR/previous_commit.txt"
echo "✓ Current commit saved: $CURRENT_COMMIT"

# Check 5: Store current migration version
FLASK_APP=./run.py python3 -m flask db current 2>/dev/null > "$BACKUP_DIR/previous_migration.txt" || true
if [ -s "$BACKUP_DIR/previous_migration.txt" ]; then
    echo "✓ Migration version saved: $(cat $BACKUP_DIR/previous_migration.txt | head -1)"
else
    echo "✓ Migration version saved: (none or could not determine)"
fi

# Check 6: Check disk space (need at least 500MB free)
FREE_SPACE_KB=$(df -k "$INSTALL_FOLDER" | tail -1 | awk '{print $4}')
FREE_SPACE_MB=$((FREE_SPACE_KB / 1024))
if [ "$FREE_SPACE_MB" -lt 500 ]; then
    echo "ERROR: Less than 500MB free disk space (${FREE_SPACE_MB}MB available)"
    exit 1
fi
echo "✓ Disk space OK (${FREE_SPACE_MB}MB free)"

# Check 7: Verify git repository is clean (no uncommitted changes)
if ! git diff --quiet 2>/dev/null; then
    echo "WARNING: Uncommitted changes detected in repository"
    git status --short
fi

# Export backup directory for other scripts
echo "$BACKUP_DIR" > /tmp/sp-deploy-backup-dir.txt

echo ""
echo "=== Pre-deployment checks PASSED ==="
echo "Backup directory: $BACKUP_DIR"
exit 0
