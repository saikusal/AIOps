# Deployment Notes

For the full operator-facing Kubernetes install flow, see [KUBERNETES_DEPLOYMENT.md](./KUBERNETES_DEPLOYMENT.md).

OpsMitra now supports two Kubernetes deployment tracks:

1. `deploy/helm/opsmitra`
   The OpsMitra control plane itself.
2. `deploy/helm/opsmitra-cluster-agent`
   The monitored-cluster agent installed into customer Kubernetes clusters.

## Build and push the cluster-agent image

```bash
./scripts/build_k8s_agent_image.sh your-registry/opsmitra-k8s-agent v0.1.0
./scripts/push_k8s_agent_image.sh your-registry/opsmitra-k8s-agent v0.1.0
```

Then set:

- `AIOPS_K8S_AGENT_IMAGE_REPOSITORY=your-registry/opsmitra-k8s-agent`
- `AIOPS_K8S_AGENT_IMAGE_TAG=v0.1.0`

on the control plane so generated onboarding manifests point to the correct image.

## Current Kubernetes capability boundary

Implemented today:

- control-plane deployment on Kubernetes
- monitored-cluster enrollment
- cluster heartbeat
- read-only discovery
- Kubernetes diagnostic command execution through the cluster agent
- Kubernetes rollout restart remediation through the cluster agent

Not implemented yet:

- scale / cordon / drain and broader Kubernetes-native action coverage
