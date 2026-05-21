#!/usr/bin/env python3
import argparse
import csv
from pathlib import Path


JOINTS = ["j1", "j2", "j3", "j4", "j5", "j6"]
ACTION_COLUMNS = [
    "seq",
    "pc_command_time_ns",
    "delta_j1",
    "delta_j2",
    "delta_j3",
    "delta_j4",
    "delta_j5",
    "delta_j6",
    "cmd_gripper",
]


def load_states(path: Path):
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def write_actions(path: Path, states: list[dict]):
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=ACTION_COLUMNS)
        writer.writeheader()

        for current, nxt in zip(states, states[1:]):
            row = {
                "seq": current["seq"],
                "pc_command_time_ns": current["pc_receive_time_ns"],
                "cmd_gripper": nxt.get("gripper", ""),
            }
            for joint in JOINTS:
                row[f"delta_{joint}"] = float(nxt[joint]) - float(current[joint])
            writer.writerow(row)


def main():
    parser = argparse.ArgumentParser(
        description="Generate actions.csv from manual-demo states.csv"
    )
    parser.add_argument("episode_dir", help="dataset/episode_0001")
    args = parser.parse_args()

    episode_dir = Path(args.episode_dir)
    states_path = episode_dir / "states.csv"
    actions_path = episode_dir / "actions.csv"

    states = load_states(states_path)
    if len(states) < 2:
        raise SystemExit("states.csv needs at least 2 rows")

    write_actions(actions_path, states)
    print(f"wrote {actions_path}")


if __name__ == "__main__":
    main()
