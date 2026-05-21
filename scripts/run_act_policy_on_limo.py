#!/usr/bin/env python3
import argparse
import atexit
import builtins
import json
import sys
import time
import urllib.request
from io import BytesIO
from pathlib import Path

import torch
from PIL import Image
from lerobot.policies.act.modeling_act import ACTPolicy


STATE_KEYS = ["j1", "j2", "j3", "j4", "j5", "j6", "gripper"]
DEFAULT_TARGET_POLICY = (
    "/home/shori/outputs/train/act_limo_cobot_center_target_h5/"
    "checkpoints/005000/pretrained_model"
)


def setup_log_file(log_file: str | None):
    if not log_file:
        return

    path = Path(log_file).expanduser()
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = path.open("a", buffering=1)
    original_print = builtins.print

    def tee_print(*args, **kwargs):
        original_print(*args, **kwargs)
        file_kwargs = dict(kwargs)
        file_kwargs["file"] = handle
        file_kwargs["flush"] = True
        original_print(*args, **file_kwargs)

    builtins.print = tee_print
    atexit.register(handle.close)
    print(f"log file: {path}", flush=True)
    print(f"command: {' '.join(sys.argv)}", flush=True)


def get_json(url: str) -> dict:
    request = urllib.request.Request(url, headers={"Cache-Control": "no-store"})
    with urllib.request.urlopen(request, timeout=2.0) as response:
        return json.loads(response.read().decode("utf-8"))


def post_json(url: str, payload: dict) -> dict:
    body = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=body,
        headers={
            "Content-Type": "application/json",
            "Cache-Control": "no-store",
        },
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=2.0) as response:
        return json.loads(response.read().decode("utf-8"))


def get_image(url: str) -> Image.Image:
    request = urllib.request.Request(url, headers={"Cache-Control": "no-store"})
    with urllib.request.urlopen(request, timeout=2.0) as response:
        return Image.open(BytesIO(response.read())).convert("RGB")


def image_to_tensor(image: Image.Image, device: torch.device) -> torch.Tensor:
    if image.size != (640, 480):
        image = image.resize((640, 480))
    data = torch.ByteTensor(torch.ByteStorage.from_buffer(image.tobytes()))
    data = data.view(480, 640, 3).permute(2, 0, 1).float().div(255.0)
    return data.unsqueeze(0).to(device)


def state_to_tensor(angles: list[float], gripper: float, device: torch.device) -> torch.Tensor:
    values = [float(v) for v in angles[:6]] + [float(gripper)]
    return torch.tensor(values, dtype=torch.float32, device=device).unsqueeze(0)


def read_observation(
    limo_url: str,
    image_endpoint: str,
    device: torch.device,
    angles_url: str | None,
    fallback_gripper: float,
    force_angles_url: bool,
):
    state = get_json(f"{limo_url}/state.json")
    arm = state.get("arm") or {}
    angles = arm.get("angles")
    gripper = arm.get("gripper_value")
    angle_source = "state"
    angle_timestamp = arm.get("stamp") or arm.get("timestamp") or state.get("timestamp")

    if force_angles_url:
        if not angles_url:
            raise RuntimeError("--force-angles-url requires --angles-url")
        angle_payload = get_json(angles_url)
        if not angle_payload.get("ok") or not angle_payload.get("angles"):
            raise RuntimeError(f"forced angles failed: {angle_payload}")
        angles = angle_payload["angles"]
        gripper = angle_payload.get("gripper_value", gripper)
        angle_source = "forced"
        angle_timestamp = angle_payload.get("timestamp")
    elif not angles or len(angles) < 6:
        if not angles_url:
            raise RuntimeError(f"state.json has no valid arm angles: {arm.get('error')}")
        angle_payload = get_json(angles_url)
        if not angle_payload.get("ok") or not angle_payload.get("angles"):
            raise RuntimeError(f"fallback angles failed: {angle_payload}")
        angles = angle_payload["angles"]
        angle_source = "fallback"
        angle_timestamp = angle_payload.get("timestamp")
    arm["_angle_source"] = angle_source
    arm["_angle_timestamp"] = angle_timestamp
    if gripper is None:
        gripper = fallback_gripper

    image = get_image(f"{limo_url}/{image_endpoint.lstrip('/')}")
    batch = {
        "observation.state": state_to_tensor(angles, gripper, device),
        "observation.images.rgb": image_to_tensor(image, device),
    }
    return batch, angles[:6], float(gripper), arm


def clamp(value: float, limit: float) -> float:
    return max(-limit, min(limit, value))


def parse_joint_values(value: str | None, expected_len: int = 6) -> list[float] | None:
    if value is None:
        return None
    values = [float(part.strip()) for part in value.split(",") if part.strip()]
    if len(values) != expected_len:
        raise ValueError(f"expected {expected_len} comma-separated values, got {len(values)}: {value}")
    return values


def parse_scalar_or_joint_values(value: str | None):
    if value is None:
        return None
    values = [float(part.strip()) for part in value.split(",") if part.strip()]
    if len(values) == 1:
        return values[0]
    if len(values) == 6:
        return values
    raise ValueError(f"expected scalar or 6 comma-separated values, got {len(values)}: {value}")


def compute_target(
    current_angles,
    action,
    max_delta_deg: float,
    action_mode: str,
    action_scale: float,
    joint_max_delta_deg: list[float] | None,
):
    if action_mode == "delta":
        raw_deltas = [float(v) for v in action[:6]]
    else:
        raw_deltas = [float(target) - float(current) for target, current in zip(action[:6], current_angles)]

    scaled_deltas = [delta * action_scale for delta in raw_deltas]
    limits = joint_max_delta_deg or [max_delta_deg] * 6
    deltas = [clamp(delta, limit) for delta, limit in zip(scaled_deltas, limits)]
    target = [float(a) + d for a, d in zip(current_angles, deltas)]
    cmd_gripper = float(action[6])
    cmd_gripper = max(0.0, min(100.0, cmd_gripper))
    return target, cmd_gripper, deltas, raw_deltas, scaled_deltas


def limit_target_step(previous_target: list[float], target: list[float], limits: list[float] | None):
    if limits is None:
        return target
    return [
        float(prev) + clamp(float(next_value) - float(prev), limit)
        for prev, next_value, limit in zip(previous_target, target, limits)
    ]


def clamp_target_window(center: list[float] | None, target: list[float], window: list[float] | None):
    if center is None or window is None:
        return target
    return [
        max(float(base) - limit, min(float(base) + limit, float(value)))
        for base, value, limit in zip(center, target, window)
    ]


def connect_mycobot(port: str, baud: int):
    from pymycobot import MyCobot280

    return MyCobot280(port, baud)


def send_robot_command(mc, target_angles, cmd_gripper, speed: int, gripper_speed: int, send_gripper: bool):
    mc.send_angles(target_angles, speed)
    if send_gripper:
        try:
            mc.set_gripper_value(int(round(cmd_gripper)), gripper_speed)
        except AttributeError:
            print("warning: pymycobot has no set_gripper_value; skipped gripper command")


def send_http_command(
    command_url: str,
    target_angles,
    cmd_gripper,
    speed: int,
    gripper_speed: int,
    send_gripper: bool,
    max_delta_deg: list[float] | None,
):
    payload = {"angles": target_angles, "speed": speed}
    if max_delta_deg is not None:
        payload["max_delta_deg"] = max_delta_deg
    response = post_json(
        f"{command_url.rstrip('/')}/send_angles",
        payload,
    )
    if not response.get("ok"):
        raise RuntimeError(f"send_angles failed: {response}")

    gripper_response = None
    if send_gripper:
        try:
            gripper_response = post_json(
                f"{command_url.rstrip('/')}/set_gripper",
                {"value": cmd_gripper, "speed": gripper_speed},
            )
            if not gripper_response.get("ok"):
                print(f"warning: set_gripper failed: {gripper_response}", flush=True)
        except Exception as exc:
            gripper_response = {"ok": False, "error": str(exc)}
            print(f"warning: set_gripper skipped after error: {exc}", flush=True)
    return response, gripper_response


def send_http_chunk(command_url: str, chunk: list[dict], payload: dict):
    request_payload = {"chunk": chunk}
    request_payload.update(payload)
    response = post_json(f"{command_url.rstrip('/')}/chunk", request_payload)
    if not response.get("ok"):
        raise RuntimeError(f"chunk send failed: {response}")
    return response


def resolve_gripper_command(
    model_gripper: float,
    step: int,
    gripper_mode: str,
    close_gripper_step: int,
    open_gripper_value: float,
    close_gripper_value: float,
):
    if gripper_mode == "none":
        return model_gripper, False
    if gripper_mode == "model":
        return model_gripper, True
    if gripper_mode == "close_after_step":
        if step < close_gripper_step:
            return open_gripper_value, True
        return close_gripper_value, True
    raise ValueError(f"unknown gripper mode: {gripper_mode}")


def main():
    parser = argparse.ArgumentParser(description="Run trained LeRobot ACT policy on LIMO/myCobot")
    parser.add_argument("--policy-path", default=DEFAULT_TARGET_POLICY)
    parser.add_argument("--action-mode", choices=["delta", "target"], default="target")
    parser.add_argument("--limo-url", default="http://192.168.0.161:8001")
    parser.add_argument(
        "--command-url",
        default=None,
        help="HTTP command bridge URL. Defaults to limo-url when --command-mode=http.",
    )
    parser.add_argument("--image-endpoint", default="image.jpg")
    parser.add_argument(
        "--angles-url",
        default=None,
        help="Fallback angle JSON URL when limo-url/state.json has arm disabled. Defaults to command-url/angles.",
    )
    parser.add_argument("--fallback-gripper", type=float, default=80.0)
    parser.add_argument(
        "--log-file",
        default=None,
        help="Append all runtime console output to this file while still printing to the terminal.",
    )
    parser.add_argument("--hz", type=float, default=5.0)
    parser.add_argument("--steps", type=int, default=0, help="0 means run until Ctrl-C")
    parser.add_argument(
        "--replan-steps",
        type=int,
        default=100,
        help="Reset ACT action queue every N control steps. Use 20 to consume only 20 actions from each chunk.",
    )
    parser.add_argument("--device", default="cuda")
    parser.add_argument("--port", default="/dev/ttyACM0")
    parser.add_argument("--baud", type=int, default=115200)
    parser.add_argument("--speed", type=int, default=10)
    parser.add_argument("--gripper-speed", type=int, default=50)
    parser.add_argument("--max-delta-deg", type=float, default=2.0)
    parser.add_argument("--action-scale", type=float, default=1.0)
    parser.add_argument(
        "--smooth-alpha",
        type=float,
        default=1.0,
        help="Low-pass filter for commanded joint deltas. 1.0 disables smoothing; try 0.3-0.6 for smoother motion.",
    )
    parser.add_argument(
        "--joint-max-delta-deg",
        default=None,
        help="Optional per-joint clamp as j1,j2,j3,j4,j5,j6. Overrides --max-delta-deg.",
    )
    parser.add_argument("--send-gripper", action="store_true", help="Deprecated alias for --gripper-mode model.")
    parser.add_argument(
        "--gripper-mode",
        choices=["none", "model", "model_latch", "close_after_step"],
        default="none",
        help=(
            "none: do not command gripper. model: use policy output. "
            "model_latch: use policy output, then keep closed after it predicts a close value. "
            "close_after_step: open then close by step."
        ),
    )
    parser.add_argument("--close-gripper-step", type=int, default=120)
    parser.add_argument("--open-gripper-value", type=float, default=80.0)
    parser.add_argument("--close-gripper-value", type=float, default=20.0)
    parser.add_argument(
        "--gripper-latch-threshold",
        type=float,
        default=35.0,
        help="For --gripper-mode model_latch, latch closed once the model gripper is at or below this value.",
    )
    parser.add_argument(
        "--gripper-latch-value",
        type=float,
        default=10.0,
        help="For --gripper-mode model_latch, command this value after the latch closes.",
    )
    parser.add_argument(
        "--command-mode",
        choices=["direct", "http", "chunk-http"],
        default="http",
        help=(
            "direct: local USB pymycobot. http: POST one command per step. "
            "chunk-http: POST short action chunks to LIMO smooth controller."
        ),
    )
    parser.add_argument("--chunk-size", type=int, default=20, help="Number of actions to send to /chunk in chunk-http mode.")
    parser.add_argument(
        "--chunk-max-delta-deg",
        default=None,
        help="Optional per-joint LIMO controller clamp for /chunk, as scalar or j1,j2,j3,j4,j5,j6.",
    )
    parser.add_argument(
        "--chunk-smooth-alpha",
        type=float,
        default=None,
        help="Optional LIMO controller smoothing alpha for /chunk.",
    )
    parser.add_argument(
        "--chunk-step-max-delta-deg",
        default=None,
        help="Optional per-step target jump clamp inside each PC-generated chunk, as j1,j2,j3,j4,j5,j6.",
    )
    parser.add_argument(
        "--joint-window-deg",
        default=None,
        help=(
            "Optional absolute target window around the initial qpos, as j1,j2,j3,j4,j5,j6. "
            "Use this to prevent slow drift that moves the camera target out of view."
        ),
    )
    parser.add_argument(
        "--qpos-stale-warn-steps",
        type=int,
        default=15,
        help="Print qpos_stale=warn once the same rounded qpos repeats this many policy steps.",
    )
    parser.add_argument(
        "--force-angles-url",
        action="store_true",
        help="Always use --angles-url for qpos/gripper instead of mixing state.json arm angles with fallback angles.",
    )
    parser.add_argument(
        "--enable-motion",
        action="store_true",
        help="Actually send commands to myCobot. Without this, only prints predicted commands.",
    )
    parser.add_argument(
        "--release-servos",
        action="store_true",
        help="Call release_all_servos before starting. Usually leave this off for policy execution.",
    )
    args = parser.parse_args()
    setup_log_file(args.log_file)

    if args.device == "cuda" and not torch.cuda.is_available():
        raise SystemExit("CUDA was requested but is not available")

    joint_max_delta_deg = parse_joint_values(args.joint_max_delta_deg)
    chunk_step_max_delta_deg = parse_joint_values(args.chunk_step_max_delta_deg)
    joint_window_deg = parse_joint_values(args.joint_window_deg)
    if args.send_gripper and args.gripper_mode == "none":
        args.gripper_mode = "model"
    device = torch.device(args.device)
    print(f"loading policy: {args.policy_path}", flush=True)
    policy = ACTPolicy.from_pretrained(args.policy_path)
    policy.to(device)
    policy.eval()
    policy.reset()
    print("policy loaded", flush=True)

    mc = None
    command_url = args.command_url or args.limo_url
    angles_url = args.angles_url or f"{command_url.rstrip('/')}/angles"
    if args.enable_motion:
        if args.command_mode == "direct":
            mc = connect_mycobot(args.port, args.baud)
            if args.release_servos:
                mc.release_all_servos()
            print(f"motion enabled: direct USB {args.port} baud={args.baud} speed={args.speed}", flush=True)
        else:
            if args.release_servos:
                post_json(f"{command_url.rstrip('/')}/release_all_servos", {})
            print(f"motion enabled: HTTP {command_url} speed={args.speed}", flush=True)
    else:
        print("dry-run mode: not sending commands. Add --enable-motion to move the robot.", flush=True)

    period = 1.0 / args.hz
    step = 0
    next_time = time.monotonic()
    previous_deltas = None
    gripper_latched = False
    chunk_send_count = 0
    previous_current_angles = None
    qpos_stale_steps = 0
    joint_window_center = None

    print(f"policy: {Path(args.policy_path)}", flush=True)
    print(f"observation: {args.limo_url}/state.json + /{args.image_endpoint}", flush=True)
    print(f"fallback angles: {angles_url}", flush=True)
    print("Ctrl-C to stop", flush=True)

    try:
        while args.steps <= 0 or step < args.steps:
            now = time.monotonic()
            if now < next_time:
                time.sleep(min(0.01, next_time - now))
                continue
            next_time += period

            try:
                if args.replan_steps > 0 and step > 0 and step % args.replan_steps == 0:
                    policy.reset()
                    print(f"replanned action chunk at step={step}", flush=True)

                batch, current_angles, current_gripper, arm = read_observation(
                    args.limo_url.rstrip("/"),
                    args.image_endpoint,
                    device,
                    angles_url,
                    args.fallback_gripper,
                    args.force_angles_url,
                )
                rounded_current_angles = tuple(round(float(v), 2) for v in current_angles)
                if previous_current_angles == rounded_current_angles:
                    qpos_stale_steps += 1
                else:
                    qpos_stale_steps = 0
                    previous_current_angles = rounded_current_angles
                qpos_timestamp = arm.get("_angle_timestamp")
                qpos_age = None
                if qpos_timestamp is not None:
                    try:
                        qpos_age = time.time() - float(qpos_timestamp)
                    except (TypeError, ValueError):
                        qpos_age = None
                qpos_stale_status = (
                    "warn" if qpos_stale_steps >= args.qpos_stale_warn_steps else "ok"
                )
                if joint_window_center is None:
                    joint_window_center = [float(v) for v in current_angles[:6]]
                    if joint_window_deg is not None:
                        print(
                            "joint window center={center} window={window}".format(
                                center=[round(v, 2) for v in joint_window_center],
                                window=joint_window_deg,
                            ),
                            flush=True,
                        )
                with torch.no_grad():
                    action = policy.select_action(batch).squeeze(0).detach().cpu().tolist()
                target, cmd_gripper, deltas, raw_deltas, scaled_deltas = compute_target(
                    current_angles,
                    action,
                    args.max_delta_deg,
                    args.action_mode,
                    args.action_scale,
                    joint_max_delta_deg,
                )
                if args.smooth_alpha < 1.0:
                    alpha = max(0.0, min(1.0, args.smooth_alpha))
                    if previous_deltas is None:
                        smoothed_deltas = deltas
                    else:
                        smoothed_deltas = [
                            alpha * delta + (1.0 - alpha) * prev
                            for delta, prev in zip(deltas, previous_deltas)
                        ]
                    previous_deltas = smoothed_deltas
                    deltas = smoothed_deltas
                    target = [float(angle) + delta for angle, delta in zip(current_angles, deltas)]
                else:
                    previous_deltas = deltas
                target[:6] = clamp_target_window(joint_window_center, target[:6], joint_window_deg)

                if args.command_mode == "chunk-http" and (step == 0 or step % args.replan_steps == 0):
                    limited_target = limit_target_step(current_angles, target[:6], chunk_step_max_delta_deg)
                    limited_target = clamp_target_window(joint_window_center, limited_target, joint_window_deg)
                    chunk = [{"angles": limited_target, "gripper": cmd_gripper}]
                    previous_chunk_target = limited_target
                    for _ in range(max(0, args.chunk_size - 1)):
                        with torch.no_grad():
                            chunk_action = policy.select_action(batch).squeeze(0).detach().cpu().tolist()
                        chunk_target, chunk_gripper, _, _, _ = compute_target(
                            current_angles,
                            chunk_action,
                            args.max_delta_deg,
                            args.action_mode,
                            args.action_scale,
                            joint_max_delta_deg,
                        )
                        limited_chunk_target = limit_target_step(
                            previous_chunk_target,
                            chunk_target[:6],
                            chunk_step_max_delta_deg,
                        )
                        limited_chunk_target = clamp_target_window(
                            joint_window_center,
                            limited_chunk_target,
                            joint_window_deg,
                        )
                        chunk.append({"angles": limited_chunk_target, "gripper": chunk_gripper})
                        previous_chunk_target = limited_chunk_target
            except Exception as exc:
                print(f"step={step} skipped: {exc}", flush=True)
                continue

            gripper_command, should_send_gripper = resolve_gripper_command(
                cmd_gripper,
                step,
                "model" if args.gripper_mode == "model_latch" else args.gripper_mode,
                args.close_gripper_step,
                args.open_gripper_value,
                args.close_gripper_value,
            )
            if args.gripper_mode == "model_latch":
                should_send_gripper = True
                if gripper_latched or cmd_gripper <= args.gripper_latch_threshold:
                    gripper_latched = True
                    gripper_command = args.gripper_latch_value

            print(
                "step={step} mode={mode} current={current} raw_delta={raw_delta} scaled_delta={scaled_delta} "
                "clamped_delta={delta} target={target} "
                "gripper={gripper:.1f}->model:{cmd_gripper:.1f} command:{gripper_command:.1f} "
                "qpos_source={qpos_source} qpos_stale_steps={qpos_stale_steps} "
                "qpos_age={qpos_age} qpos_stale={qpos_stale}".format(
                    step=step,
                    mode=args.action_mode,
                    current=[round(v, 2) for v in current_angles],
                    raw_delta=[round(v, 3) for v in raw_deltas],
                    scaled_delta=[round(v, 3) for v in scaled_deltas],
                    delta=[round(v, 3) for v in deltas],
                    target=[round(v, 2) for v in target],
                    gripper=current_gripper,
                    cmd_gripper=cmd_gripper,
                    gripper_command=gripper_command,
                    qpos_source=arm.get("_angle_source", "unknown"),
                    qpos_stale_steps=qpos_stale_steps,
                    qpos_age=round(qpos_age, 3) if qpos_age is not None else "unknown",
                    qpos_stale=qpos_stale_status,
                ),
                flush=True,
            )

            if args.enable_motion:
                if args.command_mode == "direct":
                    send_robot_command(
                        mc,
                        target,
                        gripper_command,
                        args.speed,
                        args.gripper_speed,
                        should_send_gripper,
                    )
                elif args.command_mode == "http":
                    response, gripper_response = send_http_command(
                        command_url,
                        target,
                        gripper_command,
                        args.speed,
                        args.gripper_speed,
                        should_send_gripper,
                        joint_max_delta_deg,
                    )
                    print(
                        "  http sent={sent} server_delta={delta}".format(
                            sent=[round(v, 2) for v in response.get("sent_angles", [])],
                            delta=response.get("clamped_delta"),
                        ),
                        flush=True,
                    )
                    if gripper_response is not None:
                        print(
                            "  gripper sent={value} result={result}".format(
                                value=gripper_response.get("gripper"),
                                result=gripper_response.get("driver_result"),
                            ),
                            flush=True,
                        )
                else:
                    if step == 0 or step % args.replan_steps == 0:
                        if args.gripper_mode == "model_latch":
                            latched_in_chunk = gripper_latched
                            for item in chunk:
                                item_gripper = item.get("gripper")
                                if item_gripper is None:
                                    continue
                                if latched_in_chunk or float(item_gripper) <= args.gripper_latch_threshold:
                                    latched_in_chunk = True
                                    item["gripper"] = args.gripper_latch_value
                            gripper_latched = latched_in_chunk
                        payload = {
                            "speed": args.speed,
                            "gripper_speed": args.gripper_speed,
                            "gripper_mode": args.gripper_mode,
                            "gripper_latch_threshold": args.gripper_latch_threshold,
                            "gripper_latch_value": args.gripper_latch_value,
                        }
                        if args.chunk_max_delta_deg is not None:
                            payload["max_delta_deg"] = parse_scalar_or_joint_values(args.chunk_max_delta_deg)
                        if args.chunk_smooth_alpha is not None:
                            payload["smooth_alpha"] = args.chunk_smooth_alpha
                        if step == 0:
                            payload["reset_gripper_latch"] = True
                        response = send_http_chunk(command_url, chunk, payload)
                        chunk_send_count += 1
                        chunk_grippers = [float(item["gripper"]) for item in chunk if item.get("gripper") is not None]
                        print(
                            (
                                "  chunk sent len={length} count={count} speed={speed} "
                                "gripper_first={g_first:.1f} gripper_min={g_min:.1f} gripper_last={g_last:.1f}"
                            ).format(
                                length=response.get("received"),
                                count=chunk_send_count,
                                speed=response.get("speed"),
                                g_first=chunk_grippers[0] if chunk_grippers else float("nan"),
                                g_min=min(chunk_grippers) if chunk_grippers else float("nan"),
                                g_last=chunk_grippers[-1] if chunk_grippers else float("nan"),
                            ),
                            flush=True,
                        )

            step += 1
    except KeyboardInterrupt:
        print("\nstopped", flush=True)


if __name__ == "__main__":
    main()
