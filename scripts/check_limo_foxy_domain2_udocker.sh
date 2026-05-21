#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

export ROS_DOMAIN_ID="${ROS_DOMAIN_ID:-2}"

"${SCRIPT_DIR}/run_ros2_foxy_udocker.sh" bash -lc '
echo "ROS_DISTRO=${ROS_DISTRO}"
echo "ROS_DOMAIN_ID=${ROS_DOMAIN_ID}"
echo "ros2=$(which ros2)"
echo
echo "[nodes]"
ros2 node list || true
echo
echo "[topics]"
ros2 topic list || true
'
