#!/usr/bin/env bash
set -eo pipefail

# Keep this shell on the host Jazzy installation and force domain 0 for LIMO checks.
unset AMENT_PREFIX_PATH || true
unset CMAKE_PREFIX_PATH || true
unset COLCON_PREFIX_PATH || true
unset LD_LIBRARY_PATH || true
unset PYTHONPATH || true
unset ROS_DISTRO || true
unset ROS_ETC_DIR || true
unset ROS_PACKAGE_PATH || true
unset ROS_PYTHON_VERSION || true
unset ROS_VERSION || true

export ROS_DOMAIN_ID=0

source /opt/ros/jazzy/setup.bash
