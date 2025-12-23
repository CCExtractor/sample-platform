#!/bin/bash
# Rollback script - restore previous working state
# Called automatically when post_deploy.sh fails
#
# This script attempts to restore the previous state:
# 1. Restore previous git commit
# 2. Downgrade database migrations (if applicable)
# 3. Reinstall previous dependencies
# 4. Reload application
# 5. Verify rollback was successful

set -e

INSTALL_FOLDER="${INSTALL_FOLDER:-/var/www/sample-platform}"
BACKUP_DIR_FILE="/tmp/sp-deploy-backup-dir.txt"

echo "=== ROLLBACK INITIATED ==="
echo "Timestamp: $(date -Iseconds)"
echo ""

# Get backup directory
if [ -f "$BACKUP_DIR_FILE" ]; then
    BACKUP_DIR=$(cat "$BACKUP_DIR_FILE")
    echo "Backup directory: $BACKUP_DIR"
else
    echo "ERROR: Backup directory file not found: $BACKUP_DIR_FILE"
    echo "Cannot determine previous state for rollback"
    echo "MANUAL INTERVENTION REQUIRED"
    exit 1
fi

cd "$INSTALL_FOLDER"

# Step 1: Get previous commit
echo ""
echo "--- Step 1: Restoring previous code ---"
if [ -f "$BACKUP_DIR/previous_commit.txt" ]; then
    PREVIOUS_COMMIT=$(cat "$BACKUP_DIR/previous_commit.txt")
    echo "Rolling back to commit: $PREVIOUS_COMMIT"

    git fetch origin
    git checkout "$PREVIOUS_COMMIT"
    echo "✓ Code rolled back to $PREVIOUS_COMMIT"
else
    echo "WARNING: No previous commit recorded"
    echo "Attempting to use git reflog..."
    PREVIOUS_COMMIT=$(git reflog | head -2 | tail -1 | awk '{print $1}')
    if [ -n "$PREVIOUS_COMMIT" ]; then
        git checkout "$PREVIOUS_COMMIT"
        echo "✓ Code rolled back to $PREVIOUS_COMMIT (from reflog)"
    else
        echo "ERROR: Could not determine previous commit"
        echo "MANUAL INTERVENTION REQUIRED"
        exit 1
    fi
fi

# Step 2: Downgrade database migration if needed
echo ""
echo "--- Step 2: Checking database migrations ---"
if [ -f "$BACKUP_DIR/previous_migration.txt" ]; then
    PREVIOUS_MIGRATION=$(cat "$BACKUP_DIR/previous_migration.txt" | grep -oP '[a-f0-9]{12}' | head -1 || true)
    if [ -n "$PREVIOUS_MIGRATION" ]; then
        CURRENT_MIGRATION=$(FLASK_APP=./run.py python3 -m flask db current 2>/dev/null | grep -oP '[a-f0-9]{12}' | head -1 || true)
        if [ "$CURRENT_MIGRATION" != "$PREVIOUS_MIGRATION" ]; then
            echo "Rolling back database to migration: $PREVIOUS_MIGRATION"
            FLASK_APP=./run.py python3 -m flask db downgrade "$PREVIOUS_MIGRATION" || {
                echo "WARNING: Database downgrade failed"
                echo "Current migration: $CURRENT_MIGRATION"
                echo "Target migration: $PREVIOUS_MIGRATION"
                echo "May need manual database intervention"
            }
            echo "✓ Database migration rolled back"
        else
            echo "✓ Database migration unchanged (already at $PREVIOUS_MIGRATION)"
        fi
    else
        echo "✓ No specific migration version to restore"
    fi
else
    echo "✓ No previous migration info, skipping database rollback"
fi

# Step 3: Reinstall dependencies for rolled-back version
echo ""
echo "--- Step 3: Reinstalling dependencies ---"
python3 -m pip install -r requirements.txt --quiet --disable-pip-version-check
echo "✓ Dependencies reinstalled"

# Step 4: Reload application
echo ""
echo "--- Step 4: Reloading application ---"
if systemctl is-active --quiet platform; then
    systemctl reload platform
    echo "✓ Platform service reloaded"
else
    systemctl start platform || {
        echo "WARNING: Could not start platform service"
        echo "Check service status manually: systemctl status platform"
    }
fi

# Step 5: Verify rollback worked
echo ""
echo "--- Step 5: Verifying rollback ---"
sleep 3

# Try health endpoint first, fallback to root
HEALTH_URL="${HEALTH_URL:-http://127.0.0.1/health}"
FALLBACK_URL="${FALLBACK_URL:-http://127.0.0.1/}"

HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" "$HEALTH_URL" 2>/dev/null || echo "000")

if [ "$HTTP_CODE" = "200" ]; then
    echo "✓ Health check passed (HTTP $HTTP_CODE)"
    ROLLBACK_SUCCESS=true
elif [ "$HTTP_CODE" = "404" ]; then
    # Health endpoint doesn't exist, try fallback
    HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" "$FALLBACK_URL" 2>/dev/null || echo "000")
    if [ "$HTTP_CODE" -ge 200 ] && [ "$HTTP_CODE" -lt 400 ]; then
        echo "✓ Fallback check passed (HTTP $HTTP_CODE)"
        ROLLBACK_SUCCESS=true
    else
        ROLLBACK_SUCCESS=false
    fi
else
    ROLLBACK_SUCCESS=false
fi

echo ""
echo "=== ROLLBACK COMPLETE ==="
echo ""
echo "Summary:"
echo "  Restored commit: ${PREVIOUS_COMMIT:-unknown}"
echo "  Health status: HTTP $HTTP_CODE"

if [ "$ROLLBACK_SUCCESS" = true ]; then
    echo "  Result: SUCCESS"
    echo ""
    echo "Application has been rolled back to the previous version."
else
    echo "  Result: VERIFICATION FAILED"
    echo ""
    echo "WARNING: Rollback completed but application health check failed."
    echo "MANUAL INTERVENTION MAY BE REQUIRED"
    echo ""
    echo "Troubleshooting steps:"
    echo "  1. Check logs: tail -f $INSTALL_FOLDER/logs/error.log"
    echo "  2. Check service: systemctl status platform"
    echo "  3. Check nginx: tail -f /var/log/nginx/error.log"
fi

echo ""
echo "Please investigate the failed deployment before retrying."

# Clean up lock file if it exists
rm -f /tmp/sp-deploy.lock

# Exit with appropriate code
if [ "$ROLLBACK_SUCCESS" = true ]; then
    exit 0
else
    exit 1
fi
