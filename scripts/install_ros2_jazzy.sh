#!/usr/bin/env bash
set -euo pipefail

if [[ "${EUID}" -eq 0 ]]; then
  echo "Run this script as your normal user, not as root."
  exit 1
fi

if ! grep -q 'Ubuntu 24.04' /etc/os-release; then
  echo "This script is intended for Ubuntu 24.04."
  exit 1
fi

need_cmd() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "Missing required command: $1"
    exit 1
  fi
}

need_cmd sudo
need_cmd dpkg
need_cmd apt-get

fetch_to_file() {
  local url="$1"
  local output="$2"

  if command -v curl >/dev/null 2>&1; then
    curl -L -o "${output}" "${url}"
  elif command -v wget >/dev/null 2>&1; then
    wget -O "${output}" "${url}"
  else
    echo "Missing required command: curl or wget"
    exit 1
  fi
}

fetch_text() {
  local url="$1"

  if command -v curl >/dev/null 2>&1; then
    curl -s "${url}"
  elif command -v wget >/dev/null 2>&1; then
    wget -qO- "${url}"
  else
    echo "Missing required command: curl or wget"
    exit 1
  fi
}

if [[ -f /opt/ros/jazzy/setup.bash ]]; then
  echo "ROS 2 Jazzy is already installed at /opt/ros/jazzy"
else
  echo "Installing ROS 2 Jazzy apt source package"
  ROS_APT_SOURCE_VERSION=$(
    fetch_text https://api.github.com/repos/ros-infrastructure/ros-apt-source/releases/latest \
    | grep -Po '"tag_name": "\K.*?(?=")'
  )
  fetch_to_file \
    "https://github.com/ros-infrastructure/ros-apt-source/releases/download/${ROS_APT_SOURCE_VERSION}/ros2-apt-source_${ROS_APT_SOURCE_VERSION}.noble_all.deb" \
    /tmp/ros2-apt-source.deb

  sudo dpkg -i /tmp/ros2-apt-source.deb
  sudo apt-get update
  sudo apt-get install -y \
    ros-jazzy-desktop \
    python3-colcon-common-extensions \
    python3-rosdep \
    python3-vcstool \
    python3-argcomplete \
    python3-pip \
    git
fi

if [[ ! -f /etc/ros/rosdep/sources.list.d/20-default.list ]]; then
  echo "Initializing rosdep"
  sudo rosdep init
fi

rosdep update

if ! grep -Fq 'source /opt/ros/jazzy/setup.bash' "${HOME}/.bashrc"; then
  echo 'source /opt/ros/jazzy/setup.bash' >> "${HOME}/.bashrc"
fi

echo
echo "ROS 2 Jazzy setup finished."
echo "Open a new shell or run:"
echo "  source /opt/ros/jazzy/setup.bash"
