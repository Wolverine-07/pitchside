#!/usr/bin/env bash
# Build the image locally, push it, retag it with OCI media types and roll it out.
# (Azure for Students blocks ACR Tasks, so the build runs on this machine.)
#   infra/deploy.sh [resource-group] [registry-name]
set -euo pipefail

RG=${1:-rg-pitchside}
ACR=${2:-$(az acr list -g "$RG" --query "[0].name" -o tsv)}
APP=pitchside-web
TAG=v$(git rev-parse --short HEAD)$( [ -n "$(git status --porcelain)" ] && echo "-dirty" || true )
IMAGE="$ACR.azurecr.io/pitchside"

cd "$(dirname "$0")/.."
docker build -q -t "$IMAGE:$TAG" .
az acr login -n "$ACR" >/dev/null
docker push -q "$IMAGE:$TAG"

ACR_USER=$(az acr credential show -n "$ACR" --query username -o tsv) \
ACR_PASSWORD=$(az acr credential show -n "$ACR" --query "passwords[0].value" -o tsv) \
  backend/.venv/bin/python infra/oci_retag.py "$ACR.azurecr.io" pitchside "$TAG" "$TAG-oci"

az containerapp update -g "$RG" -n "$APP" --image "$IMAGE:$TAG-oci" -o none
URL=$(az containerapp show -g "$RG" -n "$APP" --query properties.configuration.ingress.fqdn -o tsv)
for _ in $(seq 1 18); do
  if curl -fs "https://$URL/api/health"; then echo; echo "live: https://$URL"; exit 0; fi
  sleep 10
done
echo "health check did not pass in time" >&2
exit 1
