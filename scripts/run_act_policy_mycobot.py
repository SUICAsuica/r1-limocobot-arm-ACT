#!/usr/bin/env python3
import argparse
import json
import time
import urllib.request

import numpy as np
import torch
from PIL import Image
from lerobot.policies.act.modeling_act import ACTPolicy


STATE_KEYS = ["j1", "j2", "j3", "j4", "j5", "j6", "gripper"]
DEFAULT_POLICY = "/home/shori/outputs/train/act_limo_cobot_center_target_h5/checkpoints/005000/pretrained_model"


def get_json(url: str) -> dict:
    request = urllib.request.Request(url, headers={"Cache-Control": "no-store"})
    with urllib.request.urlopen(request, timeout=2.0) as response:
        return json.loads(response.read().decode("utf-8"))


def get_image(url: str) -> np.ndarray:
    request = urllib.request.Request(url, headers={"Cache-Control": "no-store"})
    with urllib.request.urlopen(request, timeout=2.0) as response:
        return np.asarray(Image.open(response).convert("RGB"))


def make_batch(state: dict, image: np.ndarray, device: str) -> tuple[dict, list[float], float]:
    arm = state.get("arm") or {}
    angles = arm.get("angles")
    gripper = arm.get("gripper_value")
    if not angles or gripper is None:
        raise RuntimeError(f"invalid arm state: {arm}")

    obs_state = np.array([*angles[:6], float(gripper)], dtype=np.float32)
    obs_image = image.astype(np.float32) / 255.0
    obs_image = np.transpose(obs_image, (2, 0, 1))

    batch = {
        "observation.state": torch.from_numpy(obs_state).unsqueeze(0).to(device),
        "observation.images.rgb": torch.from_numpy(obs_image).unsqueeze(0).to(device),
    }
    return batch, angles[:6], float(gripper)


def clamp_delta(delta: np.ndarray, max_delta: float) -> np.ndarray:
    return np.clip(delta, -max_delta, max_delta)


def main():
    parser = argparse.ArgumentParser(description="Run trained LeRobot ACT policy on myCobot280")
    parser.add_argument("--policy-path", default=DEFAULT_POLICY)
    parser.add_argument("--action-mode", choices=["delta", "target"], default="target")
    parser.add_argument("--limo-url", default="http://192.168.0.161:8001")
    parser.add_argument("--port", default="/dev/ttyACM0")
    parser.add_argument("--baud", type=int, default=115200)
    parser.add_argument("--hz", type=float, default=5.0)
    parser.add_argument("--steps", type=int, default=50)
    parser.add_argument("--speed", type=int, default=10)
    parser.add_argument("--max-delta", type=float, default=2.0)
    parser.add_argument("--action-scale", type=float, default=1.0)
    parser.add_argument("--device", default="cuda")
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--send-gripper", action="store_true")
    parser.add_argument("--replan-every-step", action="store_true", default=True)
    args = parser.parse_args()

    base_url = args.limo_url.rstrip("/")
    state_url = f"{base_url}/state.json"
    image_url = f"{base_url}/snapshot.jpg"

    device = args.device if torch.cuda.is_available() and args.device == "cuda" else "cpu"
    policy = ACTPolicy.from_pretrained(args.policy_path)
    policy.to(device)
    policy.eval()
    policy.reset()

    mc = None
    if args.execute:
        from pymycobot import MyCobot280

        mc = MyCobot280(args.port, args.baud)

    print(f"policy: {args.policy_path}")
    print(f"state:  {state_url}")
    print(f"image:  {image_url}")
    print(f"mode:   {'EXECUTE' if args.execute else 'DRY-RUN'}")
    print("Ctrl-C to stop")

    dt = 1.0 / args.hz
    for step in range(args.steps):
        started = time.monotonic()
        state = get_json(state_url)
        image = get_image(image_url)
        batch, current_angles, current_gripper = make_batch(state, image, device)

        if args.replan_every_step:
            policy.reset()

        with torch.no_grad():
            action = policy.select_action(batch)[0].detach().cpu().numpy()

        if args.action_mode == "delta":
            raw_delta = action[:6] * args.action_scale
        else:
            raw_target = np.asarray(current_angles, dtype=np.float32) + (
                action[:6] - np.asarray(current_angles, dtype=np.float32)
            ) * args.action_scale
            raw_delta = raw_target - np.asarray(current_angles, dtype=np.float32)

        delta = clamp_delta(raw_delta, args.max_delta)
        target_angles = [round(float(a + d), 2) for a, d in zip(current_angles, delta)]
        target_gripper = int(np.clip(round(float(action[6])), 0, 100))

        print(
            f"step={step:03d} current={np.round(current_angles, 2).tolist()} "
            f"action={np.round(action[:6], 2).tolist()} "
            f"delta={np.round(delta, 2).tolist()} target={target_angles} "
            f"gripper={current_gripper:.0f}->{target_gripper}"
        )

        if mc is not None:
            mc.send_angles(target_angles, args.speed)
            if args.send_gripper:
                mc.set_gripper_value(target_gripper, args.speed)

        elapsed = time.monotonic() - started
        if elapsed < dt:
            time.sleep(dt - elapsed)


if __name__ == "__main__":
    main()
