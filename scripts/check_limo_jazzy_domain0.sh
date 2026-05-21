#!/usr/bin/env bash
set -eo pipefail

source "${HOME}/source_ros2_jazzy_domain0.sh"

echo "ROS_DISTRO=${ROS_DISTRO}"
echo "ROS_DOMAIN_ID=${ROS_DOMAIN_ID}"
echo "ros2=$(which ros2)"
echo
echo "[nodes]"
ros2 node list || true
echo
echo "[topics]"
ros2 topic list || true
echo
echo "[hints]"
echo "If nothing is listed, start LIMO on Foxy with:"
echo "  export ROS_DOMAIN_ID=0"
echo "  source /opt/ros/foxy/setup.bash"
echo "  ros2 launch limo_base start_limo.launch.py"
echo
echo "If discovery still fails, set this on both sides before launch:"
echo "  export RMW_IMPLEMENTATION=rmw_cyclonedds_cpp"
