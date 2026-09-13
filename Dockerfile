# Dockerfile
FROM python:3.12-slim AS base

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# System dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Python dependencies
COPY requirements.txt requirements-dev.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# App code
COPY . .
COPY celery_worker.py .
COPY celery_beat.py .

# Non-root user
RUN useradd -m -u 1000 appuser && chown -R appuser:appuser /app
USER appuser

EXPOSE 8000

# Development stage
FROM base AS development
RUN pip install --no-cache-dir -r requirements-dev.txt
CMD ["hypercorn", "--reload", "--bind", "0.0.0.0:8000", "asgi:app"]

# Production stage
FROM base AS production
CMD ["gunicorn", "-w", "2", "-b", "0.0.0.0:8000", "wsgi:app"]