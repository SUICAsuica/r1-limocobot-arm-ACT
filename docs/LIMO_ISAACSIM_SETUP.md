# LIMO Pro 2 + Isaac Sim notes

## What works well on this machine

- Host OS: Ubuntu 24.04.4
- GPU: RTX 4060 Ti
- Driver: 580.126.09
- Isaac Sim target: 5.1.0 standalone
- ROS target on host: Jazzy

## Important compatibility point

AgileX `limo_ros2` is published for `Ubuntu 22.04 + ROS 2 Humble`.
Its `limo_car` package uses Gazebo Classic. Gazebo Classic is not the supported
simulator path for `Ubuntu 24.04 + ROS 2 Jazzy`, so this workspace ignores
`limo_car` on this host.

For this machine, the practical split is:

1. Use Isaac Sim on the Ubuntu 24.04 host.
2. Use ROS 2 Jazzy on the host for bridge logic and visualization.
3. Use the vendor LIMO base packages for the real robot topics and URDF.
4. Use the optional myCobot ROS 2 package only if your LIMO Pro 2 actually has the arm installed.

## Files added in this home directory

- `install_isaacsim_5_1.sh`
- `install_ros2_jazzy.sh`
- `setup_limo_pro2_ws.sh`

## Recommended order

1. `bash ~/install_ros2_jazzy.sh`
2. `bash ~/setup_limo_pro2_ws.sh`
3. `~/limo_pro2_ws/build_limo_ws.sh`
4. `bash ~/install_isaacsim_5_1.sh`

If your unit includes the optional arm:

1. `bash ~/setup_limo_pro2_ws.sh --with-arm`
2. `~/limo_pro2_ws/build_limo_ws.sh`

## Likely runtime flow

Real robot:

```bash
source ~/limo_pro2_ws/source_limo_ws.sh
ros2 launch limo_base start_limo.launch.py
```

Optional arm:

```bash
source ~/limo_pro2_ws/source_limo_ws.sh
ros2 launch mycobot_280 simple_gui.launch.py port:=/dev/ttyACM0 baud:=115200
```

Isaac Sim:

```bash
cd ~/isaacsim
./isaac-sim.selector.sh
```

## References

- Isaac Sim ROS 2 install docs:
  https://docs.isaacsim.omniverse.nvidia.com/latest/installation/install_ros.html
- ROS 2 Jazzy Ubuntu 24.04 install docs:
  https://docs.ros.org/en/jazzy/Installation/Ubuntu-Install-Debs.html
- AgileX LIMO ROS 2 repo:
  https://github.com/agilexrobotics/limo_ros2
- AgileX LIMO Pro manual repo:
  https://github.com/agilexrobotics/limo_pro_doc
- Elephant Robotics myCobot ROS 2 repo:
  https://github.com/elephantrobotics/mycobot_ros2
