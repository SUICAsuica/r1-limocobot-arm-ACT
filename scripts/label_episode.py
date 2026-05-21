#!/usr/bin/env python3
import argparse
import json
import time
from pathlib import Path


def parse_success(value: str):
    value = value.lower()
    if value in {"true", "1", "yes", "y", "success", "ok"}:
        return True
    if value in {"false", "0", "no", "n", "failure", "fail"}:
        return False
    raise argparse.ArgumentTypeError("success must be true or false")


def main():
    parser = argparse.ArgumentParser(description="Set success/failure label in meta.json")
    parser.add_argument("episode_dir", help="Example: /home/shori/dataset/episode_0009")
    parser.add_argument("success", type=parse_success, help="true or false")
    parser.add_argument("--notes", default=None)
    args = parser.parse_args()

    meta_path = Path(args.episode_dir) / "meta.json"
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    meta["success"] = args.success
    if args.notes is not None:
        meta["notes"] = args.notes
    meta["updated_time_ns"] = time.time_ns()
    meta_path.write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"updated {meta_path}: success={args.success}")


if __name__ == "__main__":
    main()
