#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
IMAGE_REPOSITORY="${1:-opsmitra/k8s-cluster-agent}"
IMAGE_TAG="${2:-latest}"
FULL_IMAGE="${IMAGE_REPOSITORY}:${IMAGE_TAG}"

echo "Building ${FULL_IMAGE}"
docker build \
  -f "${ROOT_DIR}/agent/k8s-agent.Dockerfile" \
  -t "${FULL_IMAGE}" \
  "${ROOT_DIR}"

echo "Built ${FULL_IMAGE}"
