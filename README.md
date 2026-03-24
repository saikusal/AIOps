# AIOps Platform

This repository contains the foundation of an AI-driven operations platform designed for SaaS and enterprise deployment.

The platform is intended to help operations teams:

- monitor applications and infrastructure
- investigate incidents with AI assistance
- correlate metrics, logs, traces, and alerts
- search internal documents and runbooks
- guide operators toward RCA and next actions

Although the historical Django project name in this repository is still `asset_management`, the product direction is broader: this codebase is evolving into an AIOps control plane.

## Product Vision

This platform is being shaped as an AIOps SaaS offering with support for:

- centralized observability
- AI-assisted incident investigation
- document-backed operational guidance
- application and service health views
- extensible integrations for alerts, telemetry, and automation
- cloud-hosted and air-gapped deployment models

The long-term goal is a single platform that can onboard:

- standalone applications
- virtual machines and servers
- containerized workloads
- Kubernetes environments

## Core Capabilities

- AI assistant for operational questions and RCA workflows
- observability-aware reasoning across metrics, logs, and traces
- document ingestion and retrieval for SOPs, policies, and runbooks
- incident correlation and investigation support
- application/service health monitoring integrations
- video processing utilities for subtitle and transcript workflows
- Docker-based local and packaged deployment

## Architecture Direction

At a high level, the platform is moving toward this model:

```text
Users / Operators
        |
        v
Frontend Experience Layer
        |
        v
Django Control Plane / APIs
        |
        +-- AI Assistant / Investigation Layer
        +-- Document Search / RAG Layer
        +-- Incident / Alert / Workflow Layer
        +-- Asset / Workflow Modules
        |
        v
Observability + Data Integrations
        |
        +-- Prometheus / metrics
        +-- Logs backends
        +-- Trace backends
        +-- Databases / workers / external services
```

## Current Repository Structure

```text
asset_management/   Django project settings, URLs, WSGI
assets/             Existing asset and workflow application
genai/              AI assistant and AIOps-oriented features
doc_search/         Document ingestion, search, and retrieval
video_processor/    Video upload, processing, and subtitle generation
users/              User routes and user-facing features
templates/          Shared server-rendered templates
static/             Static assets
mediafiles/         Uploaded and generated content
docker-compose.yml  Local container orchestration
Dockerfile*         App, trainer, and worker images
requirements*.txt   Dependency sets
```

## Tech Stack

### Application Layer

- Python
- Django
- Django apps for modular features
- server-rendered templates plus AI/API endpoints

### Data and Storage

- PostgreSQL
- local/media-backed file storage
- JSON-based configuration and payload storage inside Django models

### AI and Knowledge Features

- AI assistant workflows under `genai/`
- document retrieval and RAG support under `doc_search/`
- prompt-driven orchestration for operational analysis

### Observability and Operations

- Prometheus configuration
- OpenTelemetry collector configuration
- Docker / Docker Compose
- worker and trainer container patterns
- log and runtime artifact handling

### Media / Processing

- video processing workflows
- subtitle / transcript generation
- local model artifacts for speech workflows

## SaaS Platform Positioning

From a SaaS perspective, this repository supports the shape of a broader platform:

- multi-module control plane
- pluggable AI-assisted investigation workflows
- extensible observability integrations
- document-backed support operations
- optional deployment in self-hosted or managed modes

A typical SaaS productization path for this platform would include:

- tenant isolation
- SSO and enterprise authentication
- incident and investigation workspaces
- model-provider abstraction
- observability connectors
- agent-based discovery and telemetry collection
- usage metering and admin controls

## Local Development

### 1. Create a Python environment

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 2. Apply migrations

```bash
python manage.py migrate
```

### 3. Run the Django app

```bash
python manage.py runserver
```

Open:

- `http://127.0.0.1:8000`

## Docker Usage

To run the stack with Docker Compose:

```bash
docker compose up --build
```

To run a smaller subset during development:

```bash
docker compose up --build web
```

## Repository Notes

- The internal Django project/module names still reflect the earlier project structure.
- The product direction is now broader than asset management alone.
- Runtime artifacts, uploaded files, local model binaries, caches, and secrets should not be committed.

## Recommended Next Repo Additions

- `.env.example`
- deployment profiles for local, staging, and production
- architecture diagrams and service maps
- API documentation
- setup guide for observability dependencies
- contribution and release workflow docs

