# OpsMitra Control Plane Helm Chart

This chart deploys the OpsMitra control plane on Kubernetes.

## What it deploys

- `web` Django control plane
- `frontend` Vite UI container
- `predictor` background prediction loop
- `postgres` for relational state
- `redis` for cache / queue support

## Quick start

```bash
helm upgrade --install opsmitra ./deploy/helm/opsmitra \
  --namespace opsmitra \
  --create-namespace \
  -f ./deploy/helm/opsmitra/values.yaml
```

## Important values

- `images.web.repository` / `images.web.tag`
- `images.frontend.repository` / `images.frontend.tag`
- `application.secretEnv.AGENT_SECRET_TOKEN`
- `application.secretEnv.MCP_INTERNAL_TOKEN`
- `application.secretEnv.AIOPS_INTENT_SIGNING_SECRET`
- `application.env.VLLM_API_URL`
- `application.env.AIOPS_K8S_AGENT_IMAGE_REPOSITORY`
- `application.env.AIOPS_K8S_AGENT_IMAGE_TAG`
- `ingress.*`

## Notes

- This chart assumes container images already exist in your registry.
- For production, replace default secrets before install.
- If you use external Postgres or Redis later, disable the in-chart deployments and point env vars at managed services.
