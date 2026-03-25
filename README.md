# AIOps Platform

This repository contains an AI-driven operations platform built to support incident investigation, observability correlation, application health analysis, and guided RCA workflows.

The platform is being shaped as a SaaS-ready control plane with support for:

- AI-assisted incident investigation
- application and service health dashboards
- correlated metrics, logs, and traces
- alert ingestion and recommendation workflows
- command execution through controlled agents
- document-backed operational guidance
- prediction and risk scoring
- immersive React-based operations UI

## What This Platform Does

At a high level, the platform helps operators:

- detect issues through observability signals
- correlate alerts into incidents
- inspect blast radius and dependency context
- ask AI for RCA and next-step guidance
- run controlled diagnostic commands
- analyze command output with a second AI pass
- navigate incidents, applications, predictions, and documents from one workspace

## Current Tech Stack

### Backend

- Python
- Django
- Django ORM
- PostgreSQL
- Redis

### AI / Investigation Layer

- AiDE integration
- prompt-based orchestration in `genai/`
- document-backed retrieval in `doc_search/`
- prediction workflows in `genai/predictions.py`

### Frontend

- React
- TypeScript
- Vite
- TanStack Query
- React Router
- React Three Fiber / Three.js for graph views

### Observability

- Prometheus
- Alertmanager
- Grafana
- OpenTelemetry Collector
- Jaeger
- Elasticsearch
- Filebeat
- node-exporter
- postgres-exporter
- nginx Prometheus exporters

### Automation / Execution

- app-local agents
- db-agent
- allowlisted command execution

### Demo / Chaos

- Nginx frontend and gateway
- Flask demo services
- PostgreSQL
- Toxiproxy for chaos testing

### Packaging / Runtime

- Docker
- Docker Compose
- Nginx

## Repository Layout

```text
asset_management/   Django project settings and app wiring
genai/              AI assistant, incidents, predictions, execution flows
doc_search/         Document upload, processing, and retrieval
frontend/           React frontend replacement
demo/               Demo application, chaos tooling, dependency graph
agent/              Secure execution agents and allowlists
Observability/      Grafana provisioning and dashboards
filebeat/           Log shipping configuration
diagrams/           Architecture diagram sources
docker-compose.yml  Full local stack orchestration
```

## Key Product Areas

### 1. Assistant

The assistant is the investigation workspace. It is intended to:

- accept incident/application/service context
- fetch telemetry context
- explain RCA and blast radius
- suggest diagnostic commands
- analyze command output after execution

### 2. Incidents

Incidents are correlated from alerts and enriched with:

- incident timeline
- linked recommendation
- graph view
- secondary AI analysis

### 3. Applications

Applications are shown as service portfolios with:

- component health
- AI insight
- prediction risk
- graph entry points

### 4. Graphs

Graph views support:

- application topology
- incident blast radius
- alert-linked graph entry
- dependency context

### 5. Predictions

Prediction workflows provide:

- service risk scoring
- incident probability
- blast radius-aware context

### 6. Documents

Document workflows support:

- runbook upload
- retrieval-augmented answers
- operational guidance

## Local Development

### Prerequisites

- Docker
- Docker Compose

### Environment Setup

1. Copy the example env file:

```bash
cp .env.example .env
```

2. Fill in the required values in `.env`, especially:

- `POSTGRES_PASSWORD`
- `GOOGLE_CLIENT_ID`
- `GOOGLE_CLIENT_SECRET`
- `AIDE_API_KEY`
- `AIDE_API_KEY_SECONDARY`
- `AGENT_SECRET_TOKEN`

### Start the Stack

```bash
docker compose up -d --build
```

Main URLs:

- Django backend: `http://localhost:8000`
- React frontend: `http://localhost:8089`
- Prometheus: `http://localhost:9090`
- Alertmanager: `http://localhost:9093`
- Grafana: `http://localhost:3000`
- Demo frontend: `http://localhost:8088`

## Frontend

The new user experience lives in the React app under `frontend/`.

The React frontend is deployed as a separate production-style container and proxies back to the Django backend.

## Chaos and Demo

Chaos tooling lives under `demo/tools/`.

See:

- [CHAOS_RUNBOOK.md](./CHAOS_RUNBOOK.md)
- [ARCHITECTURE.md](./ARCHITECTURE.md)

## Architecture and Roadmaps

- [ARCHITECTURE.md](./ARCHITECTURE.md)
- [FRONTEND_MIGRATION_PLAN.md](./FRONTEND_MIGRATION_PLAN.md)
- [MCP_PHASE_PLAN.md](./MCP_PHASE_PLAN.md)

## Notes

- The internal Django project package is still named `asset_management`, but the product identity is AIOps.
- `.env` is intentionally gitignored.
- Local runtime data and generated volumes are also ignored.

