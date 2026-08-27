#!/usr/bin/env python3
from __future__ import annotations

import argparse
import pathlib
import sys

PROJECT_ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from nhk_radio_recorder.nhk_api import NhkApiError
from nhk_radio_recorder.recording import (
    build_targets_for_day,
    default_stream_urls,
    format_target,
    parse_services,
    resolve_target_date,
    run_live_recording_schedule,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="List or record NHK radio drama, reading, and Radio Midnight shows."
    )
    parser.add_argument("--area", default="130", help="NHK area id. Default: 130 (Tokyo)")
    parser.add_argument(
        "--services",
        default="r1,r3",
        help="Comma-separated NHK service ids. Default: r1,r3",
    )
    parser.add_argument("--date", dest="target_date", help="Date in YYYY-MM-DD format")
    parser.add_argument(
        "--output-dir",
        default="recordings",
        help="Recording root directory. Default: recordings",
    )
    parser.add_argument(
        "--record",
        action="store_true",
        help="Actually record audio with ffmpeg. Without this flag, only print the plan.",
    )
    parser.add_argument(
        "--rules",
        dest="rules_path",
        help="Path to a JSON file that defines recording selection rules.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    try:
        services = parse_services(args.services)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    target_date = resolve_target_date(args.target_date)

    try:
        targets = build_targets_for_day(
            area=args.area,
            services=services,
            target_date=target_date,
            rules_path=args.rules_path,
        )
    except (NhkApiError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    if not targets:
        print(f"No matching programs found for {target_date.isoformat()}.")
        return 0

    print(f"Recording targets for {target_date.isoformat()} ({','.join(services)}):")
    for target in targets:
        print(format_target(target))

    if not args.record:
        return 0

    try:
        stream_urls = default_stream_urls(services, area=args.area)
        run_live_recording_schedule(
            area=args.area,
            services=services,
            target_date=target_date,
            stream_urls=stream_urls,
            output_dir=pathlib.Path(args.output_dir),
            rules_path=args.rules_path,
        )
    except FileNotFoundError:
        print("error: ffmpeg was not found in PATH.", file=sys.stderr)
        return 1
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:
        print(f"error: recording failed: {exc}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
