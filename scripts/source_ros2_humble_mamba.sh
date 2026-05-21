#!/usr/bin/env bash
set -eo pipefail

export MAMBA_ROOT_PREFIX="${HOME}/.local/share/mamba"
export PATH="${HOME}/.local/bin:${PATH}"

# Avoid mixing the host Jazzy environment with the isolated Humble environment.
unset AMENT_PREFIX_PATH
unset CMAKE_PREFIX_PATH
unset COLCON_PREFIX_PATH
unset LD_LIBRARY_PATH || true
unset PYTHONPATH || true
unset ROS_DISTRO || true
unset ROS_ETC_DIR || true
unset ROS_PACKAGE_PATH || true
unset ROS_PYTHON_VERSION || true
unset ROS_VERSION || true

set +u
source "${HOME}/.local/share/mamba/envs/ros2_humble/setup.bash"
