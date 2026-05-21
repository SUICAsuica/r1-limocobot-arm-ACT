# LIMO Foxy Startup Guide

このメモは、LIMO 実機と PC を `ROS 2 Foxy / ROS_DOMAIN_ID=2` で 1 から立ち上げて、
接続確認と最小の前進確認まで行う手順をまとめたものです。

## 前提

- LIMO 側は `ROS 2 Foxy` が入っている
- LIMO 側のワークスペースに `limo_base` がある
- PC 側では `udocker` 上の Foxy を使う
- LIMO と PC は同じネットワークにいる

## 使う設定

- `ROS_DOMAIN_ID=2`
- `ROS_LOCALHOST_ONLY=0`

## 1. LIMO 側を起動する

LIMO 側では `demo_nodes_cpp talker` ではなく、車体本体のドライバを起動する。

```bash
source /opt/ros/foxy/setup.bash
source ~/limo_pro2_ws/install/setup.bash
export ROS_DOMAIN_ID=2
export ROS_LOCALHOST_ONLY=0
ros2 launch limo_base start_limo.launch.py port_name:=ttyUSB0 start_lidar:=true
```

### 補足

- `ttyUSB0` ではなく udev 名を使っている場合は `port_name:=ttylimo` のこともある
- LiDAR を上げたくないなら `start_lidar:=false`

## 2. LIMO 側で起動確認する

別ターミナルで確認する。

```bash
source /opt/ros/foxy/setup.bash
source ~/limo_pro2_ws/install/setup.bash
export ROS_DOMAIN_ID=2
export ROS_LOCALHOST_ONLY=0
ros2 node list
ros2 topic list
```

最低限、以下の一部または全部が見えてほしい。

- `/limo_base`
- `/ydlidar_ros2_driver_node`
- `/cmd_vel`
- `/odom`
- `/limo_status`
- `/scan`
- `/tf`
- `/tf_static`

## 3. PC 側で Foxy 環境を使う

この PC は Ubuntu 24.04 なので、ネイティブの `/opt/ros/foxy` ではなく `udocker` 上の Foxy を使う。

用意済みスクリプト:

- `~/run_ros2_foxy_udocker.sh`
- `~/check_limo_foxy_domain2_udocker.sh`

PC 側の接続確認:

```bash
bash ~/check_limo_foxy_domain2_udocker.sh
```

任意の Foxy コマンドを打つとき:

```bash
ROS_DOMAIN_ID=2 ROS_LOCALHOST_ONLY=0 ~/run_ros2_foxy_udocker.sh ros2 node list
ROS_DOMAIN_ID=2 ROS_LOCALHOST_ONLY=0 ~/run_ros2_foxy_udocker.sh ros2 topic list
ROS_DOMAIN_ID=2 ROS_LOCALHOST_ONLY=0 ~/run_ros2_foxy_udocker.sh ros2 topic echo /limo_status
```

## 4. PC 側から見えるべき状態

接続できていれば、PC 側から次が見える。

- node: `/limo_base`
- topic: `/cmd_vel`, `/odom`, `/limo_status`, `/scan`, `/tf`, `/tf_static`

もし `/talker` と `/chatter` しか見えないなら、それは `demo_nodes_cpp` が動いているだけで、
LIMO 本体ドライバは起動していない。

## 5. 安全に 1 回だけ前進確認する

PC 側からごく小さい速度を 1 回だけ送り、1 秒後に停止を 1 回送る。

```bash
ROS_DOMAIN_ID=2 ROS_LOCALHOST_ONLY=0 ~/run_ros2_foxy_udocker.sh bash -lc \
'source /opt/ros/foxy/setup.bash && \
ros2 topic pub --once /cmd_vel geometry_msgs/msg/Twist "{linear: {x: 0.10, y: 0.0, z: 0.0}, angular: {x: 0.0, y: 0.0, z: 0.0}}" && \
sleep 1 && \
ros2 topic pub --once /cmd_vel geometry_msgs/msg/Twist "{linear: {x: 0.0, y: 0.0, z: 0.0}, angular: {x: 0.0, y: 0.0, z: 0.0}}"'
```

## 6. よくある詰まり方

### `start_limo.launch.py` が見つからない

`limo_base` を含むワークスペースを source していない可能性が高い。

```bash
source /opt/ros/foxy/setup.bash
source ~/limo_pro2_ws/install/setup.bash
ros2 pkg list | grep limo
ros2 pkg prefix limo_base
```

### `/talker` と `/chatter` しか見えない

`demo_nodes_cpp talker` が動いているだけ。LIMO 本体ではない。

### PC 側で Foxy がない

この PC では `udocker` 上の Foxy を使う。直接 `/opt/ros/foxy/setup.bash` は使わない。

## 7. 最低限の確認コマンド一覧

LIMO 側:

```bash
source /opt/ros/foxy/setup.bash
source ~/limo_pro2_ws/install/setup.bash
export ROS_DOMAIN_ID=2
export ROS_LOCALHOST_ONLY=0
ros2 launch limo_base start_limo.launch.py port_name:=ttyUSB0 start_lidar:=true
```

PC 側:

```bash
bash ~/check_limo_foxy_domain2_udocker.sh
```

PC 側で topic 一覧:

```bash
ROS_DOMAIN_ID=2 ROS_LOCALHOST_ONLY=0 ~/run_ros2_foxy_udocker.sh ros2 topic list
```

PC 側で前進確認:

```bash
ROS_DOMAIN_ID=2 ROS_LOCALHOST_ONLY=0 ~/run_ros2_foxy_udocker.sh bash -lc \
'source /opt/ros/foxy/setup.bash && \
ros2 topic pub --once /cmd_vel geometry_msgs/msg/Twist "{linear: {x: 0.10, y: 0.0, z: 0.0}, angular: {x: 0.0, y: 0.0, z: 0.0}}" && \
sleep 1 && \
ros2 topic pub --once /cmd_vel geometry_msgs/msg/Twist "{linear: {x: 0.0, y: 0.0, z: 0.0}, angular: {x: 0.0, y: 0.0, z: 0.0}}"'
```
