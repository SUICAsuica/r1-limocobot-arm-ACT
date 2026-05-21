#!/usr/bin/env bash
set -euo pipefail

CONTAINER_NAME="${CONTAINER_NAME:-ros2_foxy}"
ROS_DOMAIN_ID_VALUE="${ROS_DOMAIN_ID:-2}"
DISPLAY_VALUE="${DISPLAY:-}"
XAUTHORITY_VALUE="${XAUTHORITY:-${HOME}/.Xauthority}"

if [[ $# -eq 0 ]]; then
  cat <<'EOF' >&2
Usage: run_ros2_foxy_udocker.sh <command...>

Examples:
  run_ros2_foxy_udocker.sh bash
  run_ros2_foxy_udocker.sh ros2 topic list
EOF
  exit 1
fi

UDOCKER_ARGS=(
  --bindhome
  --hostenv
  --env="ROS_DOMAIN_ID=${ROS_DOMAIN_ID_VALUE}"
  --env="DISPLAY=${DISPLAY_VALUE}"
  --env="XAUTHORITY=${XAUTHORITY_VALUE}"
  --volume=/tmp/.X11-unix:/tmp/.X11-unix
)

if [[ -n "${XAUTHORITY_VALUE}" && -e "${XAUTHORITY_VALUE}" ]]; then
  UDOCKER_ARGS+=(--volume="${XAUTHORITY_VALUE}:${XAUTHORITY_VALUE}")
fi

exec micromamba run -n udocker_env \
  udocker run \
  "${UDOCKER_ARGS[@]}" \
  "${CONTAINER_NAME}" \
  "$@"
