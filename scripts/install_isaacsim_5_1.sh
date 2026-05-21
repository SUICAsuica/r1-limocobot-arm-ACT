#!/usr/bin/env bash
set -euo pipefail

ISAAC_VERSION="5.1.0"
ARCHIVE="isaac-sim-standalone-${ISAAC_VERSION}-linux-x86_64.zip"
URL="https://downloads.isaacsim.nvidia.com/${ARCHIVE}"
DOWNLOAD_DIR="${HOME}/Downloads"
INSTALL_DIR="${HOME}/isaacsim"

if ! command -v nvidia-smi >/dev/null 2>&1; then
  echo "nvidia-smi was not found. Install the NVIDIA driver first:"
  echo "  bash ~/install_nvidia_driver_for_isaacsim.sh"
  echo "Then reboot and rerun this script."
  exit 1
fi

echo "Detected NVIDIA GPU:"
nvidia-smi --query-gpu=name,driver_version,memory.total --format=csv,noheader

mkdir -p "${DOWNLOAD_DIR}" "${INSTALL_DIR}"

if ! command -v unzip >/dev/null 2>&1; then
  echo "unzip is required and was not found. Installing it with apt."
  sudo apt update
  sudo apt install -y unzip
fi

if [ ! -f "${DOWNLOAD_DIR}/${ARCHIVE}" ]; then
  echo "Downloading Isaac Sim ${ISAAC_VERSION} to ${DOWNLOAD_DIR}/${ARCHIVE}"
  echo "This file is about 8.2 GB."
  wget -c -O "${DOWNLOAD_DIR}/${ARCHIVE}" "${URL}"
else
  echo "Using existing archive: ${DOWNLOAD_DIR}/${ARCHIVE}"
fi

echo "Extracting to ${INSTALL_DIR}"
unzip -o "${DOWNLOAD_DIR}/${ARCHIVE}" -d "${INSTALL_DIR}"

cd "${INSTALL_DIR}"
./post_install.sh

echo
echo "Running Isaac Sim compatibility check. This can take several minutes on the first run."
if [ -x ./isaac-sim.compatibility_check.sh ]; then
  ./isaac-sim.compatibility_check.sh --/app/quitAfter=10 --no-window || true
else
  echo "compatibility checker was not found; skipping."
fi

echo
echo "Install finished. Start Isaac Sim with:"
echo "  cd ${INSTALL_DIR}"
echo "  ./isaac-sim.selector.sh"
