# OpsMitra Kubernetes Deployment

Deploy the OpsMitra control plane on any Kubernetes cluster using Helm.

This guide covers:

1. building and pushing the required images,
2. preparing a Helm values file,
3. deploying the control plane,
4. verifying the install,
5. optionally onboarding monitored Kubernetes clusters.

## Prerequisites

You need:

- a Kubernetes cluster with a working default `StorageClass`
- `kubectl` connected to the cluster
- `helm` installed
- `docker` or `docker buildx`
- `openssl`
- a reachable self-hosted `vLLM` endpoint for Qwen
- a container registry you can push to

Recommended minimum for testing:

- `4+ vCPU`
- `12+ GB RAM`
- persistent volumes for Postgres and media storage

## Required Images

The control-plane chart expects container images to already exist in your registry.

Required:

- `opsmitra-web`
- `opsmitra-frontend`

Optional, but needed if you want to onboard monitored Kubernetes clusters later:

- `opsmitra-k8s-cluster-agent`

## Step 1: Clone the Repo

```bash
git clone <your-repo-url>
cd AIOps
```

## Step 2: Build and Push the Control Plane Images

Build and push the backend image:

```bash
docker build -t <registry>/opsmitra-web:<tag> .
docker push <registry>/opsmitra-web:<tag>
```

Build and push the frontend image:

```bash
docker build -t <registry>/opsmitra-frontend:<tag> ./frontend
docker push <registry>/opsmitra-frontend:<tag>
```

If you also want Kubernetes monitored-cluster onboarding, build and push the cluster-agent image:

```bash
./scripts/build_k8s_agent_image.sh <registry>/opsmitra-k8s-agent <tag>
./scripts/push_k8s_agent_image.sh <registry>/opsmitra-k8s-agent <tag>
```

## Step 3: Create a Helm Values File

Create a deployment-specific values file:

```bash
cp deploy/helm/opsmitra/values.yaml deploy/helm/opsmitra/values.generated.yaml
```

Edit `deploy/helm/opsmitra/values.generated.yaml`.

At minimum, set:

```yaml
images:
  web:
    repository: <registry>/opsmitra-web
    tag: <tag>
  frontend:
    repository: <registry>/opsmitra-frontend
    tag: <tag>

application:
  env:
    VLLM_API_URL: "http://<your-vllm-host>:8001/v1/chat/completions"
    VLLM_MODEL_NAME: "qwen32b"
    VLLM_VISION_MODEL_NAME: "qwen32b"
    DJANGO_ALLOWED_HOSTS: "*"
    AIOPS_K8S_AGENT_IMAGE_REPOSITORY: "<registry>/opsmitra-k8s-agent"
    AIOPS_K8S_AGENT_IMAGE_TAG: "<tag>"
    AIOPS_K8S_AGENT_NAMESPACE: "opsmitra-system"

  secretEnv:
    POSTGRES_PASSWORD: "<strong-db-password>"
    AGENT_SECRET_TOKEN: "<long-random-secret>"
    MCP_INTERNAL_TOKEN: "<long-random-secret>"
    AIOPS_INTENT_SIGNING_SECRET: "<long-random-secret>"
```

Generate secrets with:

```bash
openssl rand -hex 32
```

Notes:

- `VLLM_API_URL` is required. The chart does not deploy `vLLM` for you.
- `AGENT_SECRET_TOKEN` secures Linux host command agents.
- `MCP_INTERNAL_TOKEN` secures internal control-plane APIs.
- `AIOPS_INTENT_SIGNING_SECRET` signs approval-aware execution intents.
- `AIOPS_K8S_AGENT_IMAGE_*` is only required if you want the control plane to generate working monitored-cluster onboarding manifests.

## Step 4: Optional Ingress Setup

If you want browser access through an ingress hostname, install an ingress controller first.

Example with nginx ingress:

```bash
kubectl apply -f https://raw.githubusercontent.com/kubernetes/ingress-nginx/controller-v1.8.1/deploy/static/provider/cloud/deploy.yaml
```

Then enable ingress in `deploy/helm/opsmitra/values.generated.yaml`:

```yaml
ingress:
  enabled: true
  className: nginx
  hosts:
    - host: opsmitra.<your-domain>
      paths:
        - path: /
          pathType: Prefix
          service: frontend
```

If you only want to test quickly, keep ingress disabled and use port-forwarding later.

## Step 5: Deploy OpsMitra

Install the Helm chart:

```bash
helm upgrade --install opsmitra ./deploy/helm/opsmitra \
  --namespace opsmitra \
  --create-namespace \
  --reset-values \
  -f deploy/helm/opsmitra/values.generated.yaml
```

## Step 6: Verify the Pods

Check that the main services are starting:

```bash
kubectl get pods -n opsmitra
```

You should see pods for:

- `web`
- `frontend`
- `predictor`
- `postgres`
- `redis`
- `otel-collector`
- `jaeger`
- `victoriametrics`

## Step 7: Check Logs If Needed

Useful commands:

```bash
kubectl logs -n opsmitra deploy/opsmitra-web
kubectl logs -n opsmitra deploy/opsmitra-frontend
kubectl logs -n opsmitra deploy/opsmitra-predictor
kubectl logs -n opsmitra deploy/opsmitra-otel-collector
```

If your release name is different, replace the deployment names accordingly.

## Step 8: Access the UI

If ingress is disabled, use port-forwarding:

```bash
kubectl port-forward -n opsmitra svc/opsmitra-frontend 8089:8080
kubectl port-forward -n opsmitra svc/opsmitra-web 8000:8000
```

Then open:

- UI: `http://localhost:8089`
- backend: `http://localhost:8000`

## Step 9: Basic Validation

Confirm:

- the UI loads
- the backend responds
- Fleet and incidents pages open
- the predictor pod is running
- Jaeger is reachable if port-forwarded
- VictoriaMetrics is reachable if port-forwarded

## Step 10: Optional Monitored-Cluster Onboarding

Once the OpsMitra control plane is running:

1. open the OpsMitra UI
2. go to onboarding
3. choose `Kubernetes`
4. generate the cluster-agent install command or manifest
5. apply it to the target cluster

The monitored-cluster agent will then:

- enroll into OpsMitra
- send cluster heartbeats
- discover namespaces, services, workloads, nodes, and ingresses
- support `kubectl` diagnostics
- support `kubectl rollout restart` for safe restart remediation

If you prefer Helm for the monitored-cluster agent itself, use:

```bash
cp deploy/helm/opsmitra-cluster-agent/values.yaml deploy/helm/opsmitra-cluster-agent/values.generated.yaml
```

Then set:

```yaml
agent:
  image:
    repository: <registry>/opsmitra-k8s-cluster-agent
    tag: <tag>
  controlPlaneUrl: "https://<opsmitra-url>"
  enrollToken: "<generated-enrollment-token>"
  clusterName: "customer-cluster"
```

Deploy it with:

```bash
helm upgrade --install opsmitra-cluster-agent ./deploy/helm/opsmitra-cluster-agent \
  --namespace opsmitra-system \
  --create-namespace \
  -f deploy/helm/opsmitra-cluster-agent/values.generated.yaml
```

## Current Kubernetes Capability Boundary

Implemented today:

- control-plane deployment on Kubernetes
- monitored-cluster enrollment
- cluster heartbeat
- workload and service discovery
- Kubernetes diagnostic command execution through the cluster agent
- `kubectl rollout restart` remediation through the cluster agent

Not implemented yet:

- scale
- cordon
- drain
- broader Kubernetes-native action coverage

## Quick Summary

1. build and push `opsmitra-web` and `opsmitra-frontend`
2. optionally build and push `opsmitra-k8s-cluster-agent`
3. create `deploy/helm/opsmitra/values.generated.yaml`
4. set image names, `VLLM_API_URL`, and secrets
5. run `helm upgrade --install`
6. verify pods
7. access the UI by ingress or port-forward
8. optionally onboard customer clusters
