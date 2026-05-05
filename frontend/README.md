# AIOps Frontend Rebuild

This folder is the new frontend workspace for the immersive AIOps experience.

## Goal

Rebuild the entire frontend without touching the Django backend.

The backend remains responsible for:

- authentication
- session management
- incidents
- predictions
- local Qwen via vLLM integration
- document search / RAG
- alert ingestion
- command orchestration

The frontend will become a dedicated React application that consumes the existing Django APIs.

## Proposed Stack

- React
- TypeScript
- Vite
- React Router
- TanStack Query
- Zustand
- Framer Motion
- React Three Fiber
- Three.js

## Initial Page Map

- `/applications`
- `/assistant`
- `/incidents`
- `/predictions`
- `/documents`
- `/graph/:alertId`

## Migration Strategy

1. Keep Django backend untouched.
2. Replace Django templates screen by screen.
3. Migrate the graph view first into a dedicated immersive React scene.
4. Migrate applications and assistant next.
5. Leave authentication on the backend and call existing endpoints from the frontend.

## Existing Backend Targets

- applications overview:
  - `/genai/applications/overview/`
- recent alerts:
  - `/genai/alerts/recent/`
- predictions:
  - `/genai/predictions/recent/`
- incidents:
  - `/genai/incidents/recent/`
- timeline:
  - `/genai/incidents/<incident_key>/timeline/`
- chat:
  - `/genai/chat/`
- sessions:
  - `/genai/session/init/`
  - `/genai/session/list/`

## Suggested Next Step

Start with the dedicated graph page:

- build `/graph/:alertId`
- fetch the selected alert/recommendation data
- render a Three.js / React Three Fiber neural dependency scene
- then move the applications page to React

## Production Build

The frontend is designed to run as a separate production container.

### Docker build and run

From the AIOps root:

```bash
cd /Users/ajithsai.kusal/Desktop/AIOps
docker compose up -d --build frontend-app
```

Frontend URL:

```text
http://localhost:8089
```

### Container model

- `frontend-app`
  - React production build
  - served by Nginx
- `web`
  - Django backend API
- Nginx in `frontend-app` proxies:
  - `/genai/`
  - `/accounts/`
  - `/doc_search/`
  - `/mediafiles/`
