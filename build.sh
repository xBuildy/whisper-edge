#!/usr/bin/env bash
set -e

# Configuration
IMAGE_NAME="ghcr.io/xbuildyteam/whisper-edge"
VERSION="${1:-1.0.0}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

cd "$SCRIPT_DIR"

echo "=========================================="
echo "Building and Pushing Whisper Edge Container"
echo "Image: ${IMAGE_NAME}"
echo "Tags: latest, ${VERSION}"
echo "=========================================="

# Check for Docker or Podman
if command -v docker &> /dev/null; then
    CONTAINER_CLI="docker"
elif command -v podman &> /dev/null; then
    CONTAINER_CLI="podman"
else
    echo "Error: Neither docker nor podman is installed or available in PATH."
    exit 1
fi

# Authenticate to GHCR if token is present
GHCR_TOKEN="${GHCR_TOKEN:-${GITHUB_TOKEN:-${CR_PAT:-}}}"
if [ -n "$GHCR_TOKEN" ]; then
    USER="${GHCR_USER:-xbuildyteam}"
    echo "Logging into ghcr.io as ${USER}..."
    echo "$GHCR_TOKEN" | $CONTAINER_CLI login ghcr.io -u "$USER" --password-stdin
else
    echo "Notice: GHCR_TOKEN / GITHUB_TOKEN not set in environment."
    echo "If push fails due to authentication, log in manually using:"
    echo "  $CONTAINER_CLI login ghcr.io"
fi

# Build image with both tags
echo "Building image..."
$CONTAINER_CLI build -t "${IMAGE_NAME}:latest" -t "${IMAGE_NAME}:${VERSION}" .

# Push image tags
echo "Pushing ${IMAGE_NAME}:latest..."
$CONTAINER_CLI push "${IMAGE_NAME}:latest"

echo "Pushing ${IMAGE_NAME}:${VERSION}..."
$CONTAINER_CLI push "${IMAGE_NAME}:${VERSION}"

echo "=========================================="
echo "Successfully built and pushed:"
echo "  - ${IMAGE_NAME}:latest"
echo "  - ${IMAGE_NAME}:${VERSION}"
echo "=========================================="
