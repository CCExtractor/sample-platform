FROM python:3.11-slim-bullseye

# Environment variables to optimize Python for Docker
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DEBIAN_FRONTEND=noninteractive \
    FLASK_APP=run.py

# 1. Install System Dependencies
RUN apt-get update && apt-get install -y \
    build-essential \
    pkg-config \
    default-libmysqlclient-dev \
    default-mysql-client \
    libxml2-dev \
    libxslt-dev \
    libmagic1 \
    mediainfo \
    git \
    lsb-release \
    curl \
    netcat-openbsd \
    gnupg2 \
    fuse \
    && export GCSFUSE_REPO=gcsfuse-`lsb_release -c -s` \
    && echo "deb [signed-by=/usr/share/keyrings/cloud.google.asc] https://packages.cloud.google.com/apt $GCSFUSE_REPO main" | tee /etc/apt/sources.list.d/gcsfuse.list \
    && curl https://packages.cloud.google.com/apt/doc/apt-key.gpg | tee /usr/share/keyrings/cloud.google.asc \
    && apt-get update \
    && apt-get install -y gcsfuse \
    && rm -rf /var/lib/apt/lists/*

# 2. Setup Workspace
WORKDIR /app

# 3. Install all Python dependencies in a single layer
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip wheel setuptools && \
    pip install --no-cache-dir mysqlclient lxml cryptography && \
    pip install --no-cache-dir --default-timeout=100 -r requirements.txt && \
    pip install --no-cache-dir gunicorn

# 4. Copy Application Code 
COPY run.py manage.py config.py config_parser.py config_sample.py database.py \
    decorators.py exceptions.py log_configuration.py mailer.py utility.py \
    bootstrap_gunicorn.py ./
COPY mod_auth/ mod_auth/
COPY mod_ci/ mod_ci/
COPY mod_customized/ mod_customized/
COPY mod_health/ mod_health/
COPY mod_home/ mod_home/
COPY mod_regression/ mod_regression/
COPY mod_sample/ mod_sample/
COPY mod_test/ mod_test/
COPY mod_upload/ mod_upload/
COPY templates/ templates/
COPY static/ static/
COPY install/ install/
COPY migrations/ migrations/
COPY tests/ tests/

# 5. Create logs directory & setup entrypoint
COPY docker-entrypoint.sh /usr/local/bin/
RUN mkdir -p logs && \
    sed -i 's/\r$//' /usr/local/bin/docker-entrypoint.sh && \
    chmod +x /usr/local/bin/docker-entrypoint.sh

# 6. Create a non-root user for running the application server
RUN apt-get update && apt-get install -y --no-install-recommends gosu && \
    rm -rf /var/lib/apt/lists/* && \
    groupadd --gid 1001 appuser && \
    useradd --uid 1001 --gid appuser --shell /bin/bash --create-home appuser && \
    chown -R appuser:appuser /app

# 7. Expose the Flask Port
EXPOSE 5000

# 8. Define the runtime command
ENTRYPOINT ["docker-entrypoint.sh"]