# OpenCode Project Guide: Full-Stack Proof of Concept 

This guide defines the standards, structure, and operational protocol for OpenCode when bootstrapping and building a new proof-of-concept (PoC) application derived from an approved BS idea (e.g., `IDEA-1114`).

---

## 1. Core Principles & Workflow

* **Clean Slate Execution:** Every idea lives in its own isolated directory. Do not reference or mix code from other idea directories.
* **Local Docker as Truth (Mandatory):** All full-stack applications must be fully containerized locally. Local development and service orchestration depend strictly on `docker-compose.yml`.
* **GitHub Integration (Encouraged, Optional):** Git versioning and GitHub remote synchronization are strongly encouraged for backup and collaboration, but local builds must run independently of GitHub.
* **Remote Cloud Deployment (Optional - Edge Case):** Deployment to cloud providers like Render is strictly optional and expected for only a small subset of mature PoCs.
* **Zero Hardcoded Secrets:** Never commit API keys, database credentials, or secrets. Rely exclusively on `.env` files for local development and `.env.example` templates for tracking configuration options.

---

## 2. Directory & Architecture Standard

When initializing a project for `IDEA-XXXX`, construct the project tree adhering to this structure:

```text
IDEA-XXXX/
├── .github/                     # OPTIONAL: Included only if GitHub integration is enabled
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
├── docker-compose.yml           # Mandatory local multi-container manifest
├── REQUIREMENTS.md              # Requirements and design specification from BS
└── README.md                    # Project overview and local execution instructions

```

---

## 3. Mandatory Container Configuration (`docker-compose.yml`)

The `docker-compose.yml` file is the primary deliverable for local testing. It must launch the entire application stack locally using standard Docker commands (`docker compose up`).

```yaml
version: '3.8'

services:
  backend:
    build:
      context: ./backend
      dockerfile: Dockerfile
    ports:
      - "${BACKEND_PORT:-8000}:8000"
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
      - "${FRONTEND_PORT:-3000}:3000"
    env_file:
      - .env
    depends_on:
      - backend

  db:
    image: postgres:16-alpine
    environment:
      POSTGRES_DB: ${POSTGRES_DB:-app_db}
      POSTGRES_USER: ${POSTGRES_USER:-postgres}
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD:-postgres}
    ports:
      - "${DB_PORT:-5432}:5432"
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U ${POSTGRES_USER:-postgres}"]
      interval: 5s
      timeout: 5s
      retries: 5

```

---

## 4. Optional GitHub Actions Workflow

If GitHub integration is enabled for the project, create `.github/workflows/docker-build.yml` to compile and push images to GitHub Container Registry (GHCR) upon pushing to `main`.

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

```

---

## 5. Verification Protocol

Before completing a task in OpenCode:

1. Verify `docker-compose.yml` parses correctly without syntax errors (`docker compose config`).
2. Ensure local environment file `.env.example` is populated with default non-sensitive values.
3. Confirm that running `docker compose up --build` successfully initializes all containers locally.

---

---

# Human Operations Playbook: Setup & Automation

This playbook covers local environment setup, optional GitHub remote creation, optional Render cloud hosting, and workspace initialization.

---

## 1. Optional GitHub Setup

GitHub tracking is optional but recommended for version control and image publishing.

1. Generate a GitHub Personal Access Token (PAT) with `write:packages` and `read:packages` scopes if you plan to use GHCR.
2. Authenticate local Docker CLI to GHCR (optional):
```bash
echo "YOUR_PAT" | docker login ghcr.io -u YOUR_GITHUB_USERNAME --password-stdin

```



---

## 2. Optional Render Cloud Deployment Setup

For the subset of projects requiring cloud deployment on Render:

1. Connect your GitHub account to Render under **Account Settings → Service Connections**.
2. **Deploying from Repository:**
* Create a new **Web Service** on Render.
* Connect the target idea repository (`IDEA-XXXX`).
* Set runtime to **Docker** and point to the appropriate `Dockerfile` path (e.g., `./backend/Dockerfile`).
* Copy variables from `.env.example` into Render's Environment Variables section.



---

## 3. Automated Idea Scaffolding Script (`start-idea.sh`)

Use this local script to spin up a new idea folder, initialize git, optionally link a remote GitHub repository, and open OpenCode.

```bash
#!/usr/bin/env bash
set -e

if [ -z "$1" ]; then
  echo "Error: Idea ID is required."
  echo "Usage: ./start-idea.sh IDEA-1114 [--use-github]"
  exit 1
fi

IDEA_ID=$1
USE_GITHUB=false

if [ "$2" == "--use-github" ]; then
  USE_GITHUB=true
fi

TARGET_DIR="./$IDEA_ID"

if [ -d "$TARGET_DIR" ]; then
  echo "Error: Directory $TARGET_DIR already exists."
  exit 1
fi

echo "==> Creating directory: $TARGET_DIR"
mkdir -p "$TARGET_DIR"
cd "$TARGET_DIR"

echo "==> Initializing Git local repository..."
git init

echo "==> Bootstrapping REQUIREMENTS.md..."
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

cat <<EOF > .env.example
# Application Ports
FRONTEND_PORT=3000
BACKEND_PORT=8000
DB_PORT=5432

# Database Configuration
POSTGRES_DB=app_db
POSTGRES_USER=postgres
POSTGRES_PASSWORD=postgres
EOF

cp .env.example .env

if [ "$USE_GITHUB" = true ]; then
  echo "==> Creating GitHub repository..."
  gh repo create "$IDEA_ID" --private --source=. --remote=origin
  git add .
  git commit -m "feat: initialize $IDEA_ID scaffolding"
  git branch -M main
  git push -u origin main
else
  echo "==> Skipping GitHub repo creation. Local git repository ready."
  git add .
  git commit -m "feat: initialize $IDEA_ID scaffolding"
fi

echo "==> Launching OpenCode..."
opencode .

```

---

---

# User Setup & Configuration Checklist

### Environment Variables Checklist

| Variable Name | Required / Optional | Default / Example | Purpose |
| --- | --- | --- | --- |
| `FRONTEND_PORT` | **Mandatory** (Local) | `3000` | Port for the web frontend interface |
| `BACKEND_PORT` | **Mandatory** (Local) | `8000` | Port for the backend API |
| `DB_PORT` | **Mandatory** (Local) | `5432` | Port for the database container |
| `POSTGRES_DB` | **Mandatory** (Local) | `app_db` | PostgreSQL database name |
| `POSTGRES_USER` | **Mandatory** (Local) | `postgres` | Database username |
| `POSTGRES_PASSWORD` | **Mandatory** (Local) | `postgres` | Database password |
| `GITHUB_TOKEN` / `PAT` | **Optional** (GitHub) | `ghp_xxx...` | Authentication for GHCR image pushing/pulling |
| `RENDER_API_KEY` | **Optional** (Render) | `rnd_xxx...` | External deployment credential for Render |

---

### Step-by-Step User Instructions

#### Phase 1: Local Development Setup (Mandatory for All Users)

1. **Ensure Prerequisites Are Installed:**
* Install Docker Desktop (or OrbStack) and verify it is running (`docker info`).
* Install OpenCode CLI.


2. **Bootstrap a New Idea Workspace:**
* Run the setup script without flags:
```bash
./start-idea.sh IDEA-1114

```




3. **Run the Application:**
* Inside OpenCode, allow the AI agent to write the code based on `REQUIREMENTS.md`.
* Test the application locally by running:
```bash
docker compose up --build

```


* Open your browser to `http://localhost:3000` (frontend) and `http://localhost:8000` (backend API).



---

#### Phase 2: Remote Code & Container Backup (Optional — Highly Encouraged)

1. **Enable GitHub Integration During Setup:**
* Run the setup script with the GitHub flag:
```bash
./start-idea.sh IDEA-1114 --use-github

```




2. **Push Changes manually (if created locally first):**
* Link to GitHub using GitHub CLI:
```bash
gh repo create IDEA-1114 --private --source=. --remote=origin
git push -u origin main

```





---

#### Phase 3: Cloud Production Deployment (Optional — Small % of Users)

1. **Deploy to Render:**
* Log into your [Render Dashboard](https://dashboard.render.com).
* Click **New +** → **Web Service**.
* Select your `IDEA-1114` GitHub repository.
* Set runtime to **Docker**.
* Enter the mandatory environment variables from `.env.example` under **Environment**.
* Click **Create Web Service**.