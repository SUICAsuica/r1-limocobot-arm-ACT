#!/usr/bin/env python3
import argparse
import base64
import csv
import json
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse


STATE_COLUMNS = [
    "seq",
    "limo_time_ns",
    "pc_receive_time_ns",
    "j1",
    "j2",
    "j3",
    "j4",
    "j5",
    "j6",
    "gripper",
    "image_path",
]


class EpisodeLogger:
    def __init__(self, dataset_dir: Path, task: str, robot: str, control_hz: float):
        self.dataset_dir = dataset_dir
        self.task = task
        self.robot = robot
        self.control_hz = control_hz
        self.episode_dir = None
        self.csv_file = None
        self.csv_writer = None
        self.last_seq = None
        self.frames = 0
        self.dropped = 0
        self.success = None
        self.notes = ""

        self.dataset_dir.mkdir(parents=True, exist_ok=True)

    def start(self, episode_id: str | None = None):
        if self.csv_file:
            self.stop()

        if episode_id is None:
            episode_id = self._next_episode_id()

        self.episode_dir = self.dataset_dir / episode_id
        (self.episode_dir / "rgb").mkdir(parents=True, exist_ok=False)

        self.csv_file = (self.episode_dir / "states.csv").open(
            "w", newline="", encoding="utf-8"
        )
        self.csv_writer = csv.DictWriter(self.csv_file, fieldnames=STATE_COLUMNS)
        self.csv_writer.writeheader()
        self.csv_file.flush()

        self.last_seq = None
        self.frames = 0
        self.dropped = 0
        self.success = None
        self.notes = ""
        self._write_meta()
        return self.episode_dir.name

    def stop(self, success: bool | None = None, notes: str | None = None):
        if success is not None:
            self.success = success
        if notes is not None:
            self.notes = notes
        self._write_meta()

        if self.csv_file:
            self.csv_file.close()
            self.csv_file = None
            self.csv_writer = None

        episode_id = self.episode_dir.name if self.episode_dir else None
        self.episode_dir = None
        return episode_id

    def label(self, success: bool, notes: str = ""):
        self.success = success
        self.notes = notes
        self._write_meta()

    def add_frame(self, payload: dict, image_bytes: bytes | None):
        if not self.csv_writer or not self.episode_dir:
            raise RuntimeError("episode is not running. call /start first")

        seq = int(payload.get("seq", self.frames))
        angles = payload.get("joint_angles") or payload.get("angles")
        if not isinstance(angles, list) or len(angles) < 6:
            raise ValueError("joint_angles must be a list with at least 6 values")

        gripper = payload.get("gripper", "")
        limo_time_ns = int(payload.get("limo_time_ns", payload.get("timestamp_ns", 0)))
        pc_receive_time_ns = time.time_ns()

        if self.last_seq is not None and seq > self.last_seq + 1:
            self.dropped += seq - self.last_seq - 1
        self.last_seq = seq

        image_path = ""
        if image_bytes:
            image_path = f"rgb/{seq:06d}.jpg"
            (self.episode_dir / image_path).write_bytes(image_bytes)

        row = {
            "seq": seq,
            "limo_time_ns": limo_time_ns,
            "pc_receive_time_ns": pc_receive_time_ns,
            "j1": angles[0],
            "j2": angles[1],
            "j3": angles[2],
            "j4": angles[3],
            "j5": angles[4],
            "j6": angles[5],
            "gripper": gripper,
            "image_path": image_path,
        }
        self.csv_writer.writerow(row)
        self.csv_file.flush()
        self.frames += 1
        self._write_meta()
        return row

    def status(self):
        return {
            "running": self.csv_writer is not None,
            "episode_id": self.episode_dir.name if self.episode_dir else None,
            "frames": self.frames,
            "dropped": self.dropped,
            "success": self.success,
            "notes": self.notes,
        }

    def _next_episode_id(self):
        max_id = 0
        for path in self.dataset_dir.glob("episode_*"):
            if path.is_dir():
                try:
                    max_id = max(max_id, int(path.name.split("_")[-1]))
                except ValueError:
                    pass
        return f"episode_{max_id + 1:04d}"

    def _write_meta(self):
        if not self.episode_dir:
            return
        meta = {
            "task": self.task,
            "robot": self.robot,
            "control_hz": self.control_hz,
            "camera": "rgb",
            "success": self.success,
            "notes": self.notes,
            "frames": self.frames,
            "dropped": self.dropped,
            "updated_time_ns": time.time_ns(),
        }
        (self.episode_dir / "meta.json").write_text(
            json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8"
        )


def make_handler(logger: EpisodeLogger):
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            parsed = urlparse(self.path)
            if parsed.path == "/status":
                self._send_json(logger.status())
                return
            self._send_json({"error": "not found"}, status=404)

        def do_POST(self):
            parsed = urlparse(self.path)
            if parsed.path == "/start":
                query = parse_qs(parsed.query)
                episode_id = first(query, "episode_id")
                self._send_json({"episode_id": logger.start(episode_id), **logger.status()})
                return

            if parsed.path == "/stop":
                data, _ = self._read_request()
                success = parse_success(data.get("success")) if "success" in data else None
                notes = str(data.get("notes", "")) if data else None
                episode_id = logger.stop(success=success, notes=notes)
                self._send_json({"stopped": episode_id, **logger.status()})
                return

            if parsed.path == "/label":
                data, _ = self._read_request()
                if "success" not in data:
                    self._send_json({"error": "success is required"}, status=400)
                    return
                logger.label(parse_success(data["success"]), str(data.get("notes", "")))
                self._send_json(logger.status())
                return

            if parsed.path == "/frame":
                try:
                    data, image_bytes = self._read_request()
                    row = logger.add_frame(data, image_bytes)
                except Exception as exc:
                    self._send_json({"error": str(exc)}, status=400)
                    return
                self._send_json({"ok": True, "row": row, **logger.status()})
                return

            self._send_json({"error": "not found"}, status=404)

        def log_message(self, fmt, *args):
            status = logger.status()
            print(
                f"[{time.strftime('%H:%M:%S')}] {self.client_address[0]} "
                f"{fmt % args} episode={status['episode_id']} frames={status['frames']}"
            )

        def _read_request(self):
            content_length = int(self.headers.get("Content-Length", "0"))
            body = self.rfile.read(content_length)
            content_type = self.headers.get("Content-Type", "")

            if "application/json" in content_type:
                data = json.loads(body.decode("utf-8")) if body else {}
                image_bytes = decode_image_from_json(data)
                return data, image_bytes

            if "multipart/form-data" in content_type:
                return parse_multipart(content_type, body)

            if not body:
                return {}, None

            data = json.loads(body.decode("utf-8"))
            image_bytes = decode_image_from_json(data)
            return data, image_bytes

        def _send_json(self, data, status=200):
            body = json.dumps(data, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    return Handler


def first(query: dict, key: str):
    values = query.get(key)
    return values[0] if values else None


def parse_success(value):
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return bool(value)
    return str(value).lower() in {"1", "true", "yes", "success", "ok"}


def decode_image_from_json(data: dict):
    value = data.pop("image_b64", None) or data.pop("image_base64", None)
    if value is None:
        return None
    if "," in value and value.startswith("data:"):
        value = value.split(",", 1)[1]
    return base64.b64decode(value)


def parse_multipart(content_type: str, body: bytes):
    import cgi
    import io

    environ = {
        "REQUEST_METHOD": "POST",
        "CONTENT_TYPE": content_type,
        "CONTENT_LENGTH": str(len(body)),
    }
    form = cgi.FieldStorage(fp=io.BytesIO(body), environ=environ, keep_blank_values=True)

    data = {}
    image_bytes = None
    for key in form.keys():
        item = form[key]
        if key in {"image", "file", "rgb"} and getattr(item, "file", None):
            image_bytes = item.file.read()
        elif key == "json":
            data.update(json.loads(item.value))
        else:
            value = item.value
            if key == "joint_angles":
                value = json.loads(value)
            data[key] = value
    return data, image_bytes


def main():
    parser = argparse.ArgumentParser(description="PC-side HTTP dataset logger")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--dataset-dir", default="dataset")
    parser.add_argument("--task", default="manual_demo")
    parser.add_argument("--robot", default="limo_cobot_mycobot280")
    parser.add_argument("--control-hz", type=float, default=10.0)
    args = parser.parse_args()

    logger = EpisodeLogger(
        dataset_dir=Path(args.dataset_dir),
        task=args.task,
        robot=args.robot,
        control_hz=args.control_hz,
    )
    server = ThreadingHTTPServer((args.host, args.port), make_handler(logger))

    print(f"dataset logger listening on http://{args.host}:{args.port}")
    print("POST /start, POST /frame, POST /label, POST /stop, GET /status")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nstopping logger")
    finally:
        logger.stop()
        server.server_close()


if __name__ == "__main__":
    main()
