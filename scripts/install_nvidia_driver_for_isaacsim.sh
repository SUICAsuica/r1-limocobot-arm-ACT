#!/usr/bin/env bash
set -euo pipefail

echo "Installing NVIDIA driver recommended for this machine: nvidia-driver-580-open"
echo "This requires sudo and a reboot. If Secure Boot is enabled, Ubuntu may ask you to enroll a MOK key."

sudo apt update
sudo apt install -y nvidia-driver-580-open

echo
echo "Driver package installation finished."
echo "Reboot now, then run:"
echo "  nvidia-smi"
echo
echo "After nvidia-smi works, run:"
echo "  bash ~/install_isaacsim_5_1.sh"
