# Frontend Migration Plan

This plan assumes:

- Django backend stays unchanged
- all current API endpoints remain valid
- the frontend is rebuilt separately for a more immersive experience

## Why Separate Frontend

The current Django template frontend is enough for operational prototyping, but it is not the right medium for:

- immersive graph visualization
- rich interaction states
- consistent product-level design
- smooth transitions and motion
- maintainable multi-page SPA behavior

## Recommended Architecture

- Backend:
  - Django
  - PostgreSQL
  - Redis
  - local Qwen via vLLM integration
  - incidents / sessions / predictions / docs
- Frontend:
  - React + TypeScript + Vite
  - React Router
  - TanStack Query
  - Zustand
  - Framer Motion
  - React Three Fiber for graph-heavy pages
  - production container served by Nginx

## Migration Sequence

### Phase 1

- scaffold frontend app
- create app shell and routing
- create page placeholders
- verify backend endpoint access through proxy

### Phase 2

- migrate applications dashboard
- migrate assistant experience
- migrate incidents list / timeline shell

### Phase 3

- build immersive graph page with React Three Fiber
- move alert recommendation graph out of Django template

### Phase 4

- refine prediction center
- migrate documents page
- add polish, transitions, and shared UI components

## First Real Build Target

The best first target is:

- `GraphPage`

Reason:

- it has the highest UX upside
- it is currently the weakest fit for templates
- it gives immediate visible product improvement

## Folder

Frontend workspace:

- `frontend/`

## Production Deployment Shape

Use a separate frontend container:

- `frontend-app`
  - serves built React assets with Nginx
  - proxies API/auth/document traffic to Django `web`
- `web`
  - stays the backend container

This keeps the backend untouched and gives a clean long-term deployment model.
