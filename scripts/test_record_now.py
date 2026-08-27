#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import pathlib
import subprocess
import sys
from datetime import datetime

PROJECT_ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from nhk_radio_recorder.nhk_api import extract_programs, fetch_schedule, find_program_at
from nhk_radio_recorder.recording import default_stream_urls, parse_services, sanitize_name


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Record a short NHK radio sample immediately.")
    parser.add_argument("--area", default="130", help="NHK area id. Default: 130")
    parser.add_argument("--services", default="r1,r3", help="Comma-separated services. Default: r1,r3")
    parser.add_argument("--seconds", type=int, default=10, help="Sample duration. Default: 10")
    parser.add_argument(
        "--output-dir",
        default="recordings/smoke_test",
        help="Output directory for sample files. Default: recordings/smoke_test",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        services = parse_services(args.services)
        stream_urls = default_stream_urls(services, area=args.area)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    output_dir = pathlib.Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    captured_at = datetime.now().astimezone()
    timestamp = captured_at.strftime("%Y%m%d_%H%M%S")

    for service in services:
        stream_url = stream_urls[service]
        payload = fetch_schedule(service=service, area=args.area, target_date=captured_at.date().isoformat())
        programs = extract_programs(payload)
        current_program = find_program_at(programs, captured_at)
        title = current_program.title if current_program else "unknown_program"
        output_stem = f"{timestamp}_{sanitize_name(service)}_{sanitize_name(title)}"
        output_path = output_dir / f"{output_stem}.m4a"
        metadata_path = output_dir / f"{output_stem}.json"
        command = [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-i",
            stream_url,
            "-vn",
            "-acodec",
            "copy",
            "-t",
            str(args.seconds),
            str(output_path),
        ]
        print(f"Testing {service}: {stream_url}")
        print(f"Writing sample: {output_path}")
        subprocess.run(command, check=True)
        metadata = {
            "captured_at": captured_at.isoformat(),
            "area": args.area,
            "service": service,
            "stream_url": stream_url,
            "title": title,
            "subtitle": current_program.subtitle if current_program else None,
            "start_time": current_program.start_time if current_program else None,
            "end_time": current_program.end_time if current_program else None,
        }
        metadata_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"Finished sample: {output_path}")
        print(f"Wrote metadata: {metadata_path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
