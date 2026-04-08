# 🐳 Sample Platform — Docker Setup Guide

> One-command local development environment for the CCExtractor Sample Platform.

---

## Table of Contents

- [Prerequisites](#prerequisites)
- [Quick Start](#quick-start)
- [Architecture](#architecture)
- [Configuration](#configuration)
  - [Environment Variables Reference](#environment-variables-reference)
  - [Google Cloud Storage](#google-cloud-storage)
  - [GitHub Integration](#github-integration)
- [Usage](#usage)
  - [Starting the Platform](#starting-the-platform)
  - [Stopping the Platform](#stopping-the-platform)
  - [Viewing Logs](#viewing-logs)
  - [Live Code Reloading (Development)](#live-code-reloading-development)
  - [Full Reset (Clean Slate)](#full-reset-clean-slate)
- [Database](#database)
  - [Connecting Directly](#connecting-directly)
  - [Migrations](#migrations)
  - [Re-seeding](#re-seeding)
- [Design Decisions](#design-decisions)
- [Troubleshooting](#troubleshooting)
- [File Overview](#file-overview)

---

## Prerequisites

| Tool               | Minimum Version | Check Command            |
| ------------------ | --------------- | ------------------------ |
| **Docker Engine**  | 20.10+          | `docker --version`       |
| **Docker Compose** | 2.0+ (V2)      | `docker compose version` |

> **Windows / macOS**: Install [Docker Desktop](https://www.docker.com/products/docker-desktop/) — it bundles both.
>
> **Linux**: Install Docker Engine + the Compose plugin via [the official docs](https://docs.docker.com/engine/install/).

---

## Quick Start

```bash
# 1. Clone the repository (if you haven't already)
git clone https://github.com/CCExtractor/sample-platform.git
cd sample-platform

# 2. Create your environment file from the template
cp env.example .env
#    → Edit .env with your own values (see Configuration below)

# 3. (Optional) Place your GCP service-account key
#    If you don't have one, the app will still start but GCS features won't work.
#    See "Google Cloud Storage" section below.

# 4. Build and start everything
docker compose up -d --build

# 5. Wait ~20 seconds for MySQL to initialize, then open:
#    http://localhost:5000
```

**Default admin credentials** (set in `.env`):

| Field    | Value               |
| -------- | ------------------- |
| Email    | `admin@example.com` |
| Password | `admin`             |

---

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    Docker Network                       │
│                 sample_platform_network                 │
│                                                         │
│  ┌──────────────┐           ┌─────────────────────────┐ │
│  │   MySQL 8.0  │◄──────── │  Flask Backend (Py 3.11) │ │
│  │              │  :3306    │                         │ │
│  │  db_data vol │           │  Gunicorn (4 workers)   │ │
│  └──────────────┘           │  :5000                  │ │
│                             │                         │ │
│                             │  .:/app (live mount)    │ │
│                             │  repository_data vol    │ │
│                             └─────────────────────────┘ │
│                                      │                  │
└──────────────────────────────────────│──────────────────┘
                                       │
                                Host :5000
                           http://localhost:5000
```

| Service     | Container Name            | Image                   | Exposed Port |
| ----------- | ------------------------- | ----------------------- | ------------ |
| **db**      | `sample_platform_db`      | `mysql:8.0`             | `3306`       |
| **backend** | `sample_platform_backend` | Built from `Dockerfile` | `5000`       |

---

## Configuration

All configuration is driven by the **`.env`** file. Docker Compose reads it via `env_file:`.

> **Single source of truth**: The `.env` file is the only place you set values. There is no
> duplicate `environment:` block in `docker-compose.yml` — this avoids the common problem of
> environment overriding env_file silently.

### Environment Variables Reference

#### MySQL

| Variable               | Description                                      | Default            |
| ---------------------- | ------------------------------------------------ | ------------------ |
| `MYSQL_ROOT_PASSWORD`  | MySQL root password                              | `root`             |
| `MYSQL_USER`           | Application-level DB user (auto-created by MySQL)| `sample_platform`  |
| `MYSQL_PASSWORD`       | Password for the application DB user             | `sample_platform`  |
| `MYSQL_DATABASE`       | Database name                                    | `sample_platform`  |

> MySQL auto-creates `MYSQL_USER` with full grants on `MYSQL_DATABASE`. The root user
> is only used for the healthcheck and initial bootstrap — the application connects as
> the dedicated user.

#### Database URI

| Variable                   | Description                              | Default |
| -------------------------- | ---------------------------------------- | ------- |
| `SQLALCHEMY_DATABASE_URI`  | Full SQLAlchemy connection string         | *(see env.example)* |

> Must be kept consistent with the MySQL variables above. Format:
> `mysql+pymysql://<MYSQL_USER>:<MYSQL_PASSWORD>@db/<MYSQL_DATABASE>?charset=utf8mb4`

#### Networking

| Variable           | Description                       | Default |
| ------------------ | --------------------------------- | ------- |
| `APP_PORT`         | Host port for the Flask app       | `5000`  |
| `DB_EXTERNAL_PORT` | Host port for direct MySQL access | `3306`  |

#### Security

| Variable     | Description                                          | Default                   |
| ------------ | ---------------------------------------------------- | ------------------------- |
| `SECRET_KEY` | Flask session secret (fallback; file overrides it)   | `change-me-in-production` |
| `HMAC_KEY`   | Used by `mod_auth` for email verification tokens     | `change-me-in-production` |

> **How secret keys actually work**: `run.py` reads binary files `/app/secret_key` and
> `/app/secret_csrf` at startup and uses their contents as the real `SECRET_KEY` and
> `CSRF_SESSION_KEY`. These files are auto-generated by the entrypoint on first run.
> The `SECRET_KEY` env var in `.env` is only a config-level fallback used briefly
> before the file-based keys overwrite it.

⚠️ **Change `SECRET_KEY` and `HMAC_KEY`** before deploying to any shared environment.

#### Google Cloud Storage

| Variable               | Description                                      | Default               |
| ---------------------- | ------------------------------------------------ | --------------------- |
| `GCS_BUCKET_NAME`      | GCS bucket for sample file storage               | `sample-platform-dev` |
| `SERVICE_ACCOUNT_FILE` | Filename of the GCP key (relative to project root)| `service-account.json`|

> ⚠️ **Must be non-empty**: `run.py` calls `client.bucket(name)` at import time. Use your real bucket name or
> keep the default placeholder.

#### GitHub

| Variable            | Description                        | Default       |
| ------------------- | ---------------------------------- | ------------- |
| `GITHUB_TOKEN`      | Personal access token for API      | *(empty)*     |
| `GITHUB_OWNER`      | GitHub org/user owning the repo    | `CCExtractor` |
| `GITHUB_REPOSITORY` | Repository name                    | `ccextractor` |

#### Admin Bootstrap

| Variable         | Description                         | Default             |
| ---------------- | ----------------------------------- | ------------------- |
| `ADMIN_USERNAME` | Username for auto-created admin     | `admin`             |
| `ADMIN_EMAIL`    | Email for auto-created admin        | `admin@example.com` |
| `ADMIN_PASSWORD` | Password for auto-created admin     | `admin`             |

#### Email (Mailgun)

| Variable        | Description            | Default   |
| --------------- | ---------------------- | --------- |
| `EMAIL_DOMAIN`  | Mailgun sending domain | *(empty)* |
| `EMAIL_API_KEY` | Mailgun API key        | *(empty)* |

#### Feature Flags

| Variable              | Description                                       | Default       |
| --------------------- | ------------------------------------------------- | ------------- |
| `INSTALL_SAMPLE_DATA` | Seed DB with sample categories & regression tests | `false`       |
| `MAINTENANCE`         | Enable maintenance mode                           | `false`       |
| `FLASK_ENV`           | Flask environment (`development` / `production`)  | `development` |

---

### Google Cloud Storage

The platform uses GCS to store sample files. To enable this:

1. Create a GCP service account with **Storage Object Admin** permissions.
2. Download the JSON key file.
3. Save it as `./service-account.json` in the project root.
4. Set `GCS_BUCKET_NAME` in your `.env`.

**Mounting Strategy**:
- **Enabled**: If `GCS_BUCKET_NAME` is set, the container mounts the bucket to `/mnt/gcs_repository` and updates `SAMPLE_REPOSITORY` to point there. This ensures the GCS mount doesn't conflict with your local code volume.
- **Disabled**: If not set, `SAMPLE_REPOSITORY` defaults to `/repository`, which is a standard Docker volume persisting data to your local machine.

---

### GitHub Integration

GitHub features (CI webhooks, PR testing) require a **Personal Access Token** with `public_repo` scope:

1. Generate a token at [github.com/settings/tokens](https://github.com/settings/tokens).
2. Set `GITHUB_TOKEN` in your `.env`.

---

## Usage

### Starting the Platform

```bash
docker compose up -d --build
```

- `-d` runs in detached mode (background).
- `--build` rebuilds the image if `Dockerfile` or `requirements.txt` changed.

**Startup sequence** (handled by `docker-entrypoint.sh`):

1. MySQL starts and becomes healthy (~10 s).
2. Backend container starts and the entrypoint:
   1. **Generates secret key files** (`/app/secret_key`, `/app/secret_csrf`) if they don't exist.
   2. **Initializes a git repo** at `/app` (required by GitPython for build-commit display).
   3. **Creates directories** mirroring `install/install.sh` (including `TempFiles/`, `TestFiles/media/`, `TestData/ci-linux/`, `TestData/ci-windows/`, etc.).
   4. **Copies sample files** (`sample1.ts`, `sample2.ts`) to `TestFiles/` and CI scripts to `TestData/`.
   5. **Waits for MySQL** to accept connections.
   6. **Runs database migrations** (stamps HEAD on fresh databases to avoid conflicts).
   7. **Creates the admin user** if no admin exists in the DB (checked via SQL query).
   8. **Seeds sample data** if `INSTALL_SAMPLE_DATA=true` and no admin existed.
   9. **Starts Gunicorn** on port 5000.

### Stopping the Platform

```bash
docker compose down
```

> Data is persisted in Docker volumes (`db_data`, `repository_data`), so nothing is lost.

### Viewing Logs

```bash
# All services
docker compose logs -f

# Backend only
docker logs -f sample_platform_backend

# MySQL only
docker logs -f sample_platform_db
```

### Live Code Reloading (Development)

The project root is mounted into the container at `/app`, so **any code change on your host
is immediately visible inside the container**. However, Gunicorn doesn't auto-reload by default.

To pick up changes without rebuilding:

```bash
# Restart just the backend (fast, no rebuild)
docker compose restart backend
```

If you changed `requirements.txt` or `Dockerfile`, you need a full rebuild:

```bash
docker compose up -d --build
```

### Full Reset (Clean Slate)

```bash
# Remove containers AND volumes (wipes DB + repository data + secret keys)
docker compose down -v

# Rebuild from scratch
docker compose up -d --build
```

---

## Database

### Connecting Directly

From your host, using the application user:

```bash
mysql -h 127.0.0.1 -P 3306 -u sample_platform -psample_platform sample_platform
```

Or via Docker:

```bash
docker exec -it sample_platform_db mysql -u sample_platform -psample_platform sample_platform
```

### Migrations

The entrypoint handles migrations automatically. To run them manually:

```bash
# Generate a new migration
docker exec -it sample_platform_backend flask db migrate -m "Description"

# Apply pending migrations
docker exec -it sample_platform_backend flask db upgrade

# View migration history
docker exec -it sample_platform_backend flask db history

# Check current migration state
docker exec -it sample_platform_backend flask db current
```

### Re-seeding

The entrypoint checks the database directly for an existing admin user — there is no
file-based sentinel. To re-seed from scratch:

```bash
# Full reset — wipes the DB volume and restarts
docker compose down -v
docker compose up -d --build
```

Or to re-seed without wiping:

```bash
# Delete the admin user, then restart
docker exec sample_platform_db mysql -u root -proot sample_platform -e "DELETE FROM user;"
docker compose restart backend
```

---

## Design Decisions

### Why mount GCS to `/mnt/gcs_repository`?

We previously mounted GCS directly to `/repository`. However, `docker-compose.yml` mounts a local volume to `/repository` for persistence. GCS FUSE requires an empty directory (or specific flags) and mounting it *over* a Docker volume hides the volume's contents and causes "non-empty directory" errors.

**Solution**: We mount GCS to a dedicated, clean path (`/mnt/gcs_repository`) and export `SAMPLE_REPOSITORY` to point to it. The application respects this variable, seamlessly switching between local storage and Cloud Storage without code changes.

### Why are secret keys generated at runtime, not in the Dockerfile?

`run.py` reads two binary files (`secret_key`, `secret_csrf`) to set Flask's `SECRET_KEY` and
`CSRF_SESSION_KEY`. We generate these files in the **entrypoint** (runtime) rather than the
**Dockerfile** (build time) because:

- **Security**: Build-time files are baked into image layers and visible via `docker history`.
- **Uniqueness**: Each container gets its own keys instead of sharing from a single image.
- **Dev compatibility**: The `.:/app` volume mount would overwrite build-time files anyway.

### Why does the container need a git repo?

`run.py` line 69-70 uses GitPython to read `repo.head.object.hexsha` for build-commit display
in the UI. It crashes at import time if no `.git` directory exists. The `.dockerignore` (correctly)
excludes `.git`, so the entrypoint creates a minimal repo at runtime.

### Why use `flask db stamp head` instead of `flask db upgrade`?

On a fresh database, `create_all()` (called by the application startup or `init_db.py`) builds the full schema. If we were to run `flask db upgrade` instead, it might try to create tables but could conflict with `create_all` logic or require a linear migration history that matches the current models exactly. Instead, we let `create_all` or the application manage table creation, and stamp the database as "already at HEAD" so Alembic knows the schema is current.

### Why a dedicated MySQL user?

MySQL's `MYSQL_USER` + `MYSQL_PASSWORD` env vars auto-create a user with grants only on
`MYSQL_DATABASE`. The root user is used only for the healthcheck probe. This follows the
principle of least privilege.

### Why `env_file` without a duplicate `environment:` block?

Docker Compose's `environment:` section **overrides** `env_file` for any duplicate keys.
Having both is confusing — you think you're editing `.env` but the compose file silently
overrides your changes. Using `env_file` alone keeps `.env` as the single source of truth.

---

## Troubleshooting

### Container exits immediately

```bash
docker logs sample_platform_backend
```

| Symptom                                   | Cause & Fix                                                                    |
| ----------------------------------------- | ------------------------------------------------------------------------------ |
| `SecretKeyInstallationException`           | `/app/secret_key` or `/app/secret_csrf` missing. Entrypoint should create them. Rebuild image. |
| `git.exc.InvalidGitRepositoryError`        | `.git` directory missing. Entrypoint should init one. Rebuild image.           |
| `No module named 'config'`                 | `config.py` not in build context. Check `.dockerignore`.                       |
| `MySQL connection timeout`                 | MySQL isn't ready. Increase `retries` in healthcheck or `sleep` in entrypoint. |
| `ModuleNotFoundError: No module named 'X'` | Missing pip dependency. Add to `requirements.txt` and rebuild.                 |
| `OperationalError: (1045, "Access denied")`| `SQLALCHEMY_DATABASE_URI` user/password doesn't match `MYSQL_USER`/`MYSQL_PASSWORD` in `.env`. |

### Port conflict

If port 5000 or 3306 is already in use, change in `.env`:

```env
APP_PORT=8080
DB_EXTERNAL_PORT=3307
```

### Database migration errors on fresh DB

The entrypoint stamps the database at HEAD on first run to avoid conflicts between
`create_all()` and Alembic. If you still see errors, do a full reset:

```bash
docker compose down -v
docker compose up -d --build
```

### Windows line-ending issues

If you see `/bin/bash^M: bad interpreter`, the entrypoint has Windows-style line endings. The
Dockerfile runs `sed -i 's/\r$//'` to fix this automatically. If you've volume-mounted and
edited the file on Windows, convert manually:

```bash
# Git Bash
sed -i 's/\r$//' docker-entrypoint.sh

# Or configure git globally
git config core.autocrlf input
```

---

## File Overview

```
.
├── .dockerignore          # Files excluded from Docker build context
├── .env                   # Your local config (git-ignored, single source of truth)
├── Dockerfile             # Image: Python 3.11 + system deps + pip install
├── DOCKER.md              # ← You are here
├── docker-compose.yml     # Orchestration (db + backend), reads .env
├── docker-entrypoint.sh   # Runtime: secrets → git → dirs → DB wait → migrate → gunicorn
├── env.example            # Template for .env (committed to git)
├── config.py              # Flask config (reads env vars, no hardcoded project values)
├── utility.py             # Helper functions (GCS download fallback, etc.)
├── requirements.txt       # Python dependencies
├── run.py                 # Flask application entry point
└── service-account.json   # GCP key (If missing, Docker might create a directory here; entrypoint handles this)
```
