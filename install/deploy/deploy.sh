#!/bin/bash
# Main deployment script
# Exit codes: 0 = success, 1 = failure (triggers rollback)
#
# This script performs the actual deployment steps:
# 1. Pull latest code from git
# 2. Install/update Python dependencies
# 3. Run database migrations
# 4. Copy CI scripts
# 5. Reload the application service

set -e

INSTALL_FOLDER="${INSTALL_FOLDER:-/var/www/sample-platform}"
SAMPLE_REPOSITORY="${SAMPLE_REPOSITORY:-/repository}"
DEPLOY_BRANCH="${DEPLOY_BRANCH:-master}"

echo "=== Starting deployment ==="
echo "Timestamp: $(date -Iseconds)"
echo "Branch: $DEPLOY_BRANCH"
echo "Install folder: $INSTALL_FOLDER"

cd "$INSTALL_FOLDER"

# Step 1: Fetch latest code
echo ""
echo "--- Step 1: Fetching latest code ---"
git fetch origin "$DEPLOY_BRANCH"
echo "✓ Fetched latest from origin/$DEPLOY_BRANCH"

# Step 2: Check for local changes and handle them
if ! git diff --quiet; then
    echo "WARNING: Local changes detected, stashing..."
    git stash push -m "pre-deploy-$(date +%Y%m%d-%H%M%S)" || true
fi

# Step 3: Update to latest code
echo ""
echo "--- Step 2: Updating code ---"
git checkout "$DEPLOY_BRANCH"
git reset --hard "origin/$DEPLOY_BRANCH"
NEW_COMMIT=$(git rev-parse HEAD)
echo "✓ Updated to commit: $NEW_COMMIT"

# Step 4: Update dependencies
echo ""
echo "--- Step 3: Updating dependencies ---"
python3 -m pip install -r requirements.txt --quiet --disable-pip-version-check
echo "✓ Dependencies updated"

# Step 5: Run database migrations
echo ""
echo "--- Step 4: Running database migrations ---"
FLASK_APP=./run.py python3 -m flask db upgrade
echo "✓ Database migrations complete"

# Step 6: Copy CI scripts (if directories exist)
echo ""
echo "--- Step 5: Updating CI scripts ---"
if [ -d "${SAMPLE_REPOSITORY}/TestData" ]; then
    if [ -f "install/ci-vm/ci-linux/ci/bootstrap" ]; then
        mkdir -p "${SAMPLE_REPOSITORY}/TestData/ci-linux"
        cp "install/ci-vm/ci-linux/ci/bootstrap" "${SAMPLE_REPOSITORY}/TestData/ci-linux/bootstrap"
        echo "✓ Copied ci-linux/bootstrap"
    fi
    if [ -f "install/ci-vm/ci-linux/ci/runCI" ]; then
        mkdir -p "${SAMPLE_REPOSITORY}/TestData/ci-linux"
        cp "install/ci-vm/ci-linux/ci/runCI" "${SAMPLE_REPOSITORY}/TestData/ci-linux/runCI"
        echo "✓ Copied ci-linux/runCI"
    fi
    if [ -f "install/ci-vm/ci-windows/ci/runCI.bat" ]; then
        mkdir -p "${SAMPLE_REPOSITORY}/TestData/ci-windows"
        cp "install/ci-vm/ci-windows/ci/runCI.bat" "${SAMPLE_REPOSITORY}/TestData/ci-windows/runCI.bat"
        echo "✓ Copied ci-windows/runCI.bat"
    fi
else
    echo "⚠ TestData directory not found, skipping CI script copy"
fi

# Step 7: Reload application
echo ""
echo "--- Step 6: Reloading application ---"
if systemctl is-active --quiet platform; then
    systemctl reload platform
    echo "✓ Platform service reloaded"
else
    echo "⚠ Platform service not running, attempting start..."
    systemctl start platform
    echo "✓ Platform service started"
fi

echo ""
echo "=== Deployment complete ==="
echo "Deployed commit: $NEW_COMMIT"
echo "Waiting for application to start..."
exit 0
