#!/usr/bin/env python3
import argparse
import csv
import json
import shutil
from pathlib import Path

import numpy as np
from PIL import Image
from lerobot.datasets.lerobot_dataset import LeRobotDataset


STATE_KEYS = ["j1", "j2", "j3", "j4", "j5", "j6", "gripper"]
DELTA_ACTION_KEYS = ["delta_j1", "delta_j2", "delta_j3", "delta_j4", "delta_j5", "delta_j6", "cmd_gripper"]
TARGET_ACTION_KEYS = ["target_j1", "target_j2", "target_j3", "target_j4", "target_j5", "target_j6", "target_gripper"]


def read_csv(path: Path) -> list[dict]:
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def parse_range(value: str) -> list[int]:
    episodes = []
    for part in value.split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            start, end = part.split("-", 1)
            episodes.extend(range(int(start), int(end) + 1))
        else:
            episodes.append(int(part))
    return episodes


def load_rgb(path: Path) -> np.ndarray:
    image = Image.open(path).convert("RGB")
    return np.asarray(image)


def row_state(row: dict) -> np.ndarray:
    return np.array([float(row[key]) for key in STATE_KEYS], dtype=np.float32)


def expert_action_from_states(current: dict, future: dict) -> np.ndarray:
    deltas = [float(future[key]) - float(current[key]) for key in STATE_KEYS[:6]]
    return np.array([*deltas, float(future["gripper"])], dtype=np.float32)


def target_action_from_state(future: dict) -> np.ndarray:
    return np.array([float(future[key]) for key in STATE_KEYS], dtype=np.float32)


def main():
    parser = argparse.ArgumentParser(description="Convert LIMO/myCobot CSV episodes to LeRobotDataset")
    parser.add_argument("--source", default="/home/shori/dataset")
    parser.add_argument("--episodes", default="11-22")
    parser.add_argument("--repo-id", default="local/limo_cobot_center")
    parser.add_argument("--root", default="/home/shori/lerobot_datasets/limo_cobot_center")
    parser.add_argument("--task", default="grasp object from center")
    parser.add_argument("--fps", type=int, default=10)
    parser.add_argument(
        "--action-horizon-frames",
        type=int,
        default=1,
        help="Use state[t+horizon] - state[t] as the expert action.",
    )
    parser.add_argument(
        "--action-mode",
        choices=["delta", "target"],
        default="delta",
        help="delta: action=state[t+h]-state[t]. target: action=state[t+h].",
    )
    parser.add_argument("--include-failures", action="store_true")
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()

    source = Path(args.source)
    root = Path(args.root)
    if root.exists():
        if not args.overwrite:
            raise SystemExit(f"{root} already exists. Use --overwrite to replace it.")
        shutil.rmtree(root)

    features = {
        "observation.state": {
            "dtype": "float32",
            "shape": (7,),
            "names": STATE_KEYS,
        },
        "observation.images.rgb": {
            "dtype": "video",
            "shape": (480, 640, 3),
            "names": ["height", "width", "channels"],
        },
        "action": {
            "dtype": "float32",
            "shape": (7,),
            "names": DELTA_ACTION_KEYS if args.action_mode == "delta" else TARGET_ACTION_KEYS,
        },
    }

    dataset = LeRobotDataset.create(
        repo_id=args.repo_id,
        fps=args.fps,
        features=features,
        root=root,
        robot_type="limo_cobot_mycobot280",
        use_videos=True,
    )

    converted = 0
    skipped = []
    for episode_num in parse_range(args.episodes):
        episode_dir = source / f"episode_{episode_num:04d}"
        meta_path = episode_dir / "meta.json"
        states_path = episode_dir / "states.csv"
        if not meta_path.exists() or not states_path.exists():
            skipped.append((episode_num, "missing files"))
            continue

        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        if meta.get("success") is not True and not args.include_failures:
            skipped.append((episode_num, f"success={meta.get('success')}"))
            continue

        states = read_csv(states_path)
        usable = len(states) - args.action_horizon_frames
        if usable <= 0:
            skipped.append((episode_num, "no usable frames"))
            continue

        for idx in range(usable):
            state = states[idx]
            future_state = states[idx + args.action_horizon_frames]
            image_path = episode_dir / state["image_path"]
            if not image_path.exists():
                raise FileNotFoundError(image_path)

            dataset.add_frame(
                {
                    "observation.state": row_state(state),
                    "observation.images.rgb": load_rgb(image_path),
                    "action": (
                        expert_action_from_states(state, future_state)
                        if args.action_mode == "delta"
                        else target_action_from_state(future_state)
                    ),
                },
                task=args.task,
                timestamp=idx / args.fps,
            )
        dataset.save_episode()
        converted += 1
        print(f"converted episode_{episode_num:04d}: {usable} frames")

    if dataset.image_writer is not None:
        dataset.stop_image_writer()

    print(f"saved LeRobot dataset: {root}")
    print(f"converted episodes: {converted}")
    if skipped:
        print("skipped:")
        for episode_num, reason in skipped:
            print(f"  episode_{episode_num:04d}: {reason}")


if __name__ == "__main__":
    main()
