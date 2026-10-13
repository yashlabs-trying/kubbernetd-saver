# Tesseract Ignite — Mac M5 Test Environment Setup
set -euo pipefail 2>/dev/null || set -euo

log() { echo "[$(date +%H:%M:%S)] $*"; }

log "Installing Homebrew..."
NONINTERACTIVE=1 /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"

eval "$(/opt/homebrew/bin/brew shellenv)"

log "Installing kind, kubectl, colima, docker, helm..."
brew install kind kubectl colima docker helm

log "Starting Colima container runtime..."
colima start --cpu 4 --memory 8 --disk 60 --arch aarch64

log "Installing Python test dependencies..."
pip3 install --user pytest pytest-asyncio aiohttp structlog kubernetes kopf typer pyyaml rich prometheus-client anyio

log "Verifying installations..."
kind version
kubectl version --client
colima status 2>&1 || true
docker info --format '{{.OSType}}/{{.Architecture}}' 2>&1 || true

log "Setup complete."
