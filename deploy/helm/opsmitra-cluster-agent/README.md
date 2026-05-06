# OpsMitra Cluster Agent Helm Chart

This chart deploys the monitored-cluster agent into a customer Kubernetes cluster.

## Purpose

The cluster agent:

- enrolls the cluster into OpsMitra using an enrollment token
- sends heartbeat updates back to the control plane
- discovers namespaces, nodes, services, deployments, statefulsets, daemonsets, and ingresses
- executes queued Kubernetes diagnostic commands from the control plane
- supports rollout restart remediation for deployments, statefulsets, and daemonsets

The current implementation covers enrollment, heartbeat, discovery, diagnostics, and rollout restart remediation.

## Quick start

```bash
helm upgrade --install opsmitra-cluster-agent ./deploy/helm/opsmitra-cluster-agent \
  --namespace opsmitra-system \
  --create-namespace \
  --set agent.controlPlaneUrl=https://opsmitra.example.com \
  --set agent.enrollToken=replace-with-token \
  --set agent.clusterName=customer-prod-cluster \
  --set agent.image.repository=opsmitra/k8s-cluster-agent \
  --set agent.image.tag=latest
```

## Important values

- `agent.controlPlaneUrl`
- `agent.enrollToken`
- `agent.clusterName`
- `agent.image.repository`
- `agent.image.tag`
- `agent.verifySsl`
- `agent.heartbeatIntervalSeconds`

## Security model

- outbound-only communication from cluster to control plane
- RBAC scoped for the currently supported diagnostic and rollout actions
- non-root container with dropped capabilities
