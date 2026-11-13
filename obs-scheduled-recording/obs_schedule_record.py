#!/usr/bin/env python3
"""
Start (and optionally stop) an OBS Studio recording at a given time on macOS.

Uses OBS's built-in WebSocket server (OBS 28+), via the `obsws-python` library.

Examples:
    # Start recording today at 14:30 (or tomorrow if 14:30 has already passed)
    python3 obs_schedule_record.py --start 14:30

    # Start at a specific date/time and stop after 45 minutes
    python3 obs_schedule_record.py --start "2026-11-14 09:00" --duration 45

    # Start at 20:00, stop at 21:15
    python3 obs_schedule_record.py --start 20:00 --stop 21:15
"""

import argparse
import os
import subprocess
import sys
import time
from datetime import datetime, timedelta

try:
    import obsws_python as obs
except ImportError:
    sys.exit("Missing dependency. Install it with:  pip3 install obsws-python")


def parse_time(value: str) -> datetime:
    """Accept 'HH:MM', 'HH:MM:SS', 'YYYY-MM-DD HH:MM' or 'YYYY-MM-DD HH:MM:SS'."""
    now = datetime.now()
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"):
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            pass
    for fmt in ("%H:%M:%S", "%H:%M"):
        try:
            t = datetime.strptime(value, fmt).time()
            target = datetime.combine(now.date(), t)
            if target <= now:  # time already passed today -> use tomorrow
                target += timedelta(days=1)
            return target
        except ValueError:
            pass
    raise argparse.ArgumentTypeError(
        f"Invalid time '{value}'. Use HH:MM, HH:MM:SS or 'YYYY-MM-DD HH:MM'."
    )


def wait_until(target: datetime, label: str) -> None:
    print(f"Waiting until {target:%Y-%m-%d %H:%M:%S} to {label}...")
    while True:
        remaining = (target - datetime.now()).total_seconds()
        if remaining <= 0:
            return
        # Sleep in short chunks so the timing stays accurate after the Mac wakes from sleep.
        time.sleep(min(remaining, 1.0))


def ensure_obs_running(launch: bool) -> None:
    running = subprocess.run(["pgrep", "-x", "OBS"], capture_output=True).returncode == 0
    if running:
        return
    if not launch:
        sys.exit("OBS is not running. Open OBS Studio or pass --launch-obs.")
    print("Launching OBS Studio...")
    subprocess.run(["open", "-a", "OBS"], check=True)


def connect(host: str, port: int, password: str, retries: int = 30) -> "obs.ReqClient":
    last_err = None
    for _ in range(retries):
        try:
            return obs.ReqClient(host=host, port=port, password=password, timeout=5)
        except Exception as e:  # OBS may still be starting up
            last_err = e
            time.sleep(2)
    sys.exit(
        f"Could not connect to OBS WebSocket at {host}:{port}: {last_err}\n"
        "In OBS: Tools > WebSocket Server Settings > enable the server and check port/password."
    )


def main() -> None:
    p = argparse.ArgumentParser(description="Schedule an OBS Studio recording.")
    p.add_argument("--start", required=True, type=parse_time,
                   help="When to start: HH:MM, HH:MM:SS or 'YYYY-MM-DD HH:MM'")
    stop = p.add_mutually_exclusive_group()
    stop.add_argument("--stop", type=parse_time, help="When to stop (same formats as --start)")
    stop.add_argument("--duration", type=float, help="Minutes to record before stopping")
    p.add_argument("--host", default="localhost")
    p.add_argument("--port", type=int, default=4455)
    p.add_argument("--password", default=os.environ.get("OBS_WS_PASSWORD", ""),
                   help="WebSocket password (or set OBS_WS_PASSWORD env var)")
    p.add_argument("--launch-obs", action="store_true",
                   help="Open OBS automatically ~1 minute before the start time if it isn't running")
    args = p.parse_args()

    stop_at = args.stop
    if args.duration:
        stop_at = args.start + timedelta(minutes=args.duration)
    if stop_at and stop_at <= args.start:
        stop_at += timedelta(days=1)  # e.g. --start 23:30 --stop 00:30

    # Get OBS ready a minute early so recording starts right on time.
    wait_until(args.start - timedelta(seconds=60), "prepare OBS")
    ensure_obs_running(args.launch_obs)
    client = connect(args.host, args.port, args.password)

    wait_until(args.start, "start recording")
    if client.get_record_status().output_active:
        print("OBS is already recording.")
    else:
        client.start_record()
        print(f"Recording started at {datetime.now():%H:%M:%S}")

    if stop_at:
        wait_until(stop_at, "stop recording")
        resp = client.stop_record()
        print(f"Recording stopped at {datetime.now():%H:%M:%S}")
        path = getattr(resp, "output_path", None)
        if path:
            print(f"Saved to: {path}")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nCancelled.")
