#!/usr/bin/env bash
# Run the Brainstormer test suite inside the production-like container
# image so system dependencies (gcc, zlib, tesseract, …) are present.
set -euo pipefail

IMAGE="brainstormer-test:latest"
cd "$(dirname "$0")/.."

echo "Building test image…"
docker build -t "$IMAGE" . >/tmp/brainstormer_build.log 2>&1 || {
    echo "Build failed; see /tmp/brainstormer_build.log"
    exit 1
}

echo "Running tests in container…"
docker run --rm \
    -e FLASK_ENV=testing \
    -e DATABASE_URL="sqlite:////tmp/test.db" \
    -e CELERY_BROKER_URL="memory://" \
    -e CELERY_RESULT_BACKEND="cache+memory://" \
    "$IMAGE" \
    sh -c "cd /app && python -m pytest -q --no-cov"
