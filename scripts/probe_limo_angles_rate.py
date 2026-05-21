#!/usr/bin/env python3
import argparse
import json
import time
import urllib.request


def get_json(url: str) -> dict:
    request = urllib.request.Request(url, headers={"Cache-Control": "no-store"})
    with urllib.request.urlopen(request, timeout=1.0) as response:
        return json.loads(response.read().decode("utf-8"))


def main():
    parser = argparse.ArgumentParser(description="Probe /angles freshness from the PC side.")
    parser.add_argument("--url", default="http://192.168.0.161:8002/angles")
    parser.add_argument("--hz", type=float, default=20.0)
    parser.add_argument("--seconds", type=float, default=10.0)
    args = parser.parse_args()

    period = 1.0 / args.hz
    deadline = time.monotonic() + args.seconds
    next_time = time.monotonic()
    last_angles = None
    total = 0
    changed = 0
    stale_run = 0
    max_stale_run = 0
    errors = 0

    while time.monotonic() < deadline:
        now = time.monotonic()
        if now < next_time:
            time.sleep(min(0.01, next_time - now))
            continue
        next_time += period
        total += 1
        try:
            payload = get_json(args.url)
            angles = payload.get("angles")
            if not angles:
                errors += 1
                continue
            rounded = tuple(round(float(v), 2) for v in angles[:6])
            if last_angles is None or rounded != last_angles:
                changed += 1
                stale_run = 0
            else:
                stale_run += 1
                max_stale_run = max(max_stale_run, stale_run)
            last_angles = rounded
            print(
                f"sample={total} changed={changed} stale_run={stale_run} "
                f"angles={list(rounded)}",
                flush=True,
            )
        except Exception as exc:
            errors += 1
            print(f"sample={total} error={exc}", flush=True)

    change_rate = changed / total if total else 0.0
    print(
        f"summary total={total} changed={changed} change_rate={change_rate:.3f} "
        f"max_stale_run={max_stale_run} max_stale_sec={max_stale_run / args.hz:.3f} "
        f"errors={errors}",
        flush=True,
    )


if __name__ == "__main__":
    main()
