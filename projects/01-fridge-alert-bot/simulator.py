"""Send realistic fake fridge readings to the API, including door openings and failures.

Examples:
    uv run python simulator.py                          # live readings every 15 s
    uv run python simulator.py --backfill-hours 24      # first fill the last 24 h of history
    uv run python simulator.py --fail kitchen-fridge-1  # start with a compressor failure
"""

import argparse
import os
import random
import sys
import time
from datetime import UTC, datetime, timedelta

import httpx

from app.simulation import DEFAULT_PROFILES, FridgeModel

BATCH_SIZE = 2000


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument("--url", default=os.getenv("SIMULATOR_URL", "http://127.0.0.1:8000"))
    parser.add_argument("--api-key", default=os.getenv("API_KEY", ""))
    parser.add_argument("--interval", type=float, default=15, help="seconds between readings")
    parser.add_argument("--backfill-hours", type=float, default=0, help="history to generate first")
    parser.add_argument(
        "--fail",
        action="append",
        default=[],
        metavar="SENSOR",
        help="start a compressor failure on this sensor (can repeat)",
    )
    parser.add_argument("--failures-per-day", type=float, default=1.0)
    parser.add_argument("--seed", type=int, default=None)
    return parser.parse_args()


def reading(sensor_id: str, temperature: float, at: datetime) -> dict[str, object]:
    return {"sensor_id": sensor_id, "temperature": temperature, "timestamp": at.isoformat()}


def setup_limits(client: httpx.Client, models: list[FridgeModel]) -> None:
    for model in models:
        p = model.profile
        client.put(f"/sensors/{p.sensor_id}/limit", json={"limit": p.limit_c}).raise_for_status()
    print("Limits set:", ", ".join(f"{m.profile.sensor_id}={m.profile.limit_c}" for m in models))


def backfill(client: httpx.Client, models: list[FridgeModel], hours: float, step_s: float) -> None:
    now = datetime.now(UTC)
    at = now - timedelta(hours=hours)
    batch: list[dict[str, object]] = []
    while at < now:
        batch.extend(reading(m.profile.sensor_id, m.step(step_s), at) for m in models)
        if len(batch) >= BATCH_SIZE:
            client.post("/readings/batch", json=batch).raise_for_status()
            batch.clear()
        at += timedelta(seconds=step_s)
    if batch:
        client.post("/readings/batch", json=batch).raise_for_status()
    print(f"Backfilled {hours:g} h of history for {len(models)} sensors.")


def live(client: httpx.Client, models: list[FridgeModel], interval: float) -> None:
    print(f"Sending live readings every {interval:g} s. Press Ctrl+C to stop.")
    while True:
        now = datetime.now(UTC)
        for model in models:
            temp = model.step(interval)
            try:
                resp = client.post("/readings", json=reading(model.profile.sensor_id, temp, now))
                resp.raise_for_status()
                state = resp.json()["state"]
            except httpx.HTTPError as exc:
                print(f"  ! {model.profile.sensor_id}: {exc}", file=sys.stderr)
                continue
            print(
                f"{now:%H:%M:%S} {model.profile.sensor_id:<18} {temp:>6.2f} °C  "
                f"[{model.mode}] -> {state}"
            )
        time.sleep(interval)


def main() -> None:
    args = parse_args()
    rng = random.Random(args.seed)
    models = [
        FridgeModel(profile, rng, failures_per_day=args.failures_per_day)
        for profile in DEFAULT_PROFILES
    ]
    headers = {"X-API-Key": args.api_key} if args.api_key else {}
    with httpx.Client(base_url=args.url, headers=headers, timeout=30) as client:
        try:
            setup_limits(client, models)
            if args.backfill_hours:
                backfill(client, models, args.backfill_hours, step_s=30)
        except httpx.HTTPError as exc:
            sys.exit(f"Cannot reach the API at {args.url}: {exc}")
        for model in models:
            if model.profile.sensor_id in args.fail:
                model.force_failure()
                print(f"Compressor failure started on {model.profile.sensor_id}")
        try:
            live(client, models, args.interval)
        except KeyboardInterrupt:
            print("\nStopped.")


if __name__ == "__main__":
    main()
