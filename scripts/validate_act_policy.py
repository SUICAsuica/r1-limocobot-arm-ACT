#!/usr/bin/env python3
import argparse
from pathlib import Path

import numpy as np
import torch
from torch.utils.data import DataLoader

from lerobot.datasets.lerobot_dataset import LeRobotDataset
from lerobot.policies.act.modeling_act import ACTPolicy


def evaluate(
    policy_path: Path,
    dataset_root: Path,
    repo_id: str,
    batch_size: int,
    device: str,
    fps: int,
    chunk_size: int,
):
    policy = ACTPolicy.from_pretrained(str(policy_path))
    policy.to(device)
    policy.train()

    dataset = LeRobotDataset(
        repo_id,
        root=dataset_root,
        video_backend="pyav",
        delta_timestamps={"action": [i / fps for i in range(chunk_size)]},
    )
    loader = DataLoader(dataset, batch_size=batch_size, shuffle=False, num_workers=0)

    losses, l1s, kls = [], [], []
    with torch.no_grad():
        for batch in loader:
            batch = {k: v.to(device) if hasattr(v, "to") else v for k, v in batch.items()}
            loss, out = policy.forward(batch)
            losses.append(float(loss.detach().cpu()))
            l1s.append(float(out["l1_loss"]))
            kls.append(float(out["kld_loss"]))

    return {
        "frames": len(dataset),
        "episodes": dataset.num_episodes,
        "loss": float(np.mean(losses)),
        "l1": float(np.mean(l1s)),
        "kl": float(np.mean(kls)),
    }


def main():
    parser = argparse.ArgumentParser(description="Evaluate ACT checkpoint loss on a LeRobotDataset")
    parser.add_argument("--policy-path", required=True)
    parser.add_argument("--dataset-root", required=True)
    parser.add_argument("--repo-id", required=True)
    parser.add_argument("--batch-size", type=int, default=2)
    parser.add_argument("--device", default="cuda")
    parser.add_argument("--fps", type=int, default=10)
    parser.add_argument("--chunk-size", type=int, default=100)
    args = parser.parse_args()

    device = args.device if args.device == "cuda" and torch.cuda.is_available() else "cpu"
    result = evaluate(
        Path(args.policy_path),
        Path(args.dataset_root),
        args.repo_id,
        args.batch_size,
        device,
        args.fps,
        args.chunk_size,
    )
    print(
        f"frames={result['frames']} episodes={result['episodes']} "
        f"loss={result['loss']:.4f} l1={result['l1']:.4f} kl={result['kl']:.4f}"
    )


if __name__ == "__main__":
    main()
