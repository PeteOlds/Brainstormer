# OpenCode Project Guide: Full-Stack Proof of Concept

This guide defines the standards, structure, and operational protocol for OpenCode when bootstrapping and building a new proof-of-concept (PoC) application derived from an approved BS idea (e.g., `IDEA-1114`).

---

## 1. Core Principles & Workflow

* **Clean Slate Execution:** Every idea lives in its own isolated directory and repository. Do not reference or mix code from other idea directories.
* **Docker as Truth:** All full-stack applications must be fully containerized. Local development and service orchestration depend strictly on `docker-compose.yml`.
* **Zero Hardcoded Secrets:** Never commit API keys, database credentials, or tokens. Rely exclusively on `.env` files for local development and `.env.example` templates for configuration tracking.
* **CI/CD First:** Prepare GitHub Actions workflows targeting GitHub Container Registry (GHCR) so images are compiled automatically on push.

---

## 2. Directory & Architecture Standard

When initializing a project for `IDEA-XXXX`, construct the project tree adhering to this structure:

```text
IDEA-XXXX/
├── .github/
│   └── workflows/
│       └── docker-build.yml     # CI/CD pipeline for GHCR publishing
├── backend/
│   ├── Dockerfile
│   └── src/
├── frontend/
│   ├── Dockerfile
│   └── src/
├── .env.example                 # Template for required environment variables
├── .gitignore                   # Standard gitignore (node_modules, .env, build outputs)
├── docker-compose.yml           # Local multi-container development manifest
├── REQUIREMENTS.md              # Requirements and design specification from BS
└── README.md                    # Project overview and setup commands

```

---

## 3. Container & Service Configuration Guidelines

### `docker-compose.yml` Requirements

* Define individual services for `frontend`, `backend`, and any stateful dependencies (e.g., `postgres`, `redis`).
* Use environment variables mapped from the local `.env` file.
* Configure explicit service dependencies using `depends_on` with condition-based health checks where applicable.
* Expose local ports cleanly (e.g., Frontend on `3000`, Backend API on `8000`).

```yaml
version: '3.8'

services:
  backend:
    build:
      context: ./backend
      dockerfile: Dockerfile
    ports:
      - "8000:8000"
    env_file:
      - .env
    depends_on:
      db:
        condition: service_healthy

  frontend:
    build:
      context: ./frontend
      dockerfile: Dockerfile
    ports:
      - "3000:3000"
    env_file:
      - .env
    depends_on:
      - backend

  db:
    image: postgres:16-alpine
    environment:
      POSTGRES_DB: ${POSTGRES_DB:-app}
      POSTGRES_USER: ${POSTGRES_USER:-postgres}
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD:-postgres}
    ports:
      - "5432:5432"
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U ${POSTGRES_USER:-postgres}"]
      interval: 5s
      timeout: 5s
      retries: 5

```

---

## 4. GitHub Actions CI/CD Protocol

Always create `.github/workflows/docker-build.yml` to compile and push images to GitHub Container Registry (GHCR) upon merging or pushing to `main`.

```yaml
name: Build and Push Docker Images

on:
  push:
    branches: [ "main" ]

env:
  REGISTRY: ghcr.io
  IMAGE_NAME: ${{ github.repository }}

jobs:
  build-and-push:
    runs-on: ubuntu-latest
    permissions:
      contents: read
      packages: write

    steps:
      - name: Checkout Repository
        uses: actions/checkout@v4

      - name: Log in to GitHub Container Registry
        uses: docker/login-action@v3
        with:
          registry: ${{ env.REGISTRY }}
          username: ${{ github.actor }}
          password: ${{ secrets.GITHUB_TOKEN }}

      - name: Extract Metadata for Backend
        id: meta-backend
        uses: docker/metadata-action@v5
        with:
          images: ${{ env.REGISTRY }}/${{ env.IMAGE_NAME }}/backend

      - name: Build and Push Backend Image
        uses: docker/build-push-action@v5
        with:
          context: ./backend
          push: true
          tags: ${{ steps.meta-backend.outputs.tags }}
          labels: ${{ steps.meta-backend.outputs.labels }}

      - name: Extract Metadata for Frontend
        id: meta-frontend
        uses: docker/metadata-action@v5
        with:
          images: ${{ env.REGISTRY }}/${{ env.IMAGE_NAME }}/frontend

      - name: Build and Push Frontend Image
        uses: docker/build-push-action@v5
        with:
          context: ./frontend
          push: true
          tags: ${{ steps.meta-frontend.outputs.tags }}
          labels: ${{ steps.meta-frontend.outputs.labels }}

```

---

## 5. Verification Protocol

Before completing a task or yielding execution in OpenCode:

1. Verify `docker-compose.yml` parses correctly without syntax errors (`docker compose config`).
2. Confirm `.env.example` contains all variables referenced across services.
3. Validate that `REQUIREMENTS.md` accurately reflects the build deliverables for the given `IDEA-XXXX`.

---

---

# Human Operations Playbook: Platform & Access Setup

This document details the manual setup steps required by the developer to configure GitHub credentials, manage container privacy, set up deployment hosts (Render / Coolify), and run the automation scaffolding.

---

## 1. Prerequisites Checklist

* **GitHub Account / Organization** with repository creation permissions.
* **GitHub CLI (`gh`)** installed locally (`brew install gh` or platform equivalent).
* **Docker Desktop** or **OrbStack** running locally.
* Account on deployment platform (**Render**, **Railway**, or a self-hosted **Coolify** instance).

---

## 2. GitHub Access & Personal Access Token (PAT) Setup

To allow local Docker CLI tools and external deployment platforms (like Render or Coolify) to pull private images from GHCR, generate a Personal Access Token:

1. Navigate to **GitHub → Settings → Developer Settings → Personal Access Tokens → Fine-Grained Tokens** (or Classic Tokens).
2. Click **Generate New Token**.
3. Set the following parameters:
* **Token Name:** `GHCR Access Token - BS Pipeline`
* **Expiration:** Select preferred duration (e.g., 90 days or 1 year).
* **Repository Access:** Select *All Repositories* (or specific idea repositories).
* **Permissions:**
* `Packages`: Select **Read and Write** (for publishing/pulling images).
* `Contents`: Select **Read-only** (if deploying code directly from source).




4. Save the generated token securely in a password manager.

---

## 3. Local Docker Authentication with GHCR

To pull private container images locally without rebuilding from source:

```bash
# Log in to GHCR using your GitHub username and PAT
echo "YOUR_PERSONAL_ACCESS_TOKEN" | docker login ghcr.io -u YOUR_GITHUB_USERNAME --password-stdin

```

Once logged in, pull images via:

```bash
docker pull ghcr.io/YOUR_GITHUB_ORGANIZATION/IDEA-1114/backend:main

```

---

## 4. External Deployment Platform Setup

### Option A: Render Setup

1. **Connect GitHub:** Log in to Render and connect your GitHub account under **Account Settings → Service Connections**.
2. **Deploying via Source (Recommended for Single-Service / Standard Apps):**
* Select **New → Web Service**.
* Link your GitHub repository (`IDEA-1114`).
* Choose **Docker** as the Runtime.
* Add environment variables matching `.env.example`.


3. **Deploying Private Images from GHCR:**
* Create a **Private Registry Credential** in Render under **Account Settings → Registry Credentials**.
* Set Registry: `ghcr.io`, Username: `YOUR_GITHUB_USERNAME`, Password: `YOUR_PAT`.
* When creating a service, specify the image URL: `ghcr.io/OWNER/IDEA-1114/backend:main`.



---

### Option B: Coolify (Self-Hosted PaaS) Setup

1. **Connect GitHub App:** Inside Coolify, go to **Sources → Add New Source → GitHub App** and follow the prompt to authorize your organization.
2. **Connect GHCR Registry:**
* Go to **Registries → Add New Registry**.
* Select **Custom / GHCR**.
* Enter your GitHub username and Personal Access Token.


3. **Deploy Multi-Container Apps:**
* Create a new Project in Coolify named `IDEA-1114`.
* Add a service using **Docker Compose**.
* Paste or link the repository's `docker-compose.yml`. Coolify handles building, SSL certificates, and domain routing automatically.



---

## 5. Automated Idea Scaffolding Script (`start-idea.sh`)

Save this script as `start-idea.sh` on your local system to automate directory initialization, GitHub repository creation, requirement bootstrapping, and launching OpenCode.

```bash
#!/usr/bin/env bash
set -e

if [ -z "$1" ]; then
  echo "Error: Idea ID is required."
  echo "Usage: ./start-idea.sh IDEA-1114"
  exit 1
fi

IDEA_ID=$1
TARGET_DIR="./$IDEA_ID"

if [ -d "$TARGET_DIR" ]; then
  echo "Error: Directory $TARGET_DIR already exists."
  exit 1
fi

echo "==> Creating directory: $TARGET_DIR"
mkdir -p "$TARGET_DIR"
cd "$TARGET_DIR"

echo "==> Initializing Git repository..."
git init

echo "==> Creating initial requirements template..."
cat <<EOF > REQUIREMENTS.md
# Requirement Specification: $IDEA_ID

## Overview
Brief description of $IDEA_ID.

## Target Architecture
- Frontend: Web Client
- Backend: REST / GraphQL API
- Database: PostgreSQL

## Goals & Functional Scope
- Proof of concept feature set.
EOF

echo "==> Creating GitHub repository via GH CLI..."
gh repo create "$IDEA_ID" --private --source=. --remote=origin

echo "==> Pushing initial commit..."
git add REQUIREMENTS.md
git commit -m "feat: initialize $IDEA_ID scaffolding"
git branch -M main
git push -u origin main

echo "==> Launching OpenCode session..."
opencode .

```

Make the script executable:

```bash
chmod +x start-idea.sh

```

Execute to spin up a new idea:

```bash
./start-idea.sh IDEA-1114

```