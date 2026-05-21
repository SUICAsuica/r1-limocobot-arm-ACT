#!/usr/bin/env python3
import argparse
import signal
import threading
import time
import urllib.request
from pathlib import Path

from dataset_logger import EpisodeLogger


class MjpegReader:
    def __init__(self, url: str):
        self.url = url
        self.latest_jpeg = None
        self.latest_capture_time = 0.0
        self.error = None
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)

    def start(self):
        self._thread.start()

    def stop(self):
        self._stop.set()
        self._thread.join(timeout=2.0)

    def latest(self):
        with self._lock:
            return self.latest_jpeg, self.latest_capture_time, self.error

    def _run(self):
        while not self._stop.is_set():
            try:
                self._read_stream()
            except Exception as exc:
                with self._lock:
                    self.error = str(exc)
                time.sleep(1.0)

    def _read_stream(self):
        request = urllib.request.Request(self.url, headers={"Cache-Control": "no-store"})
        with urllib.request.urlopen(request, timeout=5.0) as response:
            buffer = b""
            while not self._stop.is_set():
                chunk = response.read(8192)
                if not chunk:
                    raise RuntimeError("MJPEG stream closed")
                buffer += chunk

                while True:
                    start = buffer.find(b"\xff\xd8")
                    end = buffer.find(b"\xff\xd9", start + 2)
                    if start < 0 or end < 0:
                        if len(buffer) > 2_000_000:
                            buffer = buffer[-200_000:]
                        break

                    jpeg = buffer[start : end + 2]
                    header = buffer[:start].decode("latin1", errors="ignore")
                    capture_time = parse_capture_time(header)
                    buffer = buffer[end + 2 :]

                    with self._lock:
                        self.latest_jpeg = jpeg
                        self.latest_capture_time = capture_time
                        self.error = None


def parse_capture_time(header: str):
    for line in header.splitlines():
        if line.lower().startswith("x-capture-time:"):
            try:
                return float(line.split(":", 1)[1].strip())
            except ValueError:
                return 0.0
    return 0.0


def get_json(url: str):
    request = urllib.request.Request(url, headers={"Cache-Control": "no-store"})
    with urllib.request.urlopen(request, timeout=2.0) as response:
        import json

        return json.loads(response.read().decode("utf-8"))


def make_payload(seq: int, state: dict, image_capture_time: float):
    arm = state.get("arm") or {}
    camera = state.get("camera") or {}
    angles = arm.get("angles") or arm.get("joint_angles")
    if not angles:
        raise ValueError(f"state has no arm angles: {state}")

    stamp = arm.get("stamp") or camera.get("stamp") or image_capture_time or time.time()
    return {
        "seq": seq,
        "limo_time_ns": int(float(stamp) * 1_000_000_000),
        "joint_angles": angles[:6],
        "gripper": arm.get("gripper_value", ""),
    }


def main():
    parser = argparse.ArgumentParser(
        description="Pull LIMO HTTP live stream and save dataset episodes on the PC"
    )
    parser.add_argument("--limo-url", default="http://192.168.0.161:8001")
    parser.add_argument("--dataset-dir", default="dataset")
    parser.add_argument("--episode-id", default=None)
    parser.add_argument("--task", default="manual_demo")
    parser.add_argument("--robot", default="limo_cobot_mycobot280")
    parser.add_argument("--hz", type=float, default=10.0)
    parser.add_argument("--duration", type=float, default=0.0, help="0 means until Ctrl-C")
    parser.add_argument(
        "--success",
        choices=["true", "false"],
        default=None,
        help="Set episode success label without an interactive prompt",
    )
    parser.add_argument("--notes", default="", help="Notes saved to meta.json")
    args = parser.parse_args()

    base_url = args.limo_url.rstrip("/")
    state_url = f"{base_url}/state.json"
    stream_url = f"{base_url}/stream.mjpg"

    logger = EpisodeLogger(
        dataset_dir=Path(args.dataset_dir),
        task=args.task,
        robot=args.robot,
        control_hz=args.hz,
    )
    episode_id = logger.start(args.episode_id)
    mjpeg = MjpegReader(stream_url)
    mjpeg.start()

    stop_requested = False

    def request_stop(_signum, _frame):
        nonlocal stop_requested
        stop_requested = True

    signal.signal(signal.SIGINT, request_stop)
    signal.signal(signal.SIGTERM, request_stop)

    print(f"started {episode_id}")
    print(f"state:  {state_url}")
    print(f"stream: {stream_url}")
    print("press Ctrl-C to stop, then label success/failure in meta.json")

    seq = 0
    skipped = 0
    start_time = time.monotonic()
    next_time = start_time

    try:
        while not stop_requested:
            now = time.monotonic()
            if args.duration > 0 and now - start_time >= args.duration:
                break
            if now < next_time:
                time.sleep(min(0.01, next_time - now))
                continue
            next_time += 1.0 / args.hz

            state = get_json(state_url)
            image_bytes, image_capture_time, stream_error = mjpeg.latest()
            if stream_error:
                print(f"stream warning: {stream_error}")
            if image_bytes is None:
                print("waiting for first image...")
                continue

            try:
                payload = make_payload(seq, state, image_capture_time)
            except ValueError as exc:
                skipped += 1
                if skipped == 1 or skipped % max(1, int(args.hz)) == 0:
                    arm = state.get("arm") or {}
                    print(
                        f"skipping frame: {exc}; "
                        f"arm_error={arm.get('error')} skipped={skipped}"
                    )
                continue

            logger.add_frame(payload, image_bytes)
            seq += 1

            if seq % max(1, int(args.hz)) == 0:
                status = logger.status()
                print(
                    f"frames={status['frames']} dropped={status['dropped']} "
                    f"skipped={skipped} joints={payload['joint_angles']} "
                    f"gripper={payload['gripper']}"
                )
    finally:
        mjpeg.stop()
        success = parse_success_arg(args.success)
        notes = args.notes
        if args.success is None:
            success, notes = ask_episode_label(default_notes=args.notes)
        logger.stop(success=success, notes=notes)
        print(f"stopped {episode_id}, frames={seq}, skipped={skipped}")


def parse_success_arg(value: str | None):
    if value is None:
        return None
    return value == "true"


def ask_episode_label(default_notes: str = ""):
    while True:
        answer = input("success? [y/n/skip]: ").strip().lower()
        if answer in {"y", "yes", "true", "1"}:
            success = True
            break
        if answer in {"n", "no", "false", "0"}:
            success = False
            break
        if answer in {"", "s", "skip"}:
            return None, default_notes
        print("please enter y, n, or skip")

    notes = input(f"notes [{default_notes}]: ").strip()
    return success, notes or default_notes


if __name__ == "__main__":
    main()
