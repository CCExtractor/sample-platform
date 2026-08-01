FROM python:3.12-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    FLASK_APP=run.py

# git for the build commit run.py reads, libmagic for upload sniffing,
# mediainfo for sample metadata. No compiler: everything has a wheel.
RUN apt-get update && apt-get install -y --no-install-recommends \
        git libmagic1 mediainfo \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Dependencies first so application edits don't invalidate this layer.
# Pinned, and wheels only, so nothing runs a setup script during the build.
# cryptography is used by the credential generator further down.
COPY requirements.txt .
RUN pip install --only-binary :all: --upgrade \
        pip==26.2 setuptools==83.0.0 wheel==0.47.0 \
    && pip install --only-binary :all: \
        cryptography==50.0.0 gunicorn==26.0.0 \
    && pip install --only-binary :all: -r requirements.txt

# Listed by name instead of "COPY . ." so a secret_key, config.py or
# service-account.json left in a working tree can't end up in the image.
COPY run.py config_parser.py database.py decorators.py exceptions.py \
     log_configuration.py mailer.py utility.py ./
COPY mod_api/ ./mod_api/
COPY mod_auth/ ./mod_auth/
COPY mod_ci/ ./mod_ci/
COPY mod_customized/ ./mod_customized/
COPY mod_health/ ./mod_health/
COPY mod_home/ ./mod_home/
COPY mod_regression/ ./mod_regression/
COPY mod_sample/ ./mod_sample/
COPY mod_test/ ./mod_test/
COPY mod_upload/ ./mod_upload/
COPY install/ ./install/
COPY migrations/ ./migrations/
COPY static/ ./static/
COPY templates/ ./templates/

# The app reads its settings from config.py; this variant takes them from
# the environment.
COPY config.docker.py config.py

# Done once here instead of on every start: unprivileged user, secret keys,
# throwaway GCP credentials, the repository tree (named volumes inherit this
# layout on first mount) and a git repo so run.py can resolve a commit.
RUN useradd --create-home --uid 1001 appuser \
    && python install/generate_dev_credentials.py \
    && head -c 32 /dev/urandom > secret_key \
    && head -c 32 /dev/urandom > secret_csrf \
    && mkdir -p logs \
        /repository/ci-tests /repository/unsafe-ccextractor /repository/TempFiles \
        /repository/LogFiles /repository/TestResults /repository/TestFiles/media \
        /repository/QueuedFiles /repository/TestData/ci-linux \
        /repository/TestData/ci-windows /repository/vm_data \
    && git init -q . \
    && git -c user.email=dev@local -c user.name=docker add -A \
    && git -c user.email=dev@local -c user.name=docker commit -qm "container image" \
    && chown -R appuser:appuser /app /repository

COPY docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh
RUN sed -i 's/\r$//' /usr/local/bin/docker-entrypoint.sh \
    && chmod +x /usr/local/bin/docker-entrypoint.sh

USER appuser
EXPOSE 5000
ENTRYPOINT ["docker-entrypoint.sh"]
