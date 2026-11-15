# Devil-AI-OS backend — container image for hosted deployment (Vercel, Render, etc.)
#
# The application is a Python/FastAPI backend (no frontend). This image runs
# uvicorn on 0.0.0.0 so a platform proxy can reach it. Hosted mode is enabled
# via AUTONOMUS_HOSTED=true (see backend/app/core/config.py); the loopback-only
# default is preserved for local runs.

FROM python:3.11-slim

# A recognisable, non-root runtime. The app binds a port and talks to an
# external database; it needs no elevated privileges.
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Install dependencies first so this layer is cached independently of the
# application code.
COPY backend/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

# Copy the application. The backend package lives under backend/ and is run
# from there (the app expects `app.main:app` on the module path).
COPY backend /app/backend
WORKDIR /app/backend

# Runtime state (SQLite data, logs, backups) lives under /app/backend. On a
# serverless host these are ephemeral; with an external DATABASE_URL the SQLite
# path is unused. The directory is created so local-mode runs still work.
RUN mkdir -p /app/backend/data /app/backend/logs /app/backend/backups

# Hosted mode: bind all interfaces so the platform proxy can reach the API.
# AUTONOMUS_HOSTED=true is the approved opt-in for a hosted deployment; the
# host/port and database URL are supplied through the platform's environment.
ENV AUTONOMUS_HOSTED=true \
    AUTONOMUS_HOST=0.0.0.0 \
    AUTONOMUS_PORT=8000

EXPOSE 8000

# Run uvicorn directly. The CLI's `serve` writes a pid file under data/ and
# does the same; running uvicorn directly avoids the interactive CLI and is the
# standard container entrypoint. Migrations run on startup by default
# (AUTONOMUS_RUN_MIGRATIONS_ON_STARTUP=true), which is the right default for a
# single-instance container; turn it off and apply deliberately for a multi-
# instance serverless deploy.
CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
