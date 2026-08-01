# Running the Sample Platform with Docker

A two-container development stack: MySQL 8 and the Flask application served by
Gunicorn. It gives contributors a working platform without installing MySQL,
Python, or the native libraries the app depends on.

## Prerequisites

- Docker Engine 24+ with the Compose plugin (`docker compose`).

## Quick start (empty database)

```sh
cp env.example .env          # then edit the passwords
docker compose up --build
```

On first start the database initialises, the app waits for it, builds the
schema, loads the bundled fixture set (categories, samples, regression tests)
and serves on <http://localhost:5000>. Later starts only apply migrations
newer than the database, and never re-seed.

Create an administrator so you can sign in:

```sh
docker compose exec backend \
  python install/init_db.py "$SQLALCHEMY_DATABASE_URI" admin admin@example.com admin
```

## Starting from a database dump

To develop against real data, load a `mysqldump` on the database's **first**
start by dropping it into the init directory. Create `docker-compose.override.yml`:

```yaml
services:
  db:
    volumes:
      - /absolute/path/to/dump.sql:/docker-entrypoint-initdb.d/01-dump.sql:ro
```

Then `docker compose up --build`. MySQL imports the dump before the app starts;
the app applies any migrations newer than the dump on top of it. The import
only runs while the `db_data` volume is empty — `docker compose down -v` first
to reload a different dump.

## Live reload

The image is self-contained (code is copied in, not mounted). For an
edit-refresh loop, mount the package you are working on and enable Gunicorn's
reloader in the override file:

```yaml
services:
  backend:
    environment:
      GUNICORN_RELOAD: "1"
    volumes:
      - ./mod_sample:/app/mod_sample
      - ./templates:/app/templates
```

## Common commands

| Task | Command |
|---|---|
| Start | `docker compose up --build` |
| Stop | `docker compose down` |
| Reset the database | `docker compose down -v` |
| App logs | `docker compose logs -f backend` |
| A shell in the app | `docker compose exec backend bash` |
| A MySQL shell | `docker compose exec db mysql -u root -p` |

## Notes

- The database port is not published to the host. Reach MySQL through
  `docker compose exec`, or add a `ports` mapping in an override if you need a
  local client.
- The image generates throwaway secret keys and GCP credentials at build time
  so the app can boot offline. They are not suitable for production.
- Storage falls back to the local `/repository` volume; no GCS bucket is
  required for development.
