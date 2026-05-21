#!/usr/bin/env bash
set -euo pipefail

WS_DIR="${HOME}/limo_pro2_ws"
SRC_DIR="${WS_DIR}/src"
WITH_ARM=0
SKIP_ROSDEP=0

for arg in "$@"; do
  case "${arg}" in
    --with-arm)
      WITH_ARM=1
      ;;
    --skip-rosdep)
      SKIP_ROSDEP=1
      ;;
    *)
      echo "Unknown argument: ${arg}"
      echo "Usage: $0 [--with-arm] [--skip-rosdep]"
      exit 1
      ;;
  esac
done

if [[ ! -f /opt/ros/jazzy/setup.bash && ! -f /opt/ros/humble/setup.bash ]]; then
  echo "Install ROS 2 first. Expected /opt/ros/jazzy or /opt/ros/humble."
  exit 1
fi

mkdir -p "${SRC_DIR}"

clone_if_missing() {
  local repo_url="$1"
  local branch="$2"
  local target_dir="$3"

  if [[ -d "${target_dir}/.git" ]]; then
    echo "Using existing repo: ${target_dir}"
    return
  fi

  git clone --depth=1 --branch "${branch}" "${repo_url}" "${target_dir}"
}

clone_if_missing \
  "https://github.com/agilexrobotics/limo_ros2.git" \
  "humble" \
  "${SRC_DIR}/limo_ros2"

if [[ "${WITH_ARM}" -eq 1 ]]; then
  clone_if_missing \
    "https://github.com/elephantrobotics/mycobot_ros2.git" \
    "humble" \
    "${SRC_DIR}/mycobot_ros2"
fi

if grep -q 'VERSION_CODENAME=noble' /etc/os-release; then
  # The vendor limo_car package targets Gazebo Classic, which is not available
  # on Ubuntu 24.04 / ROS 2 Jazzy. Ignore it on this host and use Isaac Sim instead.
  touch "${SRC_DIR}/limo_ros2/limo_car/COLCON_IGNORE"
fi

if [[ "${SKIP_ROSDEP}" -eq 0 ]] && command -v rosdep >/dev/null 2>&1; then
  ROSDISTRO="jazzy"
  if [[ -f /opt/ros/humble/setup.bash && ! -f /opt/ros/jazzy/setup.bash ]]; then
    ROSDISTRO="humble"
  fi

  rosdep install \
    --from-paths "${SRC_DIR}" \
    --ignore-src \
    --rosdistro "${ROSDISTRO}" \
    -y \
    --skip-keys "gazebo gazebo_ros libgazebo_ros"
else
  echo "Skipping rosdep install."
fi

cat > "${WS_DIR}/build_limo_ws.sh" <<'EOF'
#!/usr/bin/env bash
set -eo pipefail

if [[ -f /opt/ros/jazzy/setup.bash ]]; then
  source /opt/ros/jazzy/setup.bash
elif [[ -f /opt/ros/humble/setup.bash ]]; then
  source /opt/ros/humble/setup.bash
else
  echo "ROS 2 is not installed."
  exit 1
fi

cd "${HOME}/limo_pro2_ws"
colcon build --symlink-install
EOF
chmod +x "${WS_DIR}/build_limo_ws.sh"

cat > "${WS_DIR}/source_limo_ws.sh" <<'EOF'
#!/usr/bin/env bash
set -eo pipefail

if [[ -f /opt/ros/jazzy/setup.bash ]]; then
  source /opt/ros/jazzy/setup.bash
elif [[ -f /opt/ros/humble/setup.bash ]]; then
  source /opt/ros/humble/setup.bash
else
  echo "ROS 2 is not installed."
  exit 1
fi

if [[ -f "${HOME}/limo_pro2_ws/install/setup.bash" ]]; then
  source "${HOME}/limo_pro2_ws/install/setup.bash"
fi
EOF
chmod +x "${WS_DIR}/source_limo_ws.sh"

echo
echo "Workspace is ready at ${WS_DIR}"
echo "Next:"
echo "  ${WS_DIR}/build_limo_ws.sh"
echo
echo "Real base launch:"
echo "  source ${WS_DIR}/source_limo_ws.sh"
echo "  ros2 launch limo_base start_limo.launch.py"
echo
if [[ "${WITH_ARM}" -eq 1 ]]; then
  echo "Optional arm launch example:"
  echo "  source ${WS_DIR}/source_limo_ws.sh"
  echo "  ros2 launch mycobot_280 simple_gui.launch.py port:=/dev/ttyACM0 baud:=115200"
fi
