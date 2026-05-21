# LIMO Foxy Bringup Memo

このメモは、今回実際に通った手順をそのまま残したものです。

- LIMO 実機側: `ROS 2 Foxy`
- PC 側: Ubuntu 24.04
- PC 側 Foxy 実行環境: `udocker`
- ROS 設定:
  - `ROS_DOMAIN_ID=2`
  - `ROS_LOCALHOST_ONLY=0`

## 1. LIMO 実機側を起動

```bash
source /opt/ros/foxy/setup.bash
source ~/limo_pro2_ws/install/setup.bash
export ROS_DOMAIN_ID=2
export ROS_LOCALHOST_ONLY=0
ros2 launch limo_base start_limo.launch.py port_name:=ttyUSB0 start_lidar:=true
```

補足:

- 環境によっては `port_name:=ttylimo`
- LiDAR を上げないなら `start_lidar:=false`

## 2. PC 側の基本確認

PC 側で使うスクリプト:

- `~/run_ros2_foxy_udocker.sh`
- `~/check_limo_foxy_domain2_udocker.sh`

疎通確認:

```bash
bash ~/check_limo_foxy_domain2_udocker.sh
```

個別確認:

```bash
ROS_DOMAIN_ID=2 ROS_LOCALHOST_ONLY=0 ~/run_ros2_foxy_udocker.sh ros2 node list
ROS_DOMAIN_ID=2 ROS_LOCALHOST_ONLY=0 ~/run_ros2_foxy_udocker.sh ros2 topic list
```

今回 PC 側から見えた主なノード:

- `/limo_base`
- `/ydlidar_ros2_driver_node`
- `/camera/camera`
- `/camera_container`

今回 PC 側から見えた主なトピック:

- `/cmd_vel`
- `/limo_status`
- `/odom`
- `/scan`
- `/tf`
- `/tf_static`
- `/camera/color/image_raw`
- `/camera/color/camera_info`
- `/camera/depth/image_raw`
- `/camera/depth/camera_info`
- `/camera/depth/points`

## 3. カメラ配信の確認

トピック自体の確認:

```bash
ROS_DOMAIN_ID=2 ROS_LOCALHOST_ONLY=0 ~/run_ros2_foxy_udocker.sh bash -lc \
'source /opt/ros/foxy/setup.bash && ros2 topic info /camera/color/image_raw'
```

`camera_info` が流れているか確認:

```bash
ROS_DOMAIN_ID=2 ROS_LOCALHOST_ONLY=0 ~/run_ros2_foxy_udocker.sh bash -lc \
'source /opt/ros/foxy/setup.bash && timeout 5 ros2 topic echo /camera/color/camera_info'
```

今回確認できた内容:

- `/camera/color/image_raw` は `sensor_msgs/msg/Image`
- Publisher count は `1`
- `/camera/color/camera_info` は連続受信
- 解像度は `640x480`

## 4. PC 側 viewer を追加

初期状態では `rqt_image_view` が入っていなかったため追加した。

```bash
ROS_DOMAIN_ID=2 ROS_LOCALHOST_ONLY=0 ~/run_ros2_foxy_udocker.sh bash -lc \
'apt-get update'

ROS_DOMAIN_ID=2 ROS_LOCALHOST_ONLY=0 ~/run_ros2_foxy_udocker.sh bash -lc \
'apt-get install -y ros-foxy-rqt-image-view ros-foxy-image-view'
```

途中で `dpkg` が以下で詰まる場合があった:

- `unknown system group 'messagebus' in statoverride file`

その場合の復旧:

```bash
ROS_DOMAIN_ID=2 ROS_LOCALHOST_ONLY=0 ~/run_ros2_foxy_udocker.sh bash -lc \
'groupadd -r messagebus || true'

ROS_DOMAIN_ID=2 ROS_LOCALHOST_ONLY=0 ~/run_ros2_foxy_udocker.sh bash -lc \
'dpkg-statoverride --remove /usr/lib/dbus-1.0/dbus-daemon-launch-helper || true'

ROS_DOMAIN_ID=2 ROS_LOCALHOST_ONLY=0 ~/run_ros2_foxy_udocker.sh bash -lc \
'dpkg --configure -a'
```

その後もう一度 install を実行する。

## 5. X11 を通すための udocker ラッパー修正

`~/run_ros2_foxy_udocker.sh` は、GUI アプリを出すために以下を通す必要があった。

- `DISPLAY`
- `XAUTHORITY`
- `/tmp/.X11-unix`
- `XAUTHORITY` ファイル自体の bind

現在のラッパーで GUI 表示可能。

## 6. 画像 viewer の起動

`rqt_image_view` はトピック選択が扱いにくかったため、`image_view` を直接使う形にした。

カラー画像:

```bash
ROS_DOMAIN_ID=2 ROS_LOCALHOST_ONLY=0 ~/run_ros2_foxy_udocker.sh bash -lc \
'source /opt/ros/foxy/setup.bash && LIBGL_ALWAYS_SOFTWARE=1 ros2 run image_view image_view --ros-args -r image:=/camera/color/image_raw'
```

深度画像:

```bash
ROS_DOMAIN_ID=2 ROS_LOCALHOST_ONLY=0 ~/run_ros2_foxy_udocker.sh bash -lc \
'source /opt/ros/foxy/setup.bash && LIBGL_ALWAYS_SOFTWARE=1 ros2 run image_view image_view --ros-args -r image:=/camera/depth/image_raw'
```

補足:

- `LIBGL_ALWAYS_SOFTWARE=1` を付けると、GL 周りの相性問題を避けやすい
- `dbind` や `canberra-gtk-module` の警告は出ても、viewer 自体は動くことがある

## 7. 最低限の確認セット

LIMO 実機側:

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

カラー画像 viewer:

```bash
ROS_DOMAIN_ID=2 ROS_LOCALHOST_ONLY=0 ~/run_ros2_foxy_udocker.sh bash -lc \
'source /opt/ros/foxy/setup.bash && LIBGL_ALWAYS_SOFTWARE=1 ros2 run image_view image_view --ros-args -r image:=/camera/color/image_raw'
```

## 8. 次にやるなら

- 前進確認:

```bash
ROS_DOMAIN_ID=2 ROS_LOCALHOST_ONLY=0 ~/run_ros2_foxy_udocker.sh bash -lc \
'source /opt/ros/foxy/setup.bash && \
ros2 topic pub --once /cmd_vel geometry_msgs/msg/Twist "{linear: {x: 0.10, y: 0.0, z: 0.0}, angular: {x: 0.0, y: 0.0, z: 0.0}}" && \
sleep 1 && \
ros2 topic pub --once /cmd_vel geometry_msgs/msg/Twist "{linear: {x: 0.0, y: 0.0, z: 0.0}, angular: {x: 0.0, y: 0.0, z: 0.0}}"'
```

- 深度画像 viewer 起動
- `limo_status` と `odom` の中身確認
