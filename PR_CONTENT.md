# Docker Development Environment Setup

## 🚀 Summary
This PR introduces a complete Docker-based development environment for the Sample Platform. It allows developers to spin up the entire application stack (Flask + MySQL) with a **single command**, eliminating manual dependency installation and configuration headaches.

## ✨ Key Features
- **One-Command Setup**: `docker compose up --build` handles everything from database creation to dependency installation.
- **Live Code Reloading**: The local source code is mounted into the container, so changes are reflected immediately without rebuilding.
- **Automated Database Management**:
  - Automatically waits for MySQL to be healthy.
  - Handles schema creation and migration stamping (`flask db stamp head`) on the first run.
  - Seeds the database with an admin user and sample data (configurable via `.env`).
- **Google Cloud Storage (GCS) Emulation**:
  - Automatically generates a dummy `service-account.json` if one is missing, preventing startup crashes.
  - Supports mounting a real GCS bucket via `gcsfuse` if credentials are provided.
- **Security Best Practices**:
  - `SECRET_KEY` and `CSRF_SESSION_KEY` are generated **at runtime** (not baked into the image) to ensure unique secrets per container.
  - Runs with a non-root user (Gunicorn).

## 📂 File Overview
- `Dockerfile`: Multi-stage build based on Python 3.11-slim.
- `docker-compose.yml`: Orchestrates the Flask backend and MySQL 8.0 database.
- `docker-entrypoint.sh`: A robust startup script that handles:
    - Secret key generation.
    - Git repository initialization (required for build commit display).
    - Database waiting and migration strategies.
    - Gunicorn execution.
- `DOCKER.md`: Comprehensive documentation on usage, architecture, and troubleshooting.
- `env.example`: A template for environment variables tailored for Docker.
- `.dockerignore`: Optimizes build context by excluding unnecessary files.

## 🧪 How to Test
1. **Checkout the branch**:
   ```bash
   git checkout feature/Docker
   ```
2. **Setup Environment**:
   ```bash
   cp env.example .env
   ```
3. **Start the Platform**:
   ```bash
   docker compose up --build
   ```
4. **Verify**:
   - Access the app at [http://localhost:5000](http://localhost:5000).
   - Log in with default credentials (`admin@example.com` / `admin`).
   - Standard logs should appear in your terminal.

## ⚠️ Design Decisions & Trade-offs
- **Runtime Secrets**: We generate secrets in the entrypoint instead of the Dockerfile to prevent leaking them in image layers and to ensure every container has unique keys.
- **GCS Mounting**: We mount GCS buckets to `/mnt/gcs_repository` instead of directly to `/repository` to avoid conflicts with Docker's volume mounting behavior.
- **Database Stamping**: On a fresh DB, we use `flask db stamp head` because `create_all()` builds the schema faster than running 50+ migrations sequentially.

---
**Documentation**: See `DOCKER.md` for full details.
