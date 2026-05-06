#!/usr/bin/env bash
set -euo pipefail

IMAGE_REPOSITORY="${1:-opsmitra/k8s-cluster-agent}"
IMAGE_TAG="${2:-latest}"
FULL_IMAGE="${IMAGE_REPOSITORY}:${IMAGE_TAG}"

echo "Pushing ${FULL_IMAGE}"
docker push "${FULL_IMAGE}"
echo "Pushed ${FULL_IMAGE}"
