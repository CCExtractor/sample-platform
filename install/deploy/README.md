# Deployment Scripts

These scripts implement safe, automated deployment with automatic rollback on failure.

## Overview

```
┌─────────────────────────────────────────────────────────────┐
│                    DEPLOYMENT FLOW                          │
├─────────────────────────────────────────────────────────────┤
│  pre_deploy.sh  →  deploy.sh  →  post_deploy.sh            │
│       ↓               ↓              ↓                      │
│  Validate env    Update code    Health check                │
│  Save state      Run migrations  Verify app                 │
│       ↓               ↓              ↓                      │
│                                 ┌────┴────┐                 │
│                                 ↓         ↓                 │
│                              SUCCESS   FAILURE              │
│                                 ↓         ↓                 │
│                               Done    rollback.sh           │
└─────────────────────────────────────────────────────────────┘
```

## Scripts

### pre_deploy.sh
Validates the environment before deployment:
- Checks for concurrent deployments (lock file)
- Verifies install folder and config.py exist
- Tests database connection
- Saves current commit and migration version for rollback
- Checks disk space

### deploy.sh
Performs the actual deployment:
- Fetches and updates code from git
- Installs/updates Python dependencies
- Runs database migrations
- Copies CI scripts to test data directory
- Reloads the platform service

### post_deploy.sh
Verifies deployment was successful:
- Waits for application to start
- Checks `/health` endpoint (with fallback to `/`)
- Retries up to 6 times with 5-second delay
- Returns success (0) or failure (1)

### rollback.sh
Restores previous working state:
- Restores previous git commit
- Downgrades database migrations if needed
- Reinstalls dependencies
- Reloads service
- Verifies rollback was successful

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `INSTALL_FOLDER` | `/var/www/sample-platform` | Application directory |
| `SAMPLE_REPOSITORY` | `/repository` | Test data repository |
| `DEPLOY_BRANCH` | `master` | Git branch to deploy |
| `HEALTH_URL` | `http://127.0.0.1/health` | Health check endpoint |
| `FALLBACK_URL` | `http://127.0.0.1/` | Fallback check URL |
| `MAX_RETRIES` | `6` | Health check retry count |
| `RETRY_DELAY` | `5` | Seconds between retries |

## Manual Usage

```bash
# Set environment
export INSTALL_FOLDER="/var/www/sample-platform"
export SAMPLE_REPOSITORY="/repository"

# Run deployment
cd $INSTALL_FOLDER
sudo bash install/deploy/pre_deploy.sh && \
sudo bash install/deploy/deploy.sh && \
sudo bash install/deploy/post_deploy.sh || \
sudo bash install/deploy/rollback.sh
```

## GitHub Actions Integration

These scripts are designed to be called from the GitHub Actions workflow:

```yaml
- name: Pre-deployment checks
  run: sudo bash install/deploy/pre_deploy.sh

- name: Deploy
  run: sudo bash install/deploy/deploy.sh

- name: Verify deployment
  run: sudo bash install/deploy/post_deploy.sh

- name: Rollback on failure
  if: failure()
  run: sudo bash install/deploy/rollback.sh
```

## Files Created During Deployment

| File | Purpose |
|------|---------|
| `/tmp/sp-deploy.lock` | Prevents concurrent deployments |
| `/tmp/sp-deploy-backup-dir.txt` | Points to backup directory |
| `/tmp/sp-deploy-YYYYMMDD-HHMMSS/` | Backup directory with rollback info |
| `/tmp/health_response.json` | Last health check response |

## Troubleshooting

### Deployment stuck
Check for stale lock file:
```bash
ls -la /tmp/sp-deploy.lock
rm /tmp/sp-deploy.lock  # If stale (>10 minutes old)
```

### Health check failing
```bash
# Check application logs
tail -f /var/www/sample-platform/logs/error.log

# Check service status
systemctl status platform

# Test health endpoint manually
curl -v http://127.0.0.1/health
```

### Rollback failed
```bash
# Check current state
cd /var/www/sample-platform
git log --oneline -5
FLASK_APP=./run.py flask db current

# Manual rollback
git checkout <previous-commit>
FLASK_APP=./run.py flask db downgrade <migration-id>
systemctl restart platform
```
