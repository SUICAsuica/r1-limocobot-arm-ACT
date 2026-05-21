#!/usr/bin/env python3
import argparse
import sys

import cv2
import numpy as np
import rclpy
from rclpy.node import Node
from rclpy.qos import QoSProfile, ReliabilityPolicy, DurabilityPolicy, HistoryPolicy
from sensor_msgs.msg import CompressedImage, Image


class LimoCameraView(Node):
    def __init__(self, topic):
        super().__init__("limo_camera_view")
        self.topic = topic
        self.frame_count = 0
        self.last_stamp = None
        qos = QoSProfile(
            history=HistoryPolicy.KEEP_LAST,
            depth=5,
            reliability=ReliabilityPolicy.RELIABLE,
            durability=DurabilityPolicy.VOLATILE,
        )

        if topic.endswith("/compressed"):
            self.sub = self.create_subscription(CompressedImage, topic, self.on_compressed, qos)
        else:
            self.sub = self.create_subscription(Image, topic, self.on_raw, qos)

        self.get_logger().info(f"subscribing: {topic}")
        self.get_logger().info("press q in the image window to quit")

    def show(self, frame):
        if frame is None:
            return
        self.frame_count += 1
        if self.frame_count == 1:
            self.get_logger().info(f"first frame: {frame.shape[1]}x{frame.shape[0]}")
        cv2.imshow("LIMO camera", frame)
        if cv2.waitKey(1) & 0xFF == ord("q"):
            rclpy.shutdown()

    def on_compressed(self, msg):
        data = np.frombuffer(msg.data, dtype=np.uint8)
        frame = cv2.imdecode(data, cv2.IMREAD_COLOR)
        self.show(frame)

    def on_raw(self, msg):
        frame = np.frombuffer(msg.data, dtype=np.uint8)
        if msg.encoding in ("bgr8", "rgb8"):
            frame = frame.reshape((msg.height, msg.width, 3))
            if msg.encoding == "rgb8":
                frame = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)
        elif msg.encoding == "mono8":
            frame = frame.reshape((msg.height, msg.width))
        else:
            self.get_logger().warn(f"unsupported raw encoding: {msg.encoding}")
            return
        self.show(frame)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--topic",
        default="/limo/rgb/image_raw/compressed",
        help="Image topic to display",
    )
    args = parser.parse_args()

    rclpy.init()
    node = LimoCameraView(args.topic)
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        cv2.destroyAllWindows()
        if rclpy.ok():
            rclpy.shutdown()
    return 0


if __name__ == "__main__":
    sys.exit(main())
