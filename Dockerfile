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

# 3. Upgrade Pip & Build Tools
RUN pip install --upgrade pip wheel setuptools

# 4. Install heavy C-extension packages first (Caching Layer)
RUN pip install --no-cache-dir mysqlclient lxml cryptography

# 5. Install Project Dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir --default-timeout=100 -r requirements.txt

# 6. Install gunicorn
RUN pip install --no-cache-dir gunicorn

# 7. Copy Application Code
COPY . .

# 8. Create logs directory (the only build-time prep needed)
RUN mkdir -p logs

# 9. Setup Entrypoint Script
COPY docker-entrypoint.sh /usr/local/bin/
RUN sed -i 's/\r$//' /usr/local/bin/docker-entrypoint.sh && \
    chmod +x /usr/local/bin/docker-entrypoint.sh

# 10. Expose the Flask Port
EXPOSE 5000

# 11. Define the runtime command
ENTRYPOINT ["docker-entrypoint.sh"]